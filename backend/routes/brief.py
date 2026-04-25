"""
Clinical brief routes — generate and retrieve physician handoff briefs.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import claude_service, supabase_service

router = APIRouter(prefix="/brief", tags=["Brief"])


# ── Request / Response models ─────────────────────────────────────────────────


class BriefGenerateRequest(BaseModel):
    patient_id: UUID
    session_id: UUID


class BriefResponse(BaseModel):
    patient_id: UUID
    session_id: UUID | None = None
    brief_text: str
    created_at: str | None = None


# ── POST /brief/generate ─────────────────────────────────────────────────────


@router.post("/generate", response_model=BriefResponse)
async def generate_brief(req: BriefGenerateRequest):
    """
    Generate a clinical handoff brief using Haiku from conversation + score.
    """
    session = await supabase_service.get_triage_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Triage session not found")

    history = session.get("conversation_history", [])
    scoring_data = {
        "urgency_score": session.get("urgency_score"),
        "urgency_level": session.get("urgency_level"),
        "reasoning_trace": session.get("reasoning_trace"),
        "recommended_action": session.get("recommended_action"),
    }

    brief_text = await claude_service.generate_brief(history, scoring_data)

    saved = await supabase_service.save_brief(
        patient_id=req.patient_id,
        session_id=req.session_id,
        brief_text=brief_text,
    )

    return BriefResponse(
        patient_id=req.patient_id,
        session_id=req.session_id,
        brief_text=brief_text,
        created_at=saved.get("created_at"),
    )


# ── GET /brief/{patient_id} ──────────────────────────────────────────────────


@router.get("/{patient_id}", response_model=BriefResponse)
async def get_brief(patient_id: UUID):
    """Retrieve the most recent brief for a patient."""
    brief = await supabase_service.get_brief_by_patient(patient_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="No brief found for this patient")

    return BriefResponse(
        patient_id=brief["patient_id"],
        session_id=brief.get("session_id"),
        brief_text=brief["brief_text"],
        created_at=brief.get("created_at"),
    )
