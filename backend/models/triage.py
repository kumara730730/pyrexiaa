"""Triage Pydantic models."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UrgencyLevel(str, Enum):
    """Urgency classification levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    NON_URGENT = "NON_URGENT"


# ── Triage Start ──────────────────────────────────────────────────────────────

class TriageStartRequest(BaseModel):
    """Begin a new triage session."""

    patient_id: UUID
    clinic_id: str
    chief_complaint: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field("en", max_length=10)


class TriageStartResponse(BaseModel):
    """Response after starting triage — may short-circuit on hard-rule match."""

    session_id: UUID
    hard_rule_triggered: bool = False
    urgency_score: Optional[int] = None
    urgency_level: Optional[UrgencyLevel] = None
    reasoning_trace: list[str] = Field(default_factory=list)
    initial_question: Optional[str] = None


# ── Triage Message (SSE streaming handled at the route level) ─────────────────

class TriageMessageRequest(BaseModel):
    """Patient replies during a triage conversation."""

    session_id: UUID
    patient_id: UUID
    clinic_id: str
    message: str = Field(..., min_length=1, max_length=5000)
    language: Optional[str] = Field("en", max_length=10)
    voice_distress_score: Optional[float] = Field(
        None,
        ge=0,
        le=10,
        description="Voice distress score (0-10) computed from speech analysis on the frontend",
    )


# ── Triage Score ──────────────────────────────────────────────────────────────

class TriageScoreRequest(BaseModel):
    """Request final scoring for a triage session."""

    session_id: UUID
    patient_id: UUID
    clinic_id: str


class TriageScoreResponse(BaseModel):
    """Final triage scoring result."""

    session_id: UUID
    patient_id: UUID
    urgency_score: int = Field(..., ge=0, le=100)
    urgency_level: UrgencyLevel
    reasoning_trace: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    estimated_wait_minutes: Optional[int] = None
