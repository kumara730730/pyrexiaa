"""
Anthropic API integration — ALL Claude interactions for Pyrexia.

Model split
───────────
• claude-sonnet-4-20250514   → triage agent (deep symptom reasoning)
• claude-haiku-4-5-20251001  → lightweight queue re-ranking (~70 % cheaper)

Conversation history is kept in Redis at  session:{session_id}:messages  (TTL 2 h).
Each ``stream_triage_message`` call appends the patient message, sends the full
history to Sonnet, and yields tokens for SSE.  When the streamed response is
valid JSON (scoring complete) the caller is signalled via a sentinel event so
it can persist the score, fire the Brief Builder, and broadcast the queue.

If the Anthropic API fails after 3 retries the service falls back to a cached
demo response stored in Supabase's ``demo_cache`` table.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator

import anthropic
import redis.asyncio as aioredis

logger = logging.getLogger("claude_service")

# ── Client singletons ────────────────────────────────────────────────────────

_client: anthropic.AsyncAnthropic | None = None
_redis: aioredis.Redis | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    return _client


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    return _redis


# ── Model constants ──────────────────────────────────────────────────────────

SONNET_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# ── Redis keys & TTL ─────────────────────────────────────────────────────────

HISTORY_TTL = 7200  # 2 hours


def _history_key(session_id: str) -> str:
    return f"session:{session_id}:messages"


# ── System prompts ───────────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
You are Pyrexia, a multilingual AI medical triage assistant operating in a
clinic waiting-room kiosk.

Language: Respond ONLY in {language}.
Voice Distress Score: {voice_distress_score}/100 (higher = more distressed tone
detected via voice analysis; factor this into your urgency assessment).

Your task:
1. Ask focused follow-up questions ONE AT A TIME to assess urgency.
2. Gather: onset, severity (1-10), duration, associated symptoms, medical history.
3. Be empathetic but concise — patients are unwell and need efficiency.
4. Never diagnose or prescribe medications.
5. If life-threatening symptoms are described, urge the patient to alert staff
   immediately while you continue assessment.

When you have gathered ENOUGH information to score (typically 3-5 exchanges),
respond with ONLY a JSON object (no markdown fences, no extra text):

{{
  "urgency_score": <int 0-100>,
  "urgency_level": "<CRITICAL|HIGH|MODERATE|LOW|NON_URGENT>",
  "reasoning_trace": ["<step-by-step reasoning>"],
  "recommended_action": "<brief recommendation>",
  "estimated_wait_minutes": <int or null>,
  "red_flags": ["<any alarming findings>"],
  "chief_complaint_refined": "<1-line refined complaint>"
}}

Scoring guidance:
  90-100  CRITICAL   → Immediate life-threatening
  70-89   HIGH       → Urgent, needs rapid assessment
  40-69   MODERATE   → Semi-urgent
  20-39   LOW        → Non-urgent but needs attention
  0-19    NON_URGENT → Can wait / self-care"""

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
Given this queue of patients with urgency scores, return the optimal ordering
as a JSON array of patient IDs.

Factors: urgency_score (primary), wait_time_minutes (secondary for ties),
voice_distress_score (tiebreaker).

Queue: {queue_json}

Return ONLY: {{"ordered_ids": [id1, id2, ...]}}"""

# Standalone scoring prompt (used by legacy score_triage)
SCORING_SYSTEM_PROMPT = """\
You are Pyrexia's triage scoring engine.  Given the full conversation between
the triage assistant and a patient, produce a JSON object with these fields:

{
  "urgency_score": <int 0-100>,
  "urgency_level": "<CRITICAL|HIGH|MODERATE|LOW|NON_URGENT>",
  "reasoning_trace": ["<step-by-step reasoning>"],
  "recommended_action": "<brief recommendation>",
  "estimated_wait_minutes": <int or null>
}

Return ONLY valid JSON, no markdown fences."""

# ── Retry helper ─────────────────────────────────────────────────────────────

_RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


async def _retry_api_call(coro_factory, *, max_attempts: int = 3):
    """
    Retry an async Anthropic call with exponential backoff.

    *coro_factory* is a zero-arg callable returning a fresh awaitable each time.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = 2 ** attempt
                logger.warning(
                    "Anthropic attempt %d/%d failed (%s), retry in %ds",
                    attempt, max_attempts, type(exc).__name__, wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Anthropic API failed after %d attempts: %s",
                    max_attempts, exc,
                )
    raise last_exc  # type: ignore[misc]


# ── Redis conversation-history helpers ────────────────────────────────────────


async def _load_history(session_id: str) -> list[dict]:
    """Load full conversation history from Redis list."""
    r = await _get_redis()
    raw_list = await r.lrange(_history_key(session_id), 0, -1)
    return [json.loads(m) for m in raw_list]


async def _append_to_history(session_id: str, role: str, content: str) -> None:
    """Append one message and refresh the 2-hour TTL."""
    r = await _get_redis()
    key = _history_key(session_id)
    await r.rpush(key, json.dumps({"role": role, "content": content}))
    await r.expire(key, HISTORY_TTL)


# ═════════════════════════════════════════════════════════════════════════════
# 1.  stream_triage_message  — Sonnet streaming with inline JSON detection
# ═════════════════════════════════════════════════════════════════════════════


async def stream_triage_message(
    session_id: str,
    patient_message: str,
    language: str = "en",
    voice_distress_score: float = 0.0,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Append *patient_message* → send full history to Sonnet → yield SSE tokens.

    After the stream completes the full response is checked for JSON.  If the
    response **is** valid JSON containing ``urgency_score`` the generator emits
    a sentinel line ``__SCORE_JSON__:<json>`` so the route layer can detect
    scoring completion and trigger downstream actions.

    On API failure after retries, emits ``__FALLBACK_JSON__:<json>`` with a
    cached demo response from Supabase.
    """
    # ── Persist patient message in Redis ─────────────────────────────────
    await _append_to_history(session_id, "user", patient_message)

    # ── Build message list ───────────────────────────────────────────────
    if conversation_history is None:
        conversation_history = await _load_history(session_id)
    else:
        # Ensure the new message is included
        last = conversation_history[-1] if conversation_history else {}
        if last.get("content") != patient_message:
            conversation_history.append({"role": "user", "content": patient_message})

    system = TRIAGE_SYSTEM_PROMPT.format(
        language=language,
        voice_distress_score=voice_distress_score,
    )

    client = _get_client()
    chunks: list[str] = []

    try:
        async with client.messages.stream(
            model=SONNET_MODEL,
            max_tokens=500,
            system=system,
            messages=conversation_history,
        ) as stream:
            async for text in stream.text_stream:
                chunks.append(text)
                yield text
    except _RETRYABLE as exc:
        logger.error("Triage stream failed: %s — serving cached fallback", exc)
        cached = await get_cached_demo_response()
        yield f"__FALLBACK_JSON__:{json.dumps(cached)}"
        return

    # ── Post-stream: persist assistant reply ─────────────────────────────
    full_response = "".join(chunks)
    await _append_to_history(session_id, "assistant", full_response)

    # ── Check for JSON scoring result ────────────────────────────────────
    stripped = full_response.strip()
    # Strip markdown fences if model wraps them anyway
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
    if stripped.endswith("```"):
        stripped = stripped.rsplit("```", 1)[0].strip()

    try:
        score_data = json.loads(stripped)
        if "urgency_score" in score_data and "urgency_level" in score_data:
            yield f"__SCORE_JSON__:{json.dumps(score_data)}"
    except (json.JSONDecodeError, ValueError):
        pass  # Normal conversational response


# ═════════════════════════════════════════════════════════════════════════════
# 2.  generate_brief  — Sonnet single-call, structured JSON output
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
    Generate a pre-visit doctor brief.

    Returns ``{brief_summary, priority_flags, context_from_history,
    suggested_opening_questions, watch_for}``.
    """
    client = _get_client()

    user_content = (
        "Generate a pre-visit brief for this patient.\n\n"
        f"Patient: {patient_name}, {age or 'Unknown'}y, {gender or 'Unknown'}\n"
        f"History notes: {history_notes or 'None available'}\n"
        f"Voice distress score: {voice_distress_score}/10\n\n"
        f"Triage assessment:\n{json.dumps(urgency_json, indent=2)}\n\n"
        "Generate the brief now."
    )

    message = await _retry_api_call(
        lambda: client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            system=BRIEF_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0].strip()

    try:
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


# ═════════════════════════════════════════════════════════════════════════════
# 3.  rerank_queue  — Haiku (fast + cheap)
# ═════════════════════════════════════════════════════════════════════════════


async def rerank_queue(queue_items: list[dict]) -> list[dict]:
    """
    Ask Haiku to optimally order patients by urgency, wait time, and distress.

    Returns *queue_items* reordered.  On failure returns the original list.
    """
    if len(queue_items) <= 1:
        return queue_items

    client = _get_client()
    queue_json = json.dumps(queue_items, indent=2)

    try:
        message = await _retry_api_call(
            lambda: client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": RERANK_PROMPT_TEMPLATE.format(queue_json=queue_json),
                }],
            )
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()

        result = json.loads(raw)
        ordered_ids = result.get("ordered_ids", [])

        # Rebuild in recommended order
        id_map = {
            (item.get("patient_id") or item.get("id")): item
            for item in queue_items
        }
        reordered = []
        for pid in ordered_ids:
            pid_str = str(pid)
            if pid_str in id_map:
                reordered.append(id_map.pop(pid_str))
        # Append any items Haiku omitted (safety net)
        reordered.extend(id_map.values())
        return reordered

    except Exception as exc:
        logger.warning("Haiku rerank failed (%s) — keeping original order", exc)
        return queue_items


# ═════════════════════════════════════════════════════════════════════════════
# 4.  get_cached_demo_response  — Supabase fallback
# ═════════════════════════════════════════════════════════════════════════════


async def get_cached_demo_response(scenario: str = "aarav_sharma") -> dict:
    """
    Fetch pre-cached triage output from Supabase ``demo_cache`` table.

    Used when the Anthropic API is unavailable.  Returns the same structure
    as a real triage scoring output.
    """
    try:
        from services.supabase_service import _get_client as _get_sb
        sb = _get_sb()
        result = (
            sb.table("demo_cache")
            .select("response_json")
            .eq("scenario", scenario)
            .single()
            .execute()
        )
        if result.data and "response_json" in result.data:
            return result.data["response_json"]
    except Exception as exc:
        logger.warning("demo_cache lookup failed: %s", exc)

    # Hard-coded last-resort fallback
    return {
        "urgency_score": 72,
        "urgency_level": "HIGH",
        "reasoning_trace": [
            "Patient reports severe abdominal pain (8/10)",
            "Onset: 3 hours ago, sudden",
            "Associated nausea and fever (38.5°C)",
            "No prior history of similar episodes",
            "Voice distress analysis suggests significant discomfort",
        ],
        "recommended_action": "Prioritise for physician assessment within 15 minutes",
        "estimated_wait_minutes": 15,
        "red_flags": ["Acute abdomen", "Fever with pain"],
        "chief_complaint_refined": "Acute abdominal pain with fever and nausea",
    }


# ═════════════════════════════════════════════════════════════════════════════
# Legacy compatibility shims
# ═════════════════════════════════════════════════════════════════════════════
# These preserve the original function signatures so existing routes continue
# to work without immediate refactoring.


async def stream_triage_response(
    conversation_history: list[dict],
    language: str = "en",
) -> AsyncGenerator[str, None]:
    """Legacy streaming — wraps Sonnet without Redis history management."""
    client = _get_client()
    system = TRIAGE_SYSTEM_PROMPT.format(language=language, voice_distress_score=0)

    try:
        async with client.messages.stream(
            model=SONNET_MODEL,
            max_tokens=500,
            system=system,
            messages=conversation_history,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except _RETRYABLE as exc:
        logger.error("Legacy stream failed: %s", exc)
        cached = await get_cached_demo_response()
        yield json.dumps(cached)


async def get_triage_response(
    conversation_history: list[dict],
    language: str = "en",
) -> str:
    """Non-streaming legacy version — returns the full response at once."""
    client = _get_client()
    system = TRIAGE_SYSTEM_PROMPT.format(language=language, voice_distress_score=0)

    try:
        message = await _retry_api_call(
            lambda: client.messages.create(
                model=SONNET_MODEL,
                max_tokens=500,
                system=system,
                messages=conversation_history,
            )
        )
        return message.content[0].text
    except Exception:
        cached = await get_cached_demo_response()
        return json.dumps(cached)


async def score_triage(conversation_history: list[dict]) -> dict:
    """Legacy scoring — separate call to Sonnet for final urgency score."""
    client = _get_client()
    scoring_messages = [
        {
            "role": "user",
            "content": (
                "Here is the full triage conversation:\n\n"
                + "\n".join(
                    f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
                    for m in conversation_history
                )
                + "\n\nPlease score this triage session."
            ),
        }
    ]

    try:
        message = await _retry_api_call(
            lambda: client.messages.create(
                model=SONNET_MODEL,
                max_tokens=1024,
                system=SCORING_SYSTEM_PROMPT,
                messages=scoring_messages,
            )
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception:
        logger.exception("score_triage failed — returning cached fallback")
        return await get_cached_demo_response()
