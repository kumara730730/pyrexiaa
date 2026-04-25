"""
Anthropic API integration — Sonnet 4 for triage reasoning, Haiku for briefs.

All methods are async.  The ``stream_triage_response`` method yields tokens
for SSE consumption at the route level.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import anthropic

# ── Client singleton ──────────────────────────────────────────────────────────

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    return _client


# ── Model constants ───────────────────────────────────────────────────────────

SONNET_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL = "claude-haiku-4-20250414"

# ── System prompts ────────────────────────────────────────────────────────────

TRIAGE_SYSTEM_PROMPT = """\
You are PriorIQ, a medical triage assistant.  Your job is to ask focused
follow-up questions to assess the patient's urgency level.

Rules:
- Be empathetic but concise.
- Ask ONE question at a time.
- Never diagnose or prescribe.
- Gather: onset, severity (1-10), duration, associated symptoms, medical history.
- If the patient describes life-threatening symptoms, urge them to call emergency
  services immediately while continuing the triage.
- Respond in the patient's language.
"""

SCORING_SYSTEM_PROMPT = """\
You are PriorIQ's triage scoring engine.  Given the full conversation between
the triage assistant and a patient, produce a JSON object with these fields:

{
  "urgency_score": <int 0-100>,
  "urgency_level": "<CRITICAL|HIGH|MODERATE|LOW|NON_URGENT>",
  "reasoning_trace": ["<step-by-step reasoning>"],
  "recommended_action": "<brief recommendation>",
  "estimated_wait_minutes": <int or null>
}

Scoring guidance:
- 90-100  CRITICAL   → Immediate life-threatening
- 70-89   HIGH       → Urgent, needs rapid assessment
- 40-69   MODERATE   → Semi-urgent
- 20-39   LOW        → Non-urgent but needs attention
- 0-19    NON_URGENT → Can wait / self-care

Return ONLY valid JSON, no markdown fences.
"""

BRIEF_SYSTEM_PROMPT = """\
You are PriorIQ's clinical brief generator.  Given triage conversation history
and scoring data for a patient, produce a concise clinical handoff brief that
a physician can read in under 30 seconds.

Include:
- Chief complaint (1 line)
- Key symptoms & timeline
- Relevant history mentioned
- Urgency assessment
- Recommended next steps

Use bullet points.  Be factual, never speculate.
"""


# ── Triage conversation (streaming) ──────────────────────────────────────────

async def stream_triage_response(
    conversation_history: list[dict],
    language: str = "en",
) -> AsyncIterator[str]:
    """
    Stream a triage follow-up response token-by-token.

    *conversation_history* is a list of ``{"role": ..., "content": ...}`` dicts
    following Anthropic's messages format.
    """
    client = _get_client()

    async with client.messages.stream(
        model=SONNET_MODEL,
        max_tokens=1024,
        system=TRIAGE_SYSTEM_PROMPT,
        messages=conversation_history,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def get_triage_response(
    conversation_history: list[dict],
    language: str = "en",
) -> str:
    """Non-streaming version — returns the full response at once."""
    client = _get_client()

    message = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1024,
        system=TRIAGE_SYSTEM_PROMPT,
        messages=conversation_history,
    )
    return message.content[0].text


# ── Triage scoring ────────────────────────────────────────────────────────────

async def score_triage(conversation_history: list[dict]) -> dict:
    """
    Ask Sonnet to produce a final urgency score for the conversation.

    Returns the parsed JSON dict.
    """
    import json

    client = _get_client()

    scoring_messages = [
        {
            "role": "user",
            "content": (
                "Here is the full triage conversation:\n\n"
                + "\n".join(
                    f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
                    for m in conversation_history
                )
                + "\n\nPlease score this triage session."
            ),
        }
    ]

    message = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1024,
        system=SCORING_SYSTEM_PROMPT,
        messages=scoring_messages,
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if the model wraps them anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]

    return json.loads(raw)


# ── Clinical brief (Haiku — fast & cheap) ─────────────────────────────────────

async def generate_brief(
    conversation_history: list[dict],
    scoring_data: dict,
) -> str:
    """Generate a physician-facing clinical brief using Haiku."""
    client = _get_client()

    brief_messages = [
        {
            "role": "user",
            "content": (
                "## Triage Conversation\n\n"
                + "\n".join(
                    f"{'Patient' if m['role'] == 'user' else 'Triage AI'}: {m['content']}"
                    for m in conversation_history
                )
                + f"\n\n## Scoring Data\n{scoring_data}"
                + "\n\nGenerate the clinical handoff brief."
            ),
        }
    ]

    message = await client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        system=BRIEF_SYSTEM_PROMPT,
        messages=brief_messages,
    )
    return message.content[0].text
