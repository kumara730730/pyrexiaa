"""
Supabase persistence layer.

All database reads and writes go through this module so the rest of the app
stays storage-agnostic.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

# ── Supabase client singleton ─────────────────────────────────────────────────

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key, options=ClientOptions(auto_refresh_token=False))
    return _client


# ── Patients ──────────────────────────────────────────────────────────────────


async def create_patient(data: dict) -> dict:
    """Insert a new patient row and return the created record."""
    client = _get_client()
    patient_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": patient_id,
        **data,
        "created_at": now,
    }
    result = client.table("patients").insert(row).execute()
    return result.data[0] if result.data else row


async def get_patient(patient_id: UUID) -> Optional[dict]:
    """Fetch a patient by ID."""
    client = _get_client()
    result = (
        client.table("patients")
        .select("*")
        .eq("id", str(patient_id))
        .single()
        .execute()
    )
    return result.data


async def update_patient(patient_id: UUID, data: dict) -> Optional[dict]:
    """Partial update of a patient row."""
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("patients")
        .update({**data, "updated_at": now})
        .eq("id", str(patient_id))
        .execute()
    )
    return result.data[0] if result.data else None


# ── Triage sessions ──────────────────────────────────────────────────────────


async def create_triage_session(
    patient_id: UUID,
    clinic_id: str,
    chief_complaint: str,
    language: str = "en",
) -> dict:
    """Create a new triage session row."""
    client = _get_client()
    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Handle placeholder patient ID (dummy UUID)
    pid_str = str(patient_id)
    if pid_str == "00000000-0000-0000-0000-000000000000":
        pid_val = None
    else:
        pid_val = pid_str

    row = {
        "id": session_id,
        "patient_id": pid_val,
        "clinic_id": clinic_id,
        "chief_complaint": chief_complaint,
        "language": language,
        "status": "active",
        "conversation_history": [],
        "created_at": now,
    }
    result = client.table("triage_sessions").insert(row).execute()
    return result.data[0] if result.data else row


async def get_triage_session(session_id: UUID) -> Optional[dict]:
    """Fetch a triage session."""
    client = _get_client()
    result = (
        client.table("triage_sessions")
        .select("*")
        .eq("id", str(session_id))
        .single()
        .execute()
    )
    return result.data


async def append_message(
    session_id: UUID,
    role: str,
    content: str,
) -> None:
    """Append a message to the session's conversation_history JSON array."""
    client = _get_client()
    session = await get_triage_session(session_id)
    if session is None:
        return
    history: list[dict] = session.get("conversation_history", [])
    history.append({"role": role, "content": content})
    client.table("triage_sessions").update(
        {"conversation_history": history}
    ).eq("id", str(session_id)).execute()


async def save_triage_score(
    session_id: UUID,
    urgency_score: int,
    urgency_level: str,
    reasoning_trace: list[str],
    recommended_action: Optional[str] = None,
    estimated_wait_minutes: Optional[int] = None,
) -> None:
    """Persist the final triage scoring onto the session row."""
    client = _get_client()
    client.table("triage_sessions").update(
        {
            "urgency_score": urgency_score,
            "urgency_level": urgency_level,
            "reasoning_trace": reasoning_trace,
            "recommended_action": recommended_action,
            "estimated_wait_minutes": estimated_wait_minutes,
            "status": "scored",
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", str(session_id)).execute()


# ── Briefs ────────────────────────────────────────────────────────────────────


async def save_brief(
    patient_id: UUID,
    session_id: UUID,
    brief_text: str,
) -> dict:
    """Store a generated clinical brief."""
    client = _get_client()
    brief_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Handle placeholder patient ID (dummy UUID)
    pid_str = str(patient_id)
    if pid_str == "00000000-0000-0000-0000-000000000000":
        pid_val = None
    else:
        pid_val = pid_str

    row = {
        "id": brief_id,
        "patient_id": pid_val,
        "session_id": str(session_id),
        "brief_text": brief_text,
        "created_at": now,
    }
    result = client.table("briefs").insert(row).execute()
    return result.data[0] if result.data else row


async def get_brief_by_patient(patient_id: UUID) -> Optional[dict]:
    """Return the most recent brief for a patient."""
    client = _get_client()
    result = (
        client.table("briefs")
        .select("*")
        .eq("patient_id", str(patient_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_brief_by_triage(session_id: UUID) -> Optional[dict]:
    """Return the brief for a specific triage session."""
    client = _get_client()
    result = (
        client.table("briefs")
        .select("*")
        .eq("session_id", str(session_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_demo_patient(name: str = "Aarav Sharma") -> Optional[dict]:
    """Look up the demo patient by name."""
    client = _get_client()
    try:
        result = (
            client.table("patients")
            .select("*")
            .ilike("name", f"%{name}%")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        return None
