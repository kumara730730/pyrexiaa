# Tasks: Generalize Demo Logic & Agentic Triage

## Wave 1: Foundation & Background Services

### [auto] Task 1: Create BackgroundTasksService
- **Files**: `backend/services/background_tasks.py`
- **Action**: Create a service to handle post-triage workflows: saving scores, enqueuing patients, broadcasting updates, and generating briefs. This should be decoupled from the route handlers.
- **Verify**: `pytest tests/test_background_tasks.py` (to be created)
- **Done**: Logic moved from `backend/routes/triage.py` to `backend/services/background_tasks.py`.

### [auto] Task 2: Refactor main.py Startup
- **Files**: `backend/main.py`, `backend/services/background_tasks.py`
- **Action**: Replace `_pregenerate_demo_brief` with a generic `initialize_demo_data` call in `BackgroundTasksService` that can handle multiple demo scenarios.
- **Verify**: Server starts without errors, logs indicate demo data initialization.
- **Done**: `main.py` is clean of patient-specific logic.

### [auto] Task 3: Architectural Documentation
- **Files**: `amd/001-agentic-triage-architecture.md`, `amd/002-background-services-design.md`
- **Action**: Document the new agentic triage flow and the background task architecture.
- **Verify**: Files exist and contain detailed design notes.
- **Done**: Documentation complete.

## Wave 2: Agentic Triage Optimization

### [auto] Task 4: Refactor Claude Service to Agentic Pattern
- **Files**: `backend/services/claude_service.py`
- **Action**: Introduce `TriageAgent` class. It should manage the state of a triage session, determine when to ask more questions vs when to score, and handle brief generation as a separate state/method.
- **Verify**: `pytest tests/test_claude_service.py` (to be created)
- **Done**: `claude_service.py` follows an agentic pattern.

### [auto] Task 5: Improve Triage Prompts & Logic
- **Files**: `backend/services/claude_service.py`
- **Action**: Refactor `TriageAgent` to strictly use Anthropic tool-calling for the scoring action (`submit_triage_score`) as specified in `amd/001-agentic-triage-architecture.md`. Remove any mention of "JSON detection" or stream-sniffing for scoring signals.
- **Verify**: `pytest tests/test_triage_agent.py` - Use automated testing to verify the `TriageAgent` correctly invokes the `submit_triage_score` tool with expected arguments (severity, reason, recommendation) and transitions to the completion state.
- **Done**: Anthropic tool-calling enforced; JSON detection logic removed.

## Wave 3: Performance & Error Handling

### [auto] Task 6: Redis Caching for Latency
- **Files**: `backend/services/claude_service.py`, `backend/services/background_tasks.py`
- **Action**: Cache generated briefs and intermediate triage states in Redis to reduce redundant LLM calls and improve response times for staff views.
- **Verify**: Check Redis keys during operation; verify latency reduction in logs.
- **Done**: Caching implemented.

### [auto] Task 7: Robust Error Handling
- **Files**: `backend/services/claude_service.py`
- **Action**: Implement better error classification in `_retry_api_call`. Handle token limits, rate limits, and content filtering gracefully.
- **Verify**: Simulate API failures and verify system stays operational (using fallbacks).
- **Done**: Error handling hardened.
