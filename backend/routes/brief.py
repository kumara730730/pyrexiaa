"""
Clinical brief routes — generate and retrieve physician handoff briefs.

The doctor dashboard fetches the brief when a patient is clicked in the queue.
If the brief is not yet ready (async generation still in progress), a 202
response is returned so the frontend can show a skeleton loader and retry.
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from services import claude_service, supabase_service, pdf_service

router = APIRouter(prefix="/brief", tags=["Brief"])


# ── Request / Response models ─────────────────────────────────────────────────


class BriefGenerateRequest(BaseModel):
    patient_id: UUID
    session_id: UUID


class BriefResponse(BaseModel):
    patient_id: str
    session_id: str | None = None
    brief_text: str
    created_at: str | None = None


# ── POST /brief/generate ─────────────────────────────────────────────────────


@router.post("/generate", response_model=BriefResponse)
async def generate_brief(req: BriefGenerateRequest):
    """
    Generate a clinical handoff brief using Claude from conversation + score.
    """
    session = await supabase_service.get_triage_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Triage session not found")

    patient = await supabase_service.get_patient(req.patient_id)

    history = session.get("conversation_history", [])
    history_notes = "\n".join(
        f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
        for m in history
    )

    scoring_data = {
        "urgency_score": session.get("urgency_score"),
        "urgency_level": session.get("urgency_level"),
        "reasoning_trace": session.get("reasoning_trace"),
        "recommended_action": session.get("recommended_action"),
    }

    brief_dict = await claude_service.generate_brief(
        patient_name=patient.get("name", "Unknown") if patient else "Unknown",
        age=patient.get("age") if patient else None,
        gender=patient.get("gender") if patient else None,
        history_notes=history_notes,
        urgency_json=scoring_data,
        voice_distress_score=float(patient.get("voice_distress_score", 0)) if patient else 0.0,
    )

    brief_text = json.dumps(brief_dict)

    saved = await supabase_service.save_brief(
        patient_id=req.patient_id,
        session_id=req.session_id,
        brief_text=brief_text,
    )

    return BriefResponse(
        patient_id=str(req.patient_id),
        session_id=str(req.session_id),
        brief_text=brief_text,
        created_at=saved.get("created_at"),
    )


# ── GET /brief/{patient_id} ──────────────────────────────────────────────────


@router.get("/{patient_id}")
async def get_brief(patient_id: UUID):
    """
    Retrieve the most recent brief for a patient.

    Returns 200 with the brief if available, or 202 with a
    ``{"status": "pending"}`` body so the frontend knows to retry
    with a skeleton loader.
    """
    brief = await supabase_service.get_brief_by_patient(patient_id)
    if brief is None:
        return JSONResponse(
            status_code=202,
            content={"status": "pending", "message": "Brief is being generated"},
        )

    return BriefResponse(
        patient_id=brief["patient_id"],
        session_id=brief.get("session_id"),
        brief_text=brief["brief_text"],
        created_at=brief.get("created_at"),
    )


# ── GET /brief/triage/{session_id} ───────────────────────────────────────────


@router.get("/triage/{session_id}")
async def get_brief_by_triage(session_id: UUID):
    """
    Retrieve the brief for a specific triage session.

    Returns 202 if the brief hasn't been generated yet.
    """
    brief = await supabase_service.get_brief_by_triage(session_id)
    if brief is None:
        return JSONResponse(
            status_code=202,
            content={"status": "pending", "message": "Brief is being generated"},
        )

    return BriefResponse(
        patient_id=brief["patient_id"],
        session_id=brief.get("session_id"),
        brief_text=brief["brief_text"],
        created_at=brief.get("created_at"),
    )


# ── GET /brief/{patient_id}/pdf ──────────────────────────────────────────────


@router.get("/{patient_id}/pdf")
async def get_brief_pdf(patient_id: UUID):
    """
    Generate and return a PDF pre-visit brief for a patient.
    """
    brief = await supabase_service.get_brief_by_patient(patient_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Brief not found or still generating")
        
    patient = await supabase_service.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    session_id = brief.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Brief is missing session context")
        
    session = await supabase_service.get_triage_session(UUID(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Triage session not found")
        
    pdf_buffer = pdf_service.generate_brief_pdf(patient, session, brief)
    
    # Format filename with patient name and date
    patient_name = patient.get("name", "Unknown").replace(" ", "_").lower()
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"brief_{patient_name}_{date_str}.pdf"
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
