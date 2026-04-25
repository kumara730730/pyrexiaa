# Agentic Triage Architecture

## Current State
The current triage flow in `claude_service.py` is procedural and relies on a somewhat brittle JSON-sniffing hack (`__SCORE_JSON__:`) over the SSE stream to determine when the model has decided to score the patient instead of asking another question.

## Target Architecture: TriageAgent
We will encapsulate the multi-turn triage logic into a `TriageAgent` class. 

### Core Responsibilities
1. **State Management**: The agent manages the session state (e.g., `GATHERING_INFO`, `SCORING`, `COMPLETE`).
2. **Tool Calling (Anthropic API)**: Instead of sniffing for JSON, we will utilize Claude's native tool-calling (function calling) capabilities. The agent will be provided with a tool called `submit_triage_score`. 
    - If the model decides it has enough information, it calls `submit_triage_score`.
    - The stream will intercept the tool use block, extract the JSON, and cleanly signal completion to the client.
3. **Prompt Engineering**: The system prompt will explicitly instruct Claude to converse naturally and use the `submit_triage_score` tool when ready.

### Flow
1. **Patient Input**: User sends a message.
2. **History Update**: Message is appended to Redis history.
3. **LLM Inference**: `TriageAgent.stream_reply()` calls Claude with history and the `submit_triage_score` tool definition.
4. **Tool Detection**:
    - If Claude responds with text, stream it to the user.
    - If Claude invokes `submit_triage_score`, stream a sentinel (or handle tool use via a custom SSE event like `event: score`), then trigger the background tasks (save, enqueue, brief).

## Fallback Mechanisms
- If the Anthropic API fails after retries, the agent will fall back to retrieving a cached demo scenario from Supabase (`demo_cache`).
- If Supabase fails, a hardcoded emergency fallback is returned.

## Benefits
- Removes brittle regex/parsing logic on the stream.
- Cleaner separation of conversational output and structured data output.
- Sets the foundation for adding more tools in the future (e.g., `escalate_to_human`, `request_vitals`).
