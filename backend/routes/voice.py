"""
Voice processing route — accepts transcribed text with a distress score.

The distress_score (0.0-1.0) is combined with hard-rule checks to decide
whether to short-circuit triage.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.triage import UrgencyLevel
from services import claude_service, supabase_service, queue_service
from services.realtime_service import broadcast_queue_update
from utils.hard_rules import check_hard_rules

router = APIRouter(prefix="/voice", tags=["Voice"])


# ── Models ────────────────────────────────────────────────────────────────────


class VoiceProcessRequest(BaseModel):
    """Payload from the voice transcription frontend."""

    patient_id: UUID
    session_id: UUID
    clinic_id: str
    text: str = Field(..., min_length=1, max_length=5000)
    distress_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Vocal distress indicator from the speech model (0=calm, 1=extreme)",
    )
    language: Optional[str] = Field("en", max_length=10)


class VoiceProcessResponse(BaseModel):
    hard_rule_triggered: bool = False
    distress_escalated: bool = False
    urgency_score: Optional[int] = None
    urgency_level: Optional[str] = None
    reasoning_trace: list[str] = Field(default_factory=list)
    assistant_response: Optional[str] = None


# ── Constants ─────────────────────────────────────────────────────────────────

DISTRESS_ESCALATION_THRESHOLD = 0.85  # ≥ 0.85 → treat as HIGH urgency


# ── POST /voice/process ──────────────────────────────────────────────────────


@router.post("/process", response_model=VoiceProcessResponse)
async def process_voice(req: VoiceProcessRequest):
    """
    Process transcribed voice input.

    1. Hard-rule check on the text.
    2. If distress_score ≥ 0.85 and no hard rule: escalate to HIGH.
    3. Otherwise, feed into the normal triage conversation.
    """
    # ── 1. Hard-rule gate ─────────────────────────────────────────────────
    hr = check_hard_rules(req.text)
    if hr.triggered:
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
            chief_complaint=req.text,
        )
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

        return VoiceProcessResponse(
            hard_rule_triggered=True,
            urgency_score=hr.urgency_score,
            urgency_level=UrgencyLevel.CRITICAL.value,
            reasoning_trace=hr.reasoning_trace,
        )

    # ── 2. Distress score escalation ──────────────────────────────────────
    if req.distress_score >= DISTRESS_ESCALATION_THRESHOLD:
        reasoning = [
            f"DISTRESS-ESCALATION: Voice distress score {req.distress_score:.2f} "
            f"exceeds threshold {DISTRESS_ESCALATION_THRESHOLD}",
        ]
        urgency_score = max(75, int(req.distress_score * 100))

        await supabase_service.save_triage_score(
            session_id=req.session_id,
            urgency_score=urgency_score,
            urgency_level="HIGH",
            reasoning_trace=reasoning,
            recommended_action="Prioritise — vocal distress detected",
        )
        await queue_service.enqueue_patient(
            clinic_id=req.clinic_id,
            patient_id=req.patient_id,
            urgency_score=urgency_score,
            urgency_level=UrgencyLevel.HIGH,
            chief_complaint=req.text,
        )
        queue = await queue_service.get_queue(req.clinic_id)
        await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

        return VoiceProcessResponse(
            distress_escalated=True,
            urgency_score=urgency_score,
            urgency_level=UrgencyLevel.HIGH.value,
            reasoning_trace=reasoning,
        )

    # ── 3. Normal flow: append to conversation and get Claude response ────
    session = await supabase_service.get_triage_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Triage session not found")

    history: list[dict] = session.get("conversation_history", [])
    history.append({"role": "user", "content": req.text})

    await supabase_service.append_message(req.session_id, "user", req.text)

    response_text = await claude_service.get_triage_response(
        history, language=req.language or "en"
    )

    await supabase_service.append_message(
        req.session_id, "assistant", response_text
    )

    return VoiceProcessResponse(assistant_response=response_text)
