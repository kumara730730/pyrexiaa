"""
Gemini Integration Service — Handles all LLM interactions for Pyrexia.

This service uses Google's Gemini API (OpenAI-compatible endpoint) for
triage assessment, reasoning, and brief generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger("llm_service")

# ── Client singletons ────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_in_memory_history: dict[str, list[dict]] = {}

async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    return _redis

# ── Configuration ────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# Google Gemini OpenAI-compatible endpoint
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

# Compatibility constants (kept for any imports elsewhere)
SONNET_MODEL = MODEL
HAIKU_MODEL = MODEL

# ── Redis keys & TTL ─────────────────────────────────────────────────────────

HISTORY_TTL = 7200  # 2 hours

def _history_key(session_id: str) -> str:
    return f"session:{session_id}:messages"

# ── System prompts ───────────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
You are Pyrexia, a senior clinical triage specialist operating through a multilingual AI medical kiosk.

Language: Respond ONLY in {language}.
Voice Distress Score: {voice_distress_score}/100.

Your Absolute Mandate:
1. Conduct a deep, systematic clinical assessment. Ask focused follow-up questions ONE AT A TIME.
2. Gather detailed data on: onset, character of pain, severity (1-10), radiation, associated systemic symptoms, and medical history.
3. Provide rigorous clinical reasoning. 

When you have sufficient data (3-5 exchanges) to classify the patient, you MUST respond with a valid JSON object and NOTHING ELSE. 

Your JSON MUST follow this exact schema:
{{
  "urgency_score": <int 0-100>,
  "urgency_level": "<CRITICAL|HIGH|MODERATE|LOW|NON_URGENT>",
  "reasoning_trace": ["<differential diagnosis logic step 1>", "<step 2>"],
  "recommended_action": "<action>",
  "estimated_wait_minutes": <int>,
  "red_flags": ["<flag 1>"],
  "chief_complaint_refined": "<refined line>"
}}

Scoring guidance:
  90-100 CRITICAL (Life-threatening)
  70-89  HIGH (Needs rapid assessment)
  40-69  MODERATE (Semi-urgent)
  20-39  LOW
  0-19   NON_URGENT"""

BRIEF_SYSTEM_PROMPT = """\
You are a clinical documentation AI. Generate a concise, actionable pre-visit brief for the attending doctor.
Output ONLY this JSON format:
{{
  "brief_summary": "2-3 sentences.",
  "priority_flags": ["flag 1"],
  "context_from_history": "Relevant history.",
  "suggested_opening_questions": ["q1"],
  "watch_for": "Critical finding"
}}"""

# ── Shared HTTP helper ───────────────────────────────────────────────────────

def _get_headers() -> dict:
    """Build auth headers for the Gemini OpenAI-compatible endpoint."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GEMINI_API_KEY}",
    }

# ── Redis conversation-history helpers ────────────────────────────────────────

async def _load_history(session_id: str) -> list[dict]:
    """Load full conversation history (fallback to in-memory if Redis fails)."""
    try:
        r = await _get_redis()
        raw_list = await r.lrange(_history_key(session_id), 0, -1)
        if raw_list:
            return [json.loads(m) for m in raw_list]
    except Exception:
        pass
    return _in_memory_history.get(session_id, [])

async def _append_to_history(session_id: str, role: str, content: str) -> None:
    """Append one message (fallback to in-memory if Redis fails)."""
    message = {"role": role, "content": content}
    try:
        r = await _get_redis()
        key = _history_key(session_id)
        await r.rpush(key, json.dumps(message))
        await r.expire(key, HISTORY_TTL)
    except Exception:
        if session_id not in _in_memory_history:
            _in_memory_history[session_id] = []
        _in_memory_history[session_id].append(message)

# ═════════════════════════════════════════════════════════════════════════════
# 1.  stream_triage_message  — Gemini streaming with JSON detection
# ═════════════════════════════════════════════════════════════════════════════

async def stream_triage_message(
    session_id: str,
    patient_message: str,
    language: str = "en",
    voice_distress_score: float = 0.0,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams response from Gemini. If JSON is detected, emits scoring sentinel.
    """
    await _append_to_history(session_id, "user", patient_message)

    if conversation_history is None:
        conversation_history = await _load_history(session_id)
    
    system_msg = {"role": "system", "content": TRIAGE_SYSTEM_PROMPT.format(
        language=language, voice_distress_score=voice_distress_score
    )}
    
    messages = [system_msg] + conversation_history
    
    full_response_text = []
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat/completions",
                headers=_get_headers(),
                json={
                    "model": MODEL,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.1,
                    "max_tokens": 500,
                }
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"Gemini error {response.status_code}: {error_body.decode()}")
                    yield "I'm having trouble connecting to the AI service. Please try again."
                    return

                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue
                    
                    if line.startswith("data: "):
                        raw_data = line[6:]
                        if raw_data.strip() == "[DONE]":
                            continue
                        try:
                            data = json.loads(raw_data)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    full_response_text.append(token)
                                    yield token
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping malformed SSE line: {raw_data[:100]}")
                            continue

    except httpx.TimeoutException:
        logger.error("Gemini streaming timed out")
        yield "The request timed out. Please try again."
        return
    except Exception as exc:
        logger.error(f"Gemini streaming failed: {exc}")
        yield "I'm having trouble connecting. Please try again."
        return

    full_response = "".join(full_response_text)
    await _append_to_history(session_id, "assistant", full_response)

    # Check if the response is JSON (Scoring)
    stripped = full_response.strip()
    # Handle markdown-wrapped JSON (```json ... ```)
    if stripped.startswith("```"):
        # Extract content between code fences
        lines = stripped.split("\n")
        json_lines = []
        in_block = False
        for l in lines:
            if l.strip().startswith("```") and not in_block:
                in_block = True
                continue
            elif l.strip().startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(l)
        stripped = "\n".join(json_lines).strip()

    if stripped.startswith("{") and "urgency_score" in stripped:
        try:
            # Basic validation
            score_data = json.loads(stripped)
            yield f"__SCORE_JSON__:{json.dumps(score_data)}"
        except json.JSONDecodeError:
            pass

# ═════════════════════════════════════════════════════════════════════════════
# 2.  get_triage_response  — Simple wrapper for initial greeting/questions
# ═════════════════════════════════════════════════════════════════════════════

async def get_triage_response(
    conversation_history: list[dict],
    language: str = "en",
    voice_distress_score: float = 0.0,
) -> str:
    """
    Get a single (non-streaming) response from Gemini.
    Used for the very first greeting/question.
    """
    system_msg = {"role": "system", "content": TRIAGE_SYSTEM_PROMPT.format(
        language=language, voice_distress_score=voice_distress_score
    )}
    messages = [system_msg] + conversation_history

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=_get_headers(),
                json={
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 300,
                }
            )
            if response.status_code != 200:
                logger.error(f"Gemini error {response.status_code}: {response.text}")
                return "Hello! I'm Pyrexia, your medical triage assistant. Could you tell me more about your symptoms?"
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error(f"Gemini call failed: {exc}")
        return "Hello! I'm Pyrexia, your medical triage assistant. Could you tell me more about your symptoms?"

# ═════════════════════════════════════════════════════════════════════════════
# 3.  generate_brief  — Gemini single-call
# ═════════════════════════════════════════════════════════════════════════════

async def generate_brief(
    patient_name: str,
    age: int | None,
    gender: str | None,
    history_notes: str,
    urgency_json: dict,
    voice_distress_score: float = 0.0,
) -> dict:
    """
    Generate a pre-visit doctor brief using Gemini.
    """
    user_content = (
        f"Generate a clinical brief for: {patient_name}, {age or 'Unknown'}y, {gender or 'Unknown'}\n"
        f"History: {history_notes}\n"
        f"Triage: {json.dumps(urgency_json)}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=_get_headers(),
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                }
            )
            if response.status_code != 200:
                logger.error(f"Gemini brief error {response.status_code}: {response.text}")
                return {"brief_summary": "Failed to generate brief."}
            result = response.json()
            raw = result["choices"][0]["message"]["content"].strip()
            # Handle markdown-wrapped JSON
            if raw.startswith("```"):
                lines = raw.split("\n")
                json_lines = []
                in_block = False
                for l in lines:
                    if l.strip().startswith("```") and not in_block:
                        in_block = True
                        continue
                    elif l.strip().startswith("```") and in_block:
                        break
                    elif in_block:
                        json_lines.append(l)
                raw = "\n".join(json_lines).strip()
            return json.loads(raw)
    except Exception as exc:
        logger.error(f"Brief generation failed: {exc}")
        return {"brief_summary": "Failed to generate brief."}

# ═════════════════════════════════════════════════════════════════════════════
# Compatibility Shims (keeping original function names)
# ═════════════════════════════════════════════════════════════════════════════

async def score_triage(conversation_history: list[dict]) -> dict:
    """Score the triage session."""
    system_prompt = "You are a triage scoring engine. Output ONLY valid JSON with no markdown fences."
    user_content = f"Score this conversation: {json.dumps(conversation_history)}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=_get_headers(),
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                }
            )
            if response.status_code != 200:
                logger.error(f"Gemini score error {response.status_code}: {response.text}")
                return {"urgency_score": 50, "urgency_level": "MODERATE"}
            result = response.json()
            raw = result["choices"][0]["message"]["content"].strip()
            # Handle markdown-wrapped JSON
            if raw.startswith("```"):
                lines = raw.split("\n")
                json_lines = []
                in_block = False
                for l in lines:
                    if l.strip().startswith("```") and not in_block:
                        in_block = True
                        continue
                    elif l.strip().startswith("```") and in_block:
                        break
                    elif in_block:
                        json_lines.append(l)
                raw = "\n".join(json_lines).strip()
            return json.loads(raw)
    except Exception:
        return {"urgency_score": 50, "urgency_level": "MODERATE"}
