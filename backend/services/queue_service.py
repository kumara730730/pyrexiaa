"""
Redis sorted-set queue operations.

Key schema: ``queue:{clinic_id}``
Score   : ``urgency_score`` (DESC) combined with a timestamp tiebreaker.

Because Redis ZRANGEBYSCORE sorts ascending, we store the score as
``urgency_score * 1e10 + (MAX_TS - timestamp)`` so that higher urgency
AND earlier arrival both sort to the top when retrieved with ZREVRANGE.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional
from uuid import UUID

import redis.asyncio as redis

from models.queue import QueueEntry, QueueResponse
from models.triage import UrgencyLevel

# ── Redis client singleton ────────────────────────────────────────────────────

_pool: redis.Redis | None = None

MAX_TS = 9_999_999_999  # ~2286, used for tiebreaker inversion


async def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    return _pool


def _queue_key(clinic_id: str) -> str:
    return f"queue:{clinic_id}"


def _compute_score(urgency_score: int) -> float:
    """Higher urgency + earlier time → higher Redis score."""
    return urgency_score * 1e10 + (MAX_TS - int(time.time()))


# ── Public API ────────────────────────────────────────────────────────────────


async def enqueue_patient(
    clinic_id: str,
    patient_id: UUID,
    urgency_score: int,
    urgency_level: UrgencyLevel,
    chief_complaint: Optional[str] = None,
    voice_distress_score: float = 0.0,
) -> None:
    """Add or update a patient in the clinic queue."""
    r = await get_redis()
    key = _queue_key(clinic_id)
    member_data = json.dumps(
        {
            "patient_id": str(patient_id),
            "clinic_id": clinic_id,
            "urgency_score": urgency_score,
            "urgency_level": urgency_level.value,
            "chief_complaint": chief_complaint,
            "voice_distress_score": voice_distress_score,
            "enqueued_at": time.time(),
        }
    )
    # Remove old entry for same patient (if re-scored)
    await _remove_patient_entry(r, key, patient_id)
    score = _compute_score(urgency_score)
    await r.zadd(key, {member_data: score})


async def _remove_patient_entry(
    r: redis.Redis, key: str, patient_id: UUID
) -> Optional[int]:
    """Remove any existing entry for *patient_id* from the sorted set."""
    members = await r.zrange(key, 0, -1)
    for member in members:
        data = json.loads(member)
        if data["patient_id"] == str(patient_id):
            await r.zrem(key, member)
            return data.get("urgency_score")
    return None


async def get_queue(clinic_id: str) -> QueueResponse:
    """Return the full ordered queue for a clinic."""
    r = await get_redis()
    key = _queue_key(clinic_id)
    members = await r.zrevrange(key, 0, -1, withscores=False)

    from datetime import datetime, timezone
    from services.claude_service import rerank_queue

    parsed_items = []
    for raw in members:
        parsed_items.append(json.loads(raw))

    # Re-rank queue using Haiku
    reordered_items = await rerank_queue(parsed_items)

    entries: list[QueueEntry] = []
    for idx, data in enumerate(reordered_items, start=1):
        entries.append(
            QueueEntry(
                patient_id=data["patient_id"],
                clinic_id=data["clinic_id"],
                urgency_score=data["urgency_score"],
                urgency_level=UrgencyLevel(data["urgency_level"]),
                chief_complaint=data.get("chief_complaint"),
                voice_distress_score=data.get("voice_distress_score", 0.0),
                position=idx,
                enqueued_at=datetime.fromtimestamp(
                    data["enqueued_at"], tz=timezone.utc
                ),
            )
        )

    return QueueResponse(clinic_id=clinic_id, entries=entries, total=len(entries))


async def reorder_patient(
    clinic_id: str,
    patient_id: UUID,
    new_urgency_score: int,
) -> Optional[int]:
    """
    Update a patient's urgency score (manual staff override).

    Returns the previous score, or ``None`` if the patient was not found.
    """
    r = await get_redis()
    key = _queue_key(clinic_id)

    # Find and remove old entry
    old_score = None
    old_data = None
    members = await r.zrange(key, 0, -1)
    for member in members:
        data = json.loads(member)
        if data["patient_id"] == str(patient_id):
            old_score = data["urgency_score"]
            old_data = data
            await r.zrem(key, member)
            break

    if old_data is None:
        return None

    # Re-insert with new score
    old_data["urgency_score"] = new_urgency_score
    member_json = json.dumps(old_data)
    score = _compute_score(new_urgency_score)
    await r.zadd(key, {member_json: score})
    return old_score


async def remove_patient(clinic_id: str, patient_id: UUID) -> bool:
    """Remove a patient from the queue (called in). Returns True if found."""
    r = await get_redis()
    key = _queue_key(clinic_id)
    old_score = await _remove_patient_entry(r, key, patient_id)
    return old_score is not None


async def emergency_override(
    clinic_id: str,
    patient_id: UUID,
    chief_complaint: Optional[str] = None,
) -> Optional[int]:
    """
    Force a patient to score 100 (position 1).

    Returns the previous score or ``None`` if new to queue.
    """
    r = await get_redis()
    key = _queue_key(clinic_id)
    old_score = await _remove_patient_entry(r, key, patient_id)

    member_data = json.dumps(
        {
            "patient_id": str(patient_id),
            "clinic_id": clinic_id,
            "urgency_score": 100,
            "urgency_level": UrgencyLevel.CRITICAL.value,
            "chief_complaint": chief_complaint,
            "voice_distress_score": 10.0,  # Emergency is max distress
            "enqueued_at": time.time(),
        }
    )
    # Use a very high score to guarantee position 1
    await r.zadd(key, {member_data: _compute_score(100)})
    return old_score
