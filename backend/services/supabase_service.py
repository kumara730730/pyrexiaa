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
    row = {
        "id": session_id,
        "patient_id": str(patient_id),
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
    row = {
        "id": brief_id,
        "patient_id": str(patient_id),
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


# ── Demo cache seeding ────────────────────────────────────────────────────────


async def upsert_demo_cache(scenario: str, response_json: dict) -> None:
    """Insert or update a demo_cache row (upsert on scenario key)."""
    client = _get_client()
    row = {
        "scenario": scenario,
        "response_json": response_json,
    }
    client.table("demo_cache").upsert(row, on_conflict="scenario").execute()


async def seed_demo_cache() -> None:
    """Seed the aarav_sharma_triage demo record into demo_cache on startup.

    Idempotent — uses upsert so it is safe to call on every boot.
    """
    import logging

    logger = logging.getLogger("supabase_service")

    payload = {
        "patient": {
            "name": "Aarav Sharma",
            "age": 52,
            "gender": "M",
            "history_notes": (
                "Type 2 Diabetes (metformin 500mg BD). Smoker — 15 pack-years. "
                "No prior cardiac events documented. Last clinic visit: 8 months "
                "ago for HbA1c monitoring."
            ),
        },
        "triage_output": {
            "urgency_score": 94,
            "urgency_level": "CRITICAL",
            "reasoning_trace": [
                "ACS pattern: chest pressure + left arm radiation",
                "Diaphoresis with sudden onset — high-risk presentation",
                "Symptom onset during sleep/early morning — peak cardiac event window",
                "Jaw radiation = triple-vessel pattern consistent with STEMI/NSTEMI",
                "Diabetic patient: atypical presentation risk — real urgency likely higher than reported",
                "15 pack-year smoking history compounds atherogenic risk",
            ],
            "presenting_complaint": (
                "52M presenting with sudden-onset chest tightness, left arm heaviness, "
                "and jaw radiation since 07:00. Associated diaphoresis."
            ),
            "red_flags": [
                "ACS pattern — chest + arm + jaw radiation",
                "Diaphoresis reported",
                "Sudden onset in early morning — peak STEMI window",
                "Diabetic with masked pain threshold",
            ],
            "suggested_doctor_questions": [
                "Is the chest discomfort constant or does it come and go?",
                "Rate your pain from 1 to 10 right now.",
                "Have you taken any aspirin or GTN before coming in?",
            ],
            "recommended_doctor_specialty": "Cardiology",
        },
        "brief": {
            "brief_summary": (
                "52M diabetic smoker presenting with classical ACS-pattern symptoms: "
                "chest pressure, left arm heaviness, jaw radiation, and diaphoresis "
                "since 07:00. Atypical pain in diabetics — do not underestimate. "
                "Immediate assessment required."
            ),
            "priority_flags": [
                "ACS pattern — chest + arm + jaw triple radiation",
                "Diabetic: masked pain threshold, atypical presentation risk",
                "Diaphoresis with sudden AM onset — peak STEMI window",
                "15 pack-year smoking: high baseline atherogenic risk",
            ],
            "context_from_history": (
                "T2DM on metformin, active smoker (15 pack-years). No prior cardiac "
                "events. HbA1c 8 months ago — current glycaemic control unknown."
            ),
            "suggested_opening_questions": [
                "Is the discomfort still ongoing, and has the character changed since arrival?",
                "Have you taken aspirin or GTN today?",
                "Any similar episodes in the past — even mild ones you dismissed?",
            ],
            "watch_for": (
                "IMMEDIATE: ECG within 60 seconds. Do not defer for full history — "
                "STEMI door-to-balloon time is the priority."
            ),
        },
    }

    try:
        await upsert_demo_cache("aarav_sharma_triage", payload)
        logger.info("✓ demo_cache seeded: aarav_sharma_triage")
    except Exception:
        logger.warning("demo_cache seeding failed (non-fatal)", exc_info=True)
