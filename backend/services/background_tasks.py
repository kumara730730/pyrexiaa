"""
Background Tasks Service — Decouples long-running or post-triage actions from API routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from services import claude_service, supabase_service, queue_service
from services.realtime_service import broadcast_queue_update

logger = logging.getLogger("background_tasks")


async def handle_scoring_complete(
    session_id: UUID,
    patient_id: UUID,
    clinic_id: str,
    score_data: dict,
    voice_distress_score: float | None = None,
) -> None:
    """
    Handle all actions required once a triage score is generated:
    1. Persist score to database.
    2. Enqueue patient in Redis.
    3. Broadcast queue update.
    4. Trigger clinical brief generation in the background.
    """
    try:
        urgency_score = int(score_data.get("urgency_score", 50))
        urgency_level = score_data.get("urgency_level", "MODERATE")
        reasoning_trace = score_data.get("reasoning_trace", [])
        recommended_action = score_data.get("recommended_action")
        estimated_wait = score_data.get("estimated_wait_minutes")
        chief_complaint = score_data.get("chief_complaint_refined")

        # 1. Persist score
        await supabase_service.save_triage_score(
            session_id=session_id,
            urgency_score=urgency_score,
            urgency_level=urgency_level,
            reasoning_trace=reasoning_trace,
            recommended_action=recommended_action,
            estimated_wait_minutes=estimated_wait,
        )

        # 2. Enqueue
        from models.triage import UrgencyLevel
        await queue_service.enqueue_patient(
            clinic_id=clinic_id,
            patient_id=patient_id,
            urgency_score=urgency_score,
            urgency_level=UrgencyLevel(urgency_level),
            chief_complaint=chief_complaint,
        )

        # 3. Broadcast update
        queue = await queue_service.get_queue(clinic_id)
        await broadcast_queue_update(clinic_id, queue.model_dump(mode="json"))

        # 4. Fire brief builder
        asyncio.create_task(
            generate_and_save_brief(
                session_id=session_id,
                patient_id=patient_id,
                score_data=score_data,
                voice_distress_score=voice_distress_score,
            ),
            name=f"brief-{session_id}",
        )
        logger.info("Successfully handled scoring completion for session %s", session_id)

    except Exception:
        logger.exception("Failed to handle scoring completion for session %s", session_id)


async def generate_and_save_brief(
    session_id: UUID,
    patient_id: UUID,
    score_data: dict,
    voice_distress_score: float | None = None,
) -> None:
    """Generate a clinical brief and persist it, using Redis for caching."""
    cache_key = f"brief:patient:{patient_id}"
    try:
        # ── Check Redis Cache ─────────────────────────────────────────────
        from services.claude_service import _get_redis
        r = await _get_redis()
        cached = await r.get(cache_key)
        if cached:
            logger.info("Retrieved brief from Redis cache for patient %s", patient_id)
            # We still save to Supabase to ensure long-term persistence/sync
            await supabase_service.save_brief(
                patient_id=patient_id,
                session_id=session_id,
                brief_text=cached,
            )
            return

        # ── Generate New Brief ────────────────────────────────────────────
        patient = await supabase_service.get_patient(patient_id)
        patient_name = patient.get("name", "Unknown") if patient else "Unknown"
        age = patient.get("age") if patient else None
        gender = patient.get("gender") if patient else None

        vds = voice_distress_score if voice_distress_score is not None else float(patient.get("voice_distress_score", 0) if patient else 0)

        # Load conversation history for context
        history = await claude_service._load_history(str(session_id))
        history_notes = "\n".join(
            f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
            for m in history
        )

        brief = await claude_service.generate_brief(
            patient_name=patient_name,
            age=age,
            gender=gender,
            history_notes=history_notes,
            urgency_json=score_data,
            voice_distress_score=vds,
        )

        brief_json = json.dumps(brief)

        # ── Save to Supabase & Cache in Redis (TTL 1 hour) ────────────────
        await supabase_service.save_brief(
            patient_id=patient_id,
            session_id=session_id,
            brief_text=brief_json,
        )
        await r.setex(cache_key, 3600, brief_json)
        
        logger.info("Clinical brief generated, saved and cached for session %s", session_id)

    except Exception:
        logger.exception("Failed to generate brief for session %s", session_id)
