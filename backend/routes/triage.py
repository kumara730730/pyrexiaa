"""
Triage routes — start a session, stream messages, and request final scoring.

The ``/triage/message`` endpoint uses Redis-backed conversation history and
SSE streaming.  When Claude returns a JSON scoring result the route
automatically persists the score, fires the Brief Builder (async, non-blocking),
pushes to the Redis queue, and broadcasts via Supabase Realtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from models.triage import (
    TriageStartRequest,
    TriageStartResponse,
    TriageMessageRequest,
    TriageScoreRequest,
    TriageScoreResponse,
    UrgencyLevel,
)
from services import claude_service, supabase_service, queue_service
from services.realtime_service import broadcast_queue_update, broadcast_emergency
from utils.hard_rules import check_hard_rules

router = APIRouter(prefix="/triage", tags=["Triage"])
logger = logging.getLogger("triage")


# ── POST /triage/start ────────────────────────────────────────────────────────


@router.post("/start", response_model=TriageStartResponse)
async def start_triage(req: TriageStartRequest):
    """
    Begin a new triage session.

    1. Run hard-rule check on the chief complaint.
    2. If critical → short-circuit, enqueue immediately, broadcast.
    3. Otherwise → create session, ask the first follow-up question via Claude.
    """
    # ── Hard-rule gate ────────────────────────────────────────────────────
    hr = check_hard_rules(req.chief_complaint)

    # Create DB session regardless
    session = await supabase_service.create_triage_session(
        patient_id=req.patient_id,
        clinic_id=req.clinic_id,
        chief_complaint=req.chief_complaint,
        language=req.language or "en",
    )
    session_id = UUID(session["id"])

    if hr.triggered:
        # Persist score
        await supabase_service.save_triage_score(
            session_id=session_id,
            urgency_score=hr.urgency_score,
            urgency_level=hr.urgency_level,
            reasoning_trace=hr.reasoning_trace,
            recommended_action="IMMEDIATE EMERGENCY ATTENTION REQUIRED",
        )
        # Emergency override — force position 0 in Redis queue
        await queue_service.emergency_override(
            clinic_id=req.clinic_id,
            patient_id=req.patient_id,
            chief_complaint=req.chief_complaint,
        )
        # Broadcast queue update + emergency alarm to all doctor screens
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))
        await broadcast_emergency(
            clinic_id=req.clinic_id,
            patient_id=str(req.patient_id),
            chief_complaint=req.chief_complaint,
            matched_keywords=hr.matched_keywords,
        )

        return TriageStartResponse(
            session_id=session_id,
            hard_rule_triggered=True,
            urgency_score=hr.urgency_score,
            urgency_level=UrgencyLevel.CRITICAL,
            reasoning_trace=hr.reasoning_trace,
        )

    # ── Normal flow: seed Redis history + ask first follow-up via Claude ──
    conversation_history = [
        {"role": "user", "content": f"Chief complaint: {req.chief_complaint}"}
    ]

    first_question = await claude_service.get_triage_response(
        conversation_history, language=req.language or "en"
    )

    # Persist in Supabase
    await supabase_service.append_message(session_id, "user", req.chief_complaint)
    await supabase_service.append_message(session_id, "assistant", first_question)

    # Seed Redis history for subsequent /triage/message calls
    await claude_service._append_to_history(str(session_id), "user", f"Chief complaint: {req.chief_complaint}")
    await claude_service._append_to_history(str(session_id), "assistant", first_question)

    return TriageStartResponse(
        session_id=session_id,
        hard_rule_triggered=False,
        initial_question=first_question,
    )


# ── POST /triage/message (SSE stream) ────────────────────────────────────────


@router.post("/message")
async def triage_message(req: TriageMessageRequest):
    """
    Continue the triage conversation — streams Claude's response via SSE.

    Flow:
    1. Hard-rule check on every patient message
    2. Append patient message to Redis history (done inside claude_service)
    3. Stream Sonnet response tokens as SSE events
    4. If response is JSON scoring → persist score, fire brief builder,
       enqueue patient, broadcast queue update
    """
    # ── Hard-rule gate on the new message ─────────────────────────────────
    hr = check_hard_rules(req.message)
    if hr.triggered:
        await supabase_service.save_triage_score(
            session_id=req.session_id,
            urgency_score=hr.urgency_score,
            urgency_level=hr.urgency_level,
            reasoning_trace=hr.reasoning_trace,
            recommended_action="IMMEDIATE EMERGENCY ATTENTION REQUIRED",
        )
        # Emergency override — force position 0 in Redis queue
        await queue_service.emergency_override(
            clinic_id=req.clinic_id,
            patient_id=req.patient_id,
            chief_complaint=req.message,
        )
        # Broadcast queue update + emergency alarm to all doctor screens
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))
        await broadcast_emergency(
            clinic_id=req.clinic_id,
            patient_id=str(req.patient_id),
            chief_complaint=req.message,
            matched_keywords=hr.matched_keywords,
        )

        return {
            "hard_rule_triggered": True,
            "urgency_score": hr.urgency_score,
            "urgency_level": UrgencyLevel.CRITICAL.value,
            "reasoning_trace": hr.reasoning_trace,
            "matched_keywords": hr.matched_keywords,
        }

    # ── Fetch patient data for potential brief generation ─────────────────
    patient = await supabase_service.get_patient(req.patient_id)

    # ── SSE streaming generator ───────────────────────────────────────────
    async def _event_generator():
        full_response: list[str] = []

        async for token in claude_service.stream_triage_message(
            session_id=str(req.session_id),
            patient_message=req.message,
            language=req.language or "en",
            voice_distress_score=(
                float(req.voice_distress_score * 10)
                if req.voice_distress_score is not None
                else (
                    float(patient.get("voice_distress_score", 0))
                    if patient else 0.0
                )
            ),
        ):
            # ── Sentinel: scoring complete ────────────────────────────
            if token.startswith("__SCORE_JSON__:"):
                score_json = token[len("__SCORE_JSON__:"):]
                score_data = json.loads(score_json)

                # Persist to Supabase & append to Supabase history
                await _handle_scoring_complete(
                    req=req,
                    score_data=score_data,
                    patient=patient,
                )

                yield {
                    "event": "score",
                    "data": score_json,
                }
                return

            # ── Sentinel: fallback response ───────────────────────────
            if token.startswith("__FALLBACK_JSON__:"):
                fallback_json = token[len("__FALLBACK_JSON__:"):]
                score_data = json.loads(fallback_json)

                await _handle_scoring_complete(
                    req=req,
                    score_data=score_data,
                    patient=patient,
                )

                yield {
                    "event": "score",
                    "data": fallback_json,
                }
                return

            # ── Normal token ──────────────────────────────────────────
            full_response.append(token)
            yield {"event": "token", "data": json.dumps({"token": token})}

        # Stream finished with no JSON detected — normal conversational reply
        complete_text = "".join(full_response)

        # Persist assistant response to Supabase (Redis already done in service)
        await supabase_service.append_message(
            req.session_id, "user", req.message
        )
        await supabase_service.append_message(
            req.session_id, "assistant", complete_text
        )

        yield {
            "event": "done",
            "data": json.dumps({"full_response": complete_text}),
        }

    return EventSourceResponse(_event_generator())


async def _handle_scoring_complete(
    req: TriageMessageRequest,
    score_data: dict,
    patient: dict | None,
) -> None:
    """
    After scoring is detected:
    1. Persist score to Supabase
    2. Enqueue patient in Redis sorted set
    3. Broadcast queue update via Supabase Realtime
    4. Fire brief builder (async, non-blocking)
    """
    urgency_score = int(score_data.get("urgency_score", 50))
    urgency_level = score_data.get("urgency_level", "MODERATE")
    reasoning_trace = score_data.get("reasoning_trace", [])
    recommended_action = score_data.get("recommended_action")
    estimated_wait = score_data.get("estimated_wait_minutes")

    # 1. Persist score
    await supabase_service.save_triage_score(
        session_id=req.session_id,
        urgency_score=urgency_score,
        urgency_level=urgency_level,
        reasoning_trace=reasoning_trace,
        recommended_action=recommended_action,
        estimated_wait_minutes=estimated_wait,
    )

    # 2. Enqueue
    await queue_service.enqueue_patient(
        clinic_id=req.clinic_id,
        patient_id=req.patient_id,
        urgency_score=urgency_score,
        urgency_level=UrgencyLevel(urgency_level),
        chief_complaint=score_data.get("chief_complaint_refined"),
    )

    # 3. Broadcast
    queue = await queue_service.get_queue(req.clinic_id)
    await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

    # 4. Fire brief builder — async, non-blocking
    asyncio.create_task(
        _build_brief_async(req, score_data, patient),
        name=f"brief-{req.session_id}",
    )


async def _build_brief_async(
    req: TriageMessageRequest,
    score_data: dict,
    patient: dict | None,
) -> None:
    """Generate and persist a clinical brief in the background."""
    try:
        patient_name = patient.get("name", "Unknown") if patient else "Unknown"
        age = patient.get("age") if patient else None
        gender = patient.get("gender") if patient else None

        # Voice distress score — prefer request value, fall back to patient record
        vds = (
            float(req.voice_distress_score)
            if req.voice_distress_score is not None
            else float(patient.get("voice_distress_score", 0) if patient else 0)
        )

        # Build history notes from Redis conversation
        history = await claude_service._load_history(str(req.session_id))
        history_notes = "\n".join(
            f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
            for m in history
        )

        brief = await claude_service.generate_brief(
            patient_name=patient_name,
            age=age,
            gender=gender,
            history_notes=history_notes,
            urgency_json=score_data,
            voice_distress_score=vds,
        )

        await supabase_service.save_brief(
            patient_id=req.patient_id,
            session_id=req.session_id,
            brief_text=json.dumps(brief),
        )
        logger.info("Brief generated for session %s", req.session_id)

    except Exception:
        logger.exception("Background brief generation failed for session %s", req.session_id)


# ── POST /triage/score ────────────────────────────────────────────────────────


@router.post("/score", response_model=TriageScoreResponse)
async def score_triage(req: TriageScoreRequest):
    """
    Request final urgency scoring for a triage session.

    After scoring, the patient is enqueued and a queue update is broadcast.
    """
    session = await supabase_service.get_triage_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Triage session not found")

    history = session.get("conversation_history", [])
    if not history:
        raise HTTPException(
            status_code=400, detail="No conversation to score"
        )

    # Ask Claude for the score
    score_data = await claude_service.score_triage(history)

    urgency_score = int(score_data.get("urgency_score", 50))
    urgency_level = UrgencyLevel(score_data.get("urgency_level", "MODERATE"))
    reasoning_trace = score_data.get("reasoning_trace", [])
    recommended_action = score_data.get("recommended_action")
    estimated_wait = score_data.get("estimated_wait_minutes")

    # Persist
    await supabase_service.save_triage_score(
        session_id=req.session_id,
        urgency_score=urgency_score,
        urgency_level=urgency_level.value,
        reasoning_trace=reasoning_trace,
        recommended_action=recommended_action,
        estimated_wait_minutes=estimated_wait,
    )

    # Enqueue
    await queue_service.enqueue_patient(
        clinic_id=req.clinic_id,
        patient_id=req.patient_id,
        urgency_score=urgency_score,
        urgency_level=urgency_level,
        chief_complaint=session.get("chief_complaint"),
    )

    # Broadcast
    queue = await queue_service.get_queue(req.clinic_id)
    await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

    return TriageScoreResponse(
        session_id=req.session_id,
        patient_id=req.patient_id,
        urgency_score=urgency_score,
        urgency_level=urgency_level,
        reasoning_trace=reasoning_trace,
        recommended_action=recommended_action,
        estimated_wait_minutes=estimated_wait,
    )
