"""
Queue routes — view, reorder, and trigger emergency overrides.

Every mutation broadcasts the updated queue via Supabase Realtime.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.queue import (
    QueueResponse,
    ReorderRequest,
    EmergencyOverrideRequest,
    EmergencyOverrideResponse,
)
from services import queue_service
from services.realtime_service import broadcast_queue_update

router = APIRouter(prefix="/queue", tags=["Queue"])


# ── GET /queue/current?clinic_id=xxx ──────────────────────────────────────────


@router.get("/current", response_model=QueueResponse)
async def get_current_queue(clinic_id: str):
    """Return the full ordered queue for a clinic."""
    return await queue_service.get_queue(clinic_id)


# ── POST /queue/reorder ──────────────────────────────────────────────────────


@router.post("/reorder", response_model=QueueResponse)
async def reorder_queue(req: ReorderRequest):
    """
    Staff manually adjusts a patient's urgency score.

    Broadcasts the updated queue after mutation.
    """
    old_score = await queue_service.reorder_patient(
        clinic_id=req.clinic_id,
        patient_id=req.patient_id,
        new_urgency_score=req.new_urgency_score,
    )
    if old_score is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found in queue",
        )

    queue = await queue_service.get_queue(req.clinic_id)
    await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))
    return queue


# ── POST /queue/call/{patient_id} ────────────────────────────────────────────


@router.post("/call/{patient_id}")
async def call_patient(patient_id: UUID, clinic_id: str):
    """
    Mark a patient as called — removes from queue and broadcasts update.
    """
    removed = await queue_service.remove_patient(clinic_id, patient_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Patient not in queue")

    queue = await queue_service.get_queue(clinic_id)
    await broadcast_queue_update(clinic_id, queue.model_dump(mode="json"))
    return {"status": "called", "patient_id": str(patient_id)}


# ── POST /queue/emergency ────────────────────────────────────────────────────


@router.post("/emergency", response_model=EmergencyOverrideResponse)
async def emergency_override(req: EmergencyOverrideRequest):
    """
    Force a patient to position 1 with score 100.

    Broadcasts immediately.
    """
    old_score = await queue_service.emergency_override(
        clinic_id=req.clinic_id,
        patient_id=req.patient_id,
    )

    queue = await queue_service.get_queue(req.clinic_id)
    await broadcast_queue_update(req.clinic_id, queue.model_dump(mode="json"))

    return EmergencyOverrideResponse(
        patient_id=req.patient_id,
        clinic_id=req.clinic_id,
        previous_score=old_score,
        new_score=100,
        position=1,
        reason=req.reason,
    )


# ── GET /queue/assignment/{patient_id} ───────────────────────────────────────


@router.get("/assignment/{patient_id}")
async def get_patient_assignment(patient_id: UUID, clinic_id: str):
    """
    Retrieve a patient's queue assignment — position, estimated wait, and
    assigned doctor info.

    This is a convenience endpoint used by the kiosk DoctorCard component.
    """
    queue = await queue_service.get_queue(clinic_id)

    # Find the patient in the queue
    entry = None
    for e in queue.entries:
        if str(e.patient_id) == str(patient_id):
            entry = e
            break

    if entry is None:
        raise HTTPException(status_code=404, detail="Patient not found in queue")

    # Map urgency level / specialty to a demo doctor assignment
    # In production this would come from a doctor scheduling service
    DOCTOR_MAP = {
        "CRITICAL": {
            "doctor_name": "Dr. Priya Nair",
            "specialty": "Emergency Medicine",
            "room_number": "ER-01",
        },
        "HIGH": {
            "doctor_name": "Dr. Rajesh Menon",
            "specialty": "Cardiology",
            "room_number": "C-04",
        },
        "MODERATE": {
            "doctor_name": "Dr. Ananya Sharma",
            "specialty": "General Practice",
            "room_number": "G-12",
        },
        "LOW": {
            "doctor_name": "Dr. Ananya Sharma",
            "specialty": "General Practice",
            "room_number": "G-12",
        },
    }

    doc = DOCTOR_MAP.get(entry.urgency_level.value, DOCTOR_MAP["MODERATE"])

    return {
        "doctor_name": doc["doctor_name"],
        "doctor_photo": "",
        "specialty": doc["specialty"],
        "room_number": doc["room_number"],
        "estimated_wait_minutes": entry.position * 5,
        "queue_position": entry.position,
    }
