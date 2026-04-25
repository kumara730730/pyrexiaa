---
phase: "Generalize Demo Logic & Agentic Triage"
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/main.py
  - backend/services/background_tasks.py
  - backend/services/claude_service.py
  - amd/001-agentic-triage-architecture.md
  - amd/002-background-services-design.md
autonomous: true
requirements: [TRIAGE-01, TRIAGE-02, INFRA-01]
must_haves:
  truths:
    - "User can complete a triage session where the score is submitted via native tool-calling (submit_triage_score) instead of JSON sniffing."
    - "Post-triage actions (brief generation, enqueuing) are handled by a dedicated BackgroundTasksService."
    - "System starts up and initializes demo data through the generalized background service without hardcoded patient logic in main.py."
  artifacts:
    - path: "backend/services/background_tasks.py"
      provides: "Asynchronous processing of post-triage workflows"
    - path: "backend/services/claude_service.py"
      provides: "TriageAgent implementing tool-calling logic"
    - path: "amd/001-agentic-triage-architecture.md"
      provides: "Architectural specification for agentic triage"
  key_links:
    - from: "backend/services/claude_service.py"
      to: "Anthropic Tool Calling API"
      via: "submit_triage_score tool definition"
    - from: "backend/routes/triage.py"
      to: "backend/services/background_tasks.py"
      via: "background_tasks.add_task(process_triage_result)"
---

# Phase: Generalize Demo Logic & Agentic Triage

Objective: Generalize hardcoded demo logic into production-ready API services and implement a robust AI agent workflow for triage.

## Goals
- Refactor `_pregenerate_demo_brief` into a generic `BackgroundTasksService`.
- Optimize `claude_service` for agentic triage (multi-turn -> scoring -> brief).
- Enhance error handling and latency (Redis caching).
- Document architecture in `amd/`.

## Success Criteria
- [ ] No hardcoded "Aarav Sharma" logic in `main.py`.
- [ ] `BackgroundTasksService` handles post-triage actions asynchronously.
- [ ] `TriageAgent` in `claude_service.py` manages conversation state and transitions.
- [ ] Redis caching effectively used for performance.
- [ ] Architectural docs present in `amd/`.

## Waves
- **Wave 1: Foundation & Background Services**
  - Create `BackgroundTasksService`.
  - Refactor `main.py` startup logic.
  - Initial AMD documentation in `amd/002-background-services-design.md`.
- **Wave 2: Agentic Triage Optimization**
  - Refactor `claude_service.py` to use a `TriageAgent` pattern.
  - Improve prompts and transition logic based on `amd/001-agentic-triage-architecture.md`.
- **Wave 3: Performance & Error Handling**
  - Latency optimizations with Redis.
  - Robust error classification and recovery.
