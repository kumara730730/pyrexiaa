"""
Supabase Realtime broadcast trigger.

After every queue mutation the caller invokes ``broadcast_queue_update``
which pushes a message on the ``queue:{clinic_id}`` channel so that all
connected frontends receive the new queue state instantly.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

# ── Configuration ─────────────────────────────────────────────────────────────

_SUPABASE_URL: str | None = None
_SUPABASE_KEY: str | None = None


def _get_config() -> tuple[str, str]:
    global _SUPABASE_URL, _SUPABASE_KEY
    if _SUPABASE_URL is None:
        _SUPABASE_URL = os.environ["SUPABASE_URL"]
        _SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
    return _SUPABASE_URL, _SUPABASE_KEY  # type: ignore[return-value]


# ── Broadcast ─────────────────────────────────────────────────────────────────


async def broadcast_queue_update(
    clinic_id: str,
    queue_data: dict[str, Any],
) -> None:
    """
    Send a broadcast message via the Supabase Realtime REST API.

    Channel: ``queue:{clinic_id}``
    Event  : ``queue_update``

    The *queue_data* payload is the serialised ``QueueResponse``.
    """
    base_url, api_key = _get_config()
    url = f"{base_url}/realtime/v1/api/broadcast"

    payload = {
        "channel": f"queue:{clinic_id}",
        "event": "queue_update",
        "payload": queue_data,
    }

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Log but do not crash the request — queue state is already persisted
            import logging
            logging.getLogger("realtime").warning(
                "Broadcast failed for clinic %s: %s %s",
                clinic_id,
                exc.response.status_code,
                exc.response.text,
            )
        except httpx.RequestError as exc:
            import logging
            logging.getLogger("realtime").warning(
                "Broadcast connection error for clinic %s: %s", clinic_id, exc
            )


async def broadcast_emergency(
    clinic_id: str,
    patient_id: str,
    chief_complaint: str,
    matched_keywords: list[str],
) -> None:
    """
    Broadcast an ``emergency_critical`` event to all doctor screens.

    Channel: ``emergency:{clinic_id}``
    Event  : ``emergency_critical``

    This is separate from ``queue_update`` and triggers alarm UI on doctor
    dashboards.
    """
    base_url, api_key = _get_config()
    url = f"{base_url}/realtime/v1/api/broadcast"

    payload = {
        "channel": f"emergency:{clinic_id}",
        "event": "emergency_critical",
        "payload": {
            "patient_id": patient_id,
            "chief_complaint": chief_complaint,
            "matched_keywords": matched_keywords,
            "urgency_score": 100,
            "urgency_level": "CRITICAL",
        },
    }

    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            import logging
            logging.getLogger("realtime").warning(
                "Emergency broadcast failed for clinic %s: %s %s",
                clinic_id,
                exc.response.status_code,
                exc.response.text,
            )
        except httpx.RequestError as exc:
            import logging
            logging.getLogger("realtime").warning(
                "Emergency broadcast connection error for clinic %s: %s",
                clinic_id,
                exc,
            )
