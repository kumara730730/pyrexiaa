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
GEMINI_SCORING_API_KEY = os.environ.get("GEMINI_SCORING_API_KEY", "") or GEMINI_API_KEY
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
SCORING_MODEL = os.environ.get("GEMINI_SCORING_MODEL", "") or MODEL

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
You are Pyrexia, a quick check-in assistant at a medical clinic kiosk. Your ONLY job is to collect just enough information to determine how urgently this patient needs to be seen.

Language: Respond ONLY in {language}.
Voice Distress Score: {voice_distress_score}/100.

YOU ARE NOT A DOCTOR. Do NOT ask diagnostic questions like "what makes it worse", "does it radiate", "describe the character of pain", or "what is your medical history". Those are the doctor's job. You are a receptionist sorting a queue.

RULES:
1. Ask exactly ONE short question per response. Keep it under 1 sentence.
2. You only need 2-3 quick data points after the chief complaint:
   - How bad is it right now? (severity 1-10)
   - How long has this been going on?
   - Any allergies or medications we should know about?
3. After collecting 2-3 answers, IMMEDIATELY output the scoring JSON. Do not keep asking.
4. Be friendly and brief. Think "clinic receptionist", not "medical examiner".

EXAMPLES OF WHAT TO ASK:
- "On a scale of 1 to 10, how bad is the pain right now?"
- "When did this start?"
- "Are you currently taking any medications or have any allergies?"

EXAMPLES OF WHAT NOT TO ASK (doctor's job):
- "Does the pain radiate anywhere?"
- "What were you doing when it started?"
- "Do you have a family history of...?"
- "Have you experienced this before?"

After 2-3 exchanges, respond with ONLY this JSON:
{{
  "urgency_score": <int 0-100>,
  "urgency_level": "<CRITICAL|HIGH|MODERATE|LOW|NON_URGENT>",
  "reasoning_trace": ["<reason 1>", "<reason 2>"],
  "recommended_action": "<action>",
  "estimated_wait_minutes": <int>,
  "red_flags": ["<flag 1>"],
  "chief_complaint_refined": "<one line summary>",
  "recommended_doctor_specialty": "<General Practice|Cardiology|Neurology|Orthopaedics|Dermatology|ENT|Gastroenterology|Pulmonology|Psychiatry|Emergency>"
}}

Scoring:
  90-100 CRITICAL — 70-89 HIGH — 40-69 MODERATE — 20-39 LOW — 0-19 NON_URGENT"""

BRIEF_SYSTEM_PROMPT = """\
You are a clinical documentation AI for Pyrexia. Generate a concise, actionable pre-visit brief for the attending doctor.

The doctor has approximately 30 seconds to read this before entering the exam room.
Be direct. Prioritise what the doctor needs to act on immediately.
Do not repeat information that can be inferred. No filler.

Output ONLY this JSON — no prose, no markdown:

{
  "brief_summary": "2-3 sentences. Chief complaint, severity, most important context.",
  "priority_flags": ["flag 1", "flag 2", "flag 3"],
  "context_from_history": "Relevant past medical info in one sentence. 'No known history' if none.",
  "suggested_opening_questions": ["q1", "q2", "q3"],
  "watch_for": "ONE thing to assess immediately upon entering the room."
}"""

RERANK_PROMPT_TEMPLATE = """\
You are a medical queue optimiser. Given a list of waiting patients, determine the optimal order they should be seen.

RULES:
1. CRITICAL patients always first, regardless of wait time
2. Among same urgency_level: longer wait time first (fairness)
3. voice_distress_score > 7 bumps priority by one position within same level
4. Never reorder past a CRITICAL patient

Patient queue:
{queue_json}

Return ONLY this JSON, no explanation:
{{"ordered_ids": ["id1", "id2", "id3"]}}"""

DIAGNOSTIC_SYSTEM_PROMPT = """\
You are a Pyrexia Diagnostic Specialist.
Language: Respond ONLY in {language}.
Voice Distress Score: {voice_distress_score}/100.

Your task is to ask deep follow-up questions regarding the specific symptoms mentioned to identify potential underlying conditions.
Do not output JSON, just ask the patient one clear, empathetic question at a time. Do not make a final diagnosis yet."""

VERIFICATION_SYSTEM_PROMPT = TRIAGE_SYSTEM_PROMPT

AGENT_REGISTRY = {
    "triage_orchestrator": TRIAGE_SYSTEM_PROMPT,
    "diagnostic_specialist": DIAGNOSTIC_SYSTEM_PROMPT,
    "verification_agent": VERIFICATION_SYSTEM_PROMPT,
}

# ── Shared HTTP helpers ──────────────────────────────────────────────────────
def _get_headers() -> dict:
    """Build auth headers for the Gemini endpoint — used for CHAT."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GEMINI_API_KEY}",
    }

def _get_scoring_headers() -> dict:
    """Build auth headers for the Gemini endpoint — used for SCORING/ANALYSIS."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GEMINI_SCORING_API_KEY}",
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
    agent_id: str = "triage_orchestrator",
    conversation_history: list[dict] | None = None,
    append_history: bool = True,
) -> AsyncGenerator[str, None]:
    """
    Streams response from Gemini. If JSON is detected, emits scoring sentinel.
    """
    if append_history:
        await _append_to_history(session_id, "user", patient_message)

    if conversation_history is None:
        conversation_history = await _load_history(session_id)

    
    # Select system prompt based on agent_id
    system_prompt_template = AGENT_REGISTRY.get(agent_id, AGENT_REGISTRY["triage_orchestrator"])
    system_msg = {"role": "system", "content": system_prompt_template.format(
        language=language, voice_distress_score=voice_distress_score
    )}
    
    messages = [system_msg] + conversation_history

    
    full_response_text = []
    
    is_json_response = None
    buffer = ""
    
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
                    "max_tokens": 200,
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
                                    if is_json_response is None:
                                        buffer += token
                                        stripped_buffer = buffer.lstrip()
                                        if not stripped_buffer:
                                            continue  # Still whitespace, wait for more tokens
                                        if stripped_buffer.startswith("{") or stripped_buffer.startswith("```"):
                                            is_json_response = True
                                        else:
                                            is_json_response = False
                                            yield buffer
                                            buffer = ""
                                    elif is_json_response:
                                        pass  # We suspect this is JSON, do not yield tokens to the chat UI
                                    else:
                                        yield token
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping malformed SSE line: {raw_data[:100]}")
                            continue

    except httpx.TimeoutException:
        logger.error("Gemini streaming timed out")
        yield "The request timed out. Please try again."
        return
    except Exception as exc:
        logger.error(f"Gemini streaming failed: {exc}", exc_info=True)
        yield "I'm having trouble connecting. Please try again."
        return

    full_response = "".join(full_response_text)
    await _append_to_history(session_id, "assistant", full_response)

    # Check if the response is JSON (Scoring)
    stripped = full_response.strip()
    is_valid_score = False

    # Try to extract JSON between markdown fences
    if "```" in stripped:
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
        if json_lines:
            stripped = "\n".join(json_lines).strip()

    # robust extraction if normal check fails but contains JSON
    if not stripped.startswith("{") and "urgency_score" in stripped:
        start_idx = stripped.find("{")
        end_idx = stripped.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            stripped = stripped[start_idx:end_idx+1]

    if stripped.startswith("{") and "urgency_score" in stripped:
        try:
            # Basic validation
            score_data = json.loads(stripped)
            yield f"__SCORE_JSON__:{json.dumps(score_data)}"
            is_valid_score = True
        except json.JSONDecodeError:
            pass

    # If we suppressed tokens but it turned out NOT to be a valid score, yield it now as fallback
    if is_json_response and not is_valid_score:
        yield full_response

# ═════════════════════════════════════════════════════════════════════════════
# 2.  get_triage_response  — Simple wrapper for initial greeting/questions
# ═════════════════════════════════════════════════════════════════════════════

async def get_triage_response(
    conversation_history: list[dict],
    language: str = "en",
    voice_distress_score: float = 0.0,
    agent_id: str = "triage_orchestrator",
) -> str:
    """
    Get a single (non-streaming) response from Gemini.
    Used for the very first greeting/questions.
    """
    # Select system prompt based on agent_id
    system_prompt_template = AGENT_REGISTRY.get(agent_id, AGENT_REGISTRY["triage_orchestrator"])
    system_msg = {"role": "system", "content": system_prompt_template.format(
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
                    "max_tokens": 150,
                }
            )
            if response.status_code != 200:
                logger.error(f"Gemini error {response.status_code}: {response.text}")
                return "Hello! I'm Pyrexia, your medical triage assistant. Could you tell me more about your symptoms?"
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error(f"Gemini call failed: {exc}", exc_info=True)
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
                headers=_get_scoring_headers(),
                json={
                    "model": SCORING_MODEL,
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
    except json.JSONDecodeError:
        logger.warning("Brief response was not valid JSON — wrapping raw text")
        return {
            "brief_summary": raw,
            "priority_flags": [],
            "context_from_history": history_notes or "No known history",
            "suggested_opening_questions": [],
            "watch_for": "Review triage notes",
        }
    except Exception as exc:
        logger.error(f"Brief generation failed: {exc}")
        return {"brief_summary": "Failed to generate brief."}

# ═════════════════════════════════════════════════════════════════════════════
# 3.  rerank_queue  — Gemini (fast + cheap)
# ═════════════════════════════════════════════════════════════════════════════

async def rerank_queue(queue_items: list[dict]) -> list[dict]:
    """
    Ask Gemini to optimally order patients by urgency, wait time, and distress.

    Returns *queue_items* reordered.  On failure returns the original list.
    """
    if len(queue_items) <= 1:
        return queue_items

    # Compute wait_minutes for each item
    current_time = time.time()
    for item in queue_items:
        enq = item.get("enqueued_at")
        wait_minutes = 0.0
        if isinstance(enq, (int, float)):
            wait_minutes = (current_time - enq) / 60.0
        elif isinstance(enq, str):
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(enq.replace("Z", "+00:00"))
                wait_minutes = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
            except ValueError:
                pass
        elif hasattr(enq, "timestamp"):
            wait_minutes = (current_time - enq.timestamp()) / 60.0
        item["wait_minutes"] = max(0.0, wait_minutes)

    # Prepare a minimal JSON for Gemini to save tokens
    clean_queue = [
        {
            "id": str(item.get("patient_id") or item.get("id")),
            "urgency_score": item.get("urgency_score", 0),
            "urgency_level": str(item.get("urgency_level", "LOW")),
            "wait_minutes": int(item.get("wait_minutes", 0)),
            "voice_distress_score": item.get("voice_distress_score", 0),
        }
        for item in queue_items
    ]
    queue_json = json.dumps(clean_queue, indent=2)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=_get_scoring_headers(),
                json={
                    "model": SCORING_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": RERANK_PROMPT_TEMPLATE.format(queue_json=queue_json),
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 200,
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Gemini rerank error {response.status_code}: {response.text}")
                return queue_items

            result = response.json()
            raw = result["choices"][0]["message"]["content"].strip()
            
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0].strip()

            result = json.loads(raw)
            ordered_ids = result.get("ordered_ids", [])

            # Rebuild in recommended order
            id_map = {
                str(item.get("patient_id") or item.get("id")): item
                for item in queue_items
            }
            reordered = []
            for pid in ordered_ids:
                pid_str = str(pid)
                if pid_str in id_map:
                    reordered.append(id_map.pop(pid_str))
            # Append any items Gemini omitted (safety net)
            reordered.extend(id_map.values())
            return reordered

    except Exception as exc:
        logger.warning("Gemini rerank failed (%s) — using Python fallback", exc)
        return sorted(
            queue_items,
            key=lambda x: (x.get("urgency_score", 0) * 0.8) + (x.get("wait_minutes", 0) * 0.2),
            reverse=True,
        )

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
                headers=_get_scoring_headers(),
                json={
                    "model": SCORING_MODEL,
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
