# Background Services Design

## Rationale
Currently, several critical post-triage steps (saving the score, enqueuing the patient, broadcasting via Realtime, and generating the clinical brief) are interleaved with route logic. This makes the system harder to test and maintain. We will consolidate this into a dedicated `BackgroundTasksService`.

## Responsibilities
The `BackgroundTasksService` will provide a unified interface for complex, asynchronous workflows:

1. **`process_triage_completion(session_id, score_data)`**:
   - Persists the final score to Supabase.
   - Enqueues the patient in Redis with the appropriate score/tiebreaker.
   - Broadcasts the queue update to all doctor dashboards.
   - Triggers the brief generation task.
2. **`generate_and_save_brief(patient_id, session_id, history)`**:
   - Calls the `TriageAgent` (or dedicated brief model) to generate a concise summary.
   - Persists the JSON brief to Supabase.
3. **`initialize_demo_environment(scenarios)`**:
   - Replaces the hardcoded `_pregenerate_demo_brief` in `main.py`.
   - Populates necessary data (patients, triage sessions, briefs) for specified demo patients (e.g., "Aarav Sharma", "Zoya Khan").

## Integration Pattern
Routes should only be responsible for:
- Authenticating/Validating the request.
- Initiating the process.
- Returning an immediate response (or starting a stream).

Long-running or multi-step operations are handed off to the `BackgroundTasksService` via `asyncio.create_task`. In a larger production environment, this would eventually move to a task queue like Celery or RabbitMQ.

## Latency & Reliability
- **Redis Caching**: Briefs should be cached in Redis with a reasonable TTL (e.g., 2 hours, matching the session TTL). This ensures that if a doctor clicks on a patient multiple times, the brief is retrieved instantly without hitting Claude.
- **Graceful Error Handling**: If brief generation fails, it should be logged as a warning, but it should not crash the triage process or prevent the patient from appearing in the queue.
