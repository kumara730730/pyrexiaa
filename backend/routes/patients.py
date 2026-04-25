"""
Patient routes — register and look up patients.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from models.patient import (
    PatientCreate,
    PatientResponse,
    PatientUpdate,
    KioskPatientCreate,
    KioskPatientResponse,
)
from services import supabase_service

router = APIRouter(prefix="/patients", tags=["Patients"])


# ── POST /patients/register ──────────────────────────────────────────────────


@router.post("/register", response_model=PatientResponse, status_code=201)
async def register_patient(req: PatientCreate):
    """Register a new patient at a clinic."""
    data = req.model_dump()
    patient = await supabase_service.create_patient(data)
    return patient


# ── POST /patients/kiosk-register ────────────────────────────────────────────

@router.post("/kiosk-register", response_model=KioskPatientResponse, status_code=201)
async def register_kiosk_patient(req: KioskPatientCreate):
    """Register a new patient from the kiosk."""
    data = req.model_dump()
    patient = await supabase_service.create_patient(data)
    return patient


# ── GET /patients/{id} ────────────────────────────────────────────────────────


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: UUID):
    """Retrieve a patient record by ID."""
    patient = await supabase_service.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


# ── PATCH /patients/{id} ──────────────────────────────────────────────────────


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(patient_id: UUID, req: PatientUpdate):
    """Partial update of patient details."""
    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    patient = await supabase_service.update_patient(patient_id, update_data)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient
