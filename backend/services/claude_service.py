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
You are a clinical documentation AI for PriorIQ.

Generate a concise pre-visit brief for the attending doctor.

CONTEXT: The doctor has 20–30 seconds to read this brief before entering the exam room.
Write for a doctor, not a patient. Use clinical shorthand where appropriate.
Prioritise what requires immediate action. Eliminate all filler.

PATIENT DATA:
Name: {name} | Age: {age} | Gender: {gender}
Medical History: {history_notes}
Voice Distress Level: {voice_distress_score}/10

TRIAGE ASSESSMENT:
{urgency_json}

OUTPUT ONLY this JSON — no prose, no markdown formatting:

{{
  "brief_summary": "2–3 sentences. Chief complaint, acuity, most actionable context. Clinical register.",
  "priority_flags": ["Specific flag 1", "Specific flag 2", "Specific flag 3"],
  "context_from_history": "Relevant comorbidities or recent history in one sentence. Write 'No significant history documented' if none.",
  "suggested_opening_questions": ["Direct question 1?", "Direct question 2?", "Direct question 3?"],
  "watch_for": "ONE thing to assess immediately upon entering the room. One sentence, maximum urgency."
}}

If urgency_level is CRITICAL: watch_for must start with "IMMEDIATE:" and describe the most time-critical action."""

RERANK_PROMPT_TEMPLATE = """\
You are a medical queue optimisation algorithm.

Given the current waiting patients, return the optimal order they should be seen.

ORDERING RULES (apply in strict priority):
1. urgency_level CRITICAL → always positions 1-N before any HIGH patient
2. Within same urgency_level: longer wait_time_minutes → higher priority (fairness)
3. If voice_distress_score > 7: bump this patient up by 1 position within their level
4. Never reorder a lower-level patient above a CRITICAL patient under any circumstances

CURRENT QUEUE:
{queue_json}

Return ONLY this JSON. No explanation. No other text.
{{"ordered_ids": ["id1", "id2", "id3"]}}"""

# ── Urgency-level rank (lower = higher clinical priority) ────────────────────

URGENCY_RANK: dict[str, int] = {
    "CRITICAL":   0,
    "HIGH":       1,
    "MODERATE":   2,
    "LOW":        3,
    "NON_URGENT": 4,
}


def _deterministic_rerank(queue_items: list[dict]) -> list[dict]:
    """
    Deterministic queue optimiser — zero LLM calls, O(n log n).

    Rules (strict priority):
      1. CRITICAL patients always occupy positions 1‑N.
      2. Within the same urgency_level, longer wait_minutes → higher priority.
      3. voice_distress_score > 7 bumps a patient up by ONE position *within*
         their urgency level (swap with the neighbour above).
      4. A lower-level patient is NEVER reordered above a CRITICAL patient.
    """
    from itertools import groupby

    # ── 1. Bucket by urgency level ───────────────────────────────────────
    for item in queue_items:
        item.setdefault("wait_minutes", 0.0)
        item.setdefault("voice_distress_score", 0.0)
        level = str(item.get("urgency_level", "LOW")).upper()
        item["_rank"] = URGENCY_RANK.get(level, 3)

    # Sort first by rank (CRITICAL→…→NON_URGENT), then by wait desc
    queue_items.sort(key=lambda x: (x["_rank"], -float(x["wait_minutes"])))

    # ── 2. Within each level, apply voice-distress bump ──────────────────
    #    Group contiguously by rank, bump high-distress patients up by 1.
    result: list[dict] = []
    for _rank, group in groupby(queue_items, key=lambda x: x["_rank"]):
        bucket = list(group)
        # Walk backward so earlier swaps don't shift later indices
        for i in range(1, len(bucket)):
            if bucket[i].get("voice_distress_score", 0) > 7:
                # Only bump if the neighbour above does NOT also exceed 7
                if bucket[i - 1].get("voice_distress_score", 0) <= 7:
                    bucket[i - 1], bucket[i] = bucket[i], bucket[i - 1]
        result.extend(bucket)

    # ── 3. Clean up temp key ─────────────────────────────────────────────
    for item in result:
        item.pop("_rank", None)

    return result


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

    # Format the system prompt with patient-specific data
    system = BRIEF_SYSTEM_PROMPT.format(
        name=patient_name,
        age=f"{age}y" if age else "Unknown",
        gender=gender or "Unknown",
        history_notes=history_notes or "None documented",
        voice_distress_score=voice_distress_score,
        urgency_json=json.dumps(urgency_json, indent=2),
    )

    message = await _retry_api_call(
        lambda: client.messages.create(
            model=SONNET_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": "Generate the pre-visit brief now."}],
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
            "context_from_history": history_notes or "No significant history documented",
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

    client = _get_client()
    
    # Prepare a minimal JSON for Haiku to save tokens
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
            str(item.get("patient_id") or item.get("id")): item
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
        logger.warning("Haiku rerank failed (%s) — using deterministic fallback", exc)
        return _deterministic_rerank(queue_items)


# ═════════════════════════════════════════════════════════════════════════════
# 4.  get_cached_demo_response  — Supabase fallback
# ═════════════════════════════════════════════════════════════════════════════


async def get_cached_demo_response(scenario: str = "aarav_sharma_triage") -> dict:
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
        "urgency_score": 94,
        "urgency_level": "CRITICAL",
        "reasoning_trace": [
            "ACS pattern: chest pressure + left arm radiation",
            "Diaphoresis with sudden onset — high-risk presentation",
            "Symptom onset during sleep/early morning — peak cardiac event window",
            "Jaw radiation = triple-vessel pattern consistent with STEMI/NSTEMI",
            "Diabetic patient: atypical presentation risk — real urgency likely higher than reported",
            "15 pack-year smoking history compounds atherogenic risk",
        ],
        "presenting_complaint": "52M presenting with sudden-onset chest tightness, left arm heaviness, and jaw radiation since 07:00. Associated diaphoresis.",
        "red_flags": [
            "ACS pattern — chest + arm + jaw radiation",
            "Diaphoresis reported",
            "Sudden onset in early morning — peak STEMI window",
            "Diabetic with masked pain threshold",
        ],
        "suggested_doctor_questions": [
            "Is the chest discomfort constant or does it come and go?",
            "Rate your pain from 1 to 10 right now.",
            "Have you taken any aspirin or GTN before coming in?",
        ],
        "recommended_doctor_specialty": "Cardiology",
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
