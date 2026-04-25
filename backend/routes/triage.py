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
from services import claude_service, supabase_service, queue_service, background_tasks
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
    patient = None
    if req.patient_id:
        patient = await supabase_service.get_patient(req.patient_id)

    # ── SSE streaming generator ───────────────────────────────────────────
    async def _event_generator():
        full_response: list[str] = []
        
        # Ensure session_id is a string for the service
        sid = str(req.session_id)

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
                await background_tasks.handle_scoring_complete(
                    session_id=req.session_id,
                    patient_id=req.patient_id,
                    clinic_id=req.clinic_id,
                    score_data=score_data,
                    voice_distress_score=req.voice_distress_score,
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

                await background_tasks.handle_scoring_complete(
                    session_id=req.session_id,
                    patient_id=req.patient_id,
                    clinic_id=req.clinic_id,
                    score_data=score_data,
                    voice_distress_score=req.voice_distress_score,
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

    # Use background tasks for all persistence and enqueuing
    await background_tasks.handle_scoring_complete(
        session_id=req.session_id,
        patient_id=req.patient_id,
        clinic_id=req.clinic_id,
        score_data=score_data,
    )

    return TriageScoreResponse(
        session_id=req.session_id,
        patient_id=req.patient_id,
        urgency_score=int(score_data.get("urgency_score", 50)),
        urgency_level=UrgencyLevel(score_data.get("urgency_level", "MODERATE")),
        reasoning_trace=score_data.get("reasoning_trace", []),
        recommended_action=score_data.get("recommended_action"),
        estimated_wait_minutes=score_data.get("estimated_wait_minutes"),
    )
