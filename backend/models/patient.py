"""Patient Pydantic models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    """Payload to register a new patient."""

    first_name: str = Field(..., min_length=1, max_length=120)
    last_name: str = Field(..., min_length=1, max_length=120)
    date_of_birth: str = Field(..., description="ISO-8601 date string (YYYY-MM-DD)")
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    language: Optional[str] = Field("en", max_length=10, description="ISO 639-1 language code")
    clinic_id: str = Field(..., description="Clinic the patient is registering at")


class PatientUpdate(BaseModel):
    """Partial update payload."""

    first_name: Optional[str] = Field(None, min_length=1, max_length=120)
    last_name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    language: Optional[str] = Field(None, max_length=10)


class PatientResponse(BaseModel):
    """Patient record returned from the API."""

    id: UUID
    first_name: str
    last_name: str
    date_of_birth: str
    phone: Optional[str] = None
    email: Optional[str] = None
    language: str = "en"
    clinic_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
