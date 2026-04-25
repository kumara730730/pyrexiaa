"""
Triage routes — start a session, stream messages, and request final scoring.
"""

from __future__ import annotations

import json
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
from services.realtime_service import broadcast_queue_update
from utils.hard_rules import check_hard_rules

router = APIRouter(prefix="/triage", tags=["Triage"])


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
        # Enqueue at top
        await queue_service.enqueue_patient(
            clinic_id=req.clinic_id,
            patient_id=req.patient_id,
            urgency_score=hr.urgency_score,
            urgency_level=UrgencyLevel.CRITICAL,
            chief_complaint=req.chief_complaint,
        )
        # Broadcast
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

        return TriageStartResponse(
            session_id=session_id,
            hard_rule_triggered=True,
            urgency_score=hr.urgency_score,
            urgency_level=UrgencyLevel.CRITICAL,
            reasoning_trace=hr.reasoning_trace,
        )

    # ── Normal flow: ask first follow-up via Claude ───────────────────────
    conversation_history = [
        {"role": "user", "content": f"Chief complaint: {req.chief_complaint}"}
    ]

    first_question = await claude_service.get_triage_response(
        conversation_history, language=req.language or "en"
    )

    # Persist conversation
    await supabase_service.append_message(session_id, "user", req.chief_complaint)
    await supabase_service.append_message(session_id, "assistant", first_question)

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

    Hard rules are checked on every patient message.
    """
    # ── Hard-rule gate on the new message ─────────────────────────────────
    hr = check_hard_rules(req.message)
    if hr.triggered:
        # Short-circuit: persist, enqueue, broadcast, return JSON (not SSE)
        await supabase_service.save_triage_score(
            session_id=req.session_id,
            urgency_score=hr.urgency_score,
            urgency_level=hr.urgency_level,
            reasoning_trace=hr.reasoning_trace,
            recommended_action="IMMEDIATE EMERGENCY ATTENTION REQUIRED",
        )
        await queue_service.enqueue_patient(
            clinic_id=req.clinic_id,
            patient_id=req.patient_id,
            urgency_score=hr.urgency_score,
            urgency_level=UrgencyLevel.CRITICAL,
            chief_complaint=req.message,
        )
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

        return {
            "hard_rule_triggered": True,
            "urgency_score": hr.urgency_score,
            "urgency_level": UrgencyLevel.CRITICAL.value,
            "reasoning_trace": hr.reasoning_trace,
        }

    # ── Load conversation history from DB ─────────────────────────────────
    session = await supabase_service.get_triage_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Triage session not found")

    history: list[dict] = session.get("conversation_history", [])
    history.append({"role": "user", "content": req.message})

    # Persist the patient message
    await supabase_service.append_message(req.session_id, "user", req.message)

    # ── SSE streaming generator ───────────────────────────────────────────
    async def _event_generator():
        full_response: list[str] = []
        async for token in claude_service.stream_triage_response(
            history, language=req.language or "en"
        ):
            full_response.append(token)
            yield {"event": "token", "data": json.dumps({"token": token})}

        # Persist assistant response
        complete_text = "".join(full_response)
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
