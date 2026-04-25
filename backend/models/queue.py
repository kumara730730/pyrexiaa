"""Queue Pydantic models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .triage import UrgencyLevel


class QueueEntry(BaseModel):
    """Single entry in the clinic queue."""

    patient_id: UUID
    clinic_id: str
    urgency_score: int = Field(..., ge=0, le=100)
    urgency_level: UrgencyLevel
    chief_complaint: Optional[str] = None
    voice_distress_score: float = 0.0
    position: int = Field(..., ge=1, description="1-indexed position in queue")
    enqueued_at: datetime


class QueueResponse(BaseModel):
    """Full queue snapshot."""

    clinic_id: str
    entries: list[QueueEntry] = Field(default_factory=list)
    total: int = 0


class ReorderRequest(BaseModel):
    """Manual reorder by clinic staff."""

    clinic_id: str
    patient_id: UUID
    new_urgency_score: int = Field(..., ge=0, le=100)
    reason: Optional[str] = None


class EmergencyOverrideRequest(BaseModel):
    """Force a patient to position 1 with score 100."""

    clinic_id: str
    patient_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)


class EmergencyOverrideResponse(BaseModel):
    """Acknowledgement of emergency override."""

    patient_id: UUID
    clinic_id: str
    previous_score: Optional[int] = None
    new_score: int = 100
    position: int = 1
    reason: str
