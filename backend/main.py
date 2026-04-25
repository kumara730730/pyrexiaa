"""
Pyrexia — Medical Triage System Backend

FastAPI application with CORS, health checks, and route registration.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env before anything touches os.environ
load_dotenv()

from routes import triage, brief, queue, patients, voice  # noqa: E402

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger("pyrexia")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources on startup, tear down on shutdown."""
    logger.info("Pyrexia starting up …")

    # Validate mandatory env vars early
    required_vars = [
        "ANTHROPIC_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "REDIS_URL",
    ]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        logger.warning("Missing environment variables: %s", ", ".join(missing))

    # ── Pre-generate Aarav demo brief on startup ──────────────────────────
    import asyncio
    asyncio.create_task(
        _pregenerate_demo_brief(),
        name="demo-brief-pregenerate",
    )

    yield

    # Shutdown: close Redis pools if opened
    from services.queue_service import _pool
    from services import claude_service

    if _pool is not None:
        await _pool.aclose()
        logger.info("Redis connection (queue) closed")

    if claude_service._redis is not None:
        await claude_service._redis.aclose()
        logger.info("Redis connection (claude) closed")

    logger.info("Pyrexia shut down")


async def _pregenerate_demo_brief() -> None:
    """Pre-generate the clinical brief for the Aarav demo patient.

    Runs on startup so the brief is instantly available when a doctor
    clicks on Aarav during a pitch demo.  Gracefully skips on any error.
    """
    import json
    from services import supabase_service, claude_service

    try:
        # Look up demo patient
        demo_patient = await supabase_service.get_demo_patient("Aarav Sharma")
        if not demo_patient:
            logger.info("Demo patient 'Aarav Sharma' not found — skipping brief pre-generation")
            return

        patient_id = demo_patient["id"]

        # Check if a brief already exists
        existing = await supabase_service.get_brief_by_patient(patient_id)
        if existing:
            logger.info("Demo brief already exists for Aarav — skipping")
            return

        # Use the cached demo triage data
        demo_urgency = await claude_service.get_cached_demo_response("aarav_sharma")

        brief = await claude_service.generate_brief(
            patient_name=demo_patient.get("name", "Aarav Sharma"),
            age=demo_patient.get("age", 28),
            gender=demo_patient.get("gender", "Male"),
            history_notes="Patient reports severe abdominal pain (8/10). Onset 3 hours ago, sudden. Associated nausea and fever (38.5°C). No prior history of similar episodes.",
            urgency_json=demo_urgency,
            voice_distress_score=float(demo_patient.get("voice_distress_score", 6.5)),
        )

        await supabase_service.save_brief(
            patient_id=patient_id,
            session_id=patient_id,  # Use patient_id as a stand-in for demo
            brief_text=json.dumps(brief),
        )
        logger.info("✓ Demo brief pre-generated for Aarav Sharma")

    except Exception:
        logger.warning("Demo brief pre-generation failed (non-fatal)", exc_info=True)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pyrexia",
    description="AI-powered medical triage and queue management system",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ─────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__,
        },
    )


# ── Request logging middleware ────────────────────────────────────────────────


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time

    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(triage.router)
app.include_router(brief.router)
app.include_router(queue.router)
app.include_router(patients.router)
app.include_router(voice.router)


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "Pyrexia"}


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "Pyrexia",
        "version": "1.0.0",
        "docs": "/docs",
    }
