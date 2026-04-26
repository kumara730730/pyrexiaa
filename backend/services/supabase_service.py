"""
Supabase persistence layer.

All database reads and writes go through this module so the rest of the app
stays storage-agnostic.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

logger = logging.getLogger("supabase_service")

# ── Supabase client singleton ─────────────────────────────────────────────────

_client: Client | None = None
_client_failed: bool = False


def _get_client() -> Client | None:
    """Return the Supabase client, or None if credentials are missing."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            logger.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set — running without database")
            _client_failed = True
            return None
        _client = create_client(url, key, options=ClientOptions(auto_refresh_token=False))
        return _client
    except Exception as exc:
        logger.error("Failed to create Supabase client: %s", exc)
        _client_failed = True
        return None


# ── Patients ──────────────────────────────────────────────────────────────────


async def create_patient(data: dict) -> dict:
    """Insert a new patient row and return the created record."""
    patient_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": patient_id,
        **data,
        "created_at": now,
    }
    client = _get_client()
    if client is None:
        logger.info("Supabase unavailable — returning in-memory patient %s", patient_id)
        return row
    try:
        result = client.table("patients").insert(row).execute()
        return result.data[0] if result.data else row
    except Exception as exc:
        logger.error("create_patient failed: %s", exc)
        return row


async def get_patient(patient_id: UUID) -> Optional[dict]:
    """Fetch a patient by ID."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = (
            client.table("patients")
            .select("*")
            .eq("id", str(patient_id))
            .limit(1)
            .execute()
        )
        return result.data[0] if result and getattr(result, "data", None) else None
    except Exception as exc:
        logger.error("get_patient failed: %s", exc)
        return None


async def update_patient(patient_id: UUID, data: dict) -> Optional[dict]:
    """Partial update of a patient row."""
    client = _get_client()
    if client is None:
        return None
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            client.table("patients")
            .update({**data, "updated_at": now})
            .eq("id", str(patient_id))
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.error("update_patient failed: %s", exc)
        return None


# ── Triage sessions ──────────────────────────────────────────────────────────


async def create_triage_session(
    patient_id: UUID,
    clinic_id: str,
    chief_complaint: str,
    language: str = "en",
) -> dict:
    """Create a new triage session row."""
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
        "active_agent": "triage_orchestrator",
        "conversation_history": [],
        "created_at": now,
    }
    client = _get_client()
    if client is None:
        logger.info("Supabase unavailable — returning in-memory session %s", session_id)
        return row
    try:
        result = client.table("triage_sessions").insert(row).execute()
        return result.data[0] if result.data else row
    except Exception as exc:
        logger.error("create_triage_session failed: %s", exc)
        return row


async def update_active_agent(session_id: UUID, agent_id: str) -> None:
    """Update the active_agent for a triage session."""
    client = _get_client()
    if client is None:
        return
    try:
        client.table("triage_sessions").update(
            {"active_agent": agent_id}
        ).eq("id", str(session_id)).execute()
    except Exception as exc:
        logger.error("update_active_agent failed: %s", exc)


async def get_triage_session(session_id: UUID) -> Optional[dict]:
    """Fetch a triage session."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = (
            client.table("triage_sessions")
            .select("*")
            .eq("id", str(session_id))
            .limit(1)
            .execute()
        )
        return result.data[0] if result and getattr(result, "data", None) else None
    except Exception as exc:
        logger.error("get_triage_session failed: %s", exc)
        return None


async def append_message(
    session_id: UUID,
    role: str,
    content: str,
) -> None:
    """Append a message to the session's conversation_history JSON array."""
    client = _get_client()
    if client is None:
        return
    try:
        session = await get_triage_session(session_id)
        if session is None:
            return
        history: list[dict] = session.get("conversation_history", [])
        history.append({"role": role, "content": content})
        client.table("triage_sessions").update(
            {"conversation_history": history}
        ).eq("id", str(session_id)).execute()
    except Exception as exc:
        logger.error("append_message failed: %s", exc)


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
    if client is None:
        logger.info("Supabase unavailable — skipping score persistence for session %s", session_id)
        return
    try:
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
    except Exception as exc:
        logger.error("save_triage_score failed: %s", exc)


# ── Briefs ────────────────────────────────────────────────────────────────────


async def save_brief(
    patient_id: UUID,
    session_id: UUID,
    brief_text: str,
) -> dict:
    """Store a generated clinical brief."""
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
    client = _get_client()
    if client is None:
        return row
    try:
        result = client.table("briefs").insert(row).execute()
        return result.data[0] if result.data else row
    except Exception as exc:
        logger.error("save_brief failed: %s", exc)
        return row


async def get_brief_by_patient(patient_id: UUID) -> Optional[dict]:
    """Return the most recent brief for a patient."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = (
            client.table("briefs")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.error("get_brief_by_patient failed: %s", exc)
        return None


async def get_brief_by_triage(session_id: UUID) -> Optional[dict]:
    """Return the brief for a specific triage session."""
    client = _get_client()
    if client is None:
        return None
    try:
        result = (
            client.table("briefs")
            .select("*")
            .eq("session_id", str(session_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as exc:
        logger.error("get_brief_by_triage failed: %s", exc)
        return None


async def get_demo_patient(name: str = "Aarav Sharma") -> Optional[dict]:
    """Look up the demo patient by name."""
    client = _get_client()
    if client is None:
        return None
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
