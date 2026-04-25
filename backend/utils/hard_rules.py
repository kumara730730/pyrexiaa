"""
Hard-rule emergency keyword detection.

These checks run BEFORE any AI call. If a critical keyword is found the
triage is short-circuited: urgency_score=100, urgency_level=CRITICAL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Critical keyword list ─────────────────────────────────────────────────────

CRITICAL_KEYWORDS: list[str] = [
    "chest pain",
    "chest tightness",
    "can't breathe",
    "not breathing",
    "unconscious",
    "unresponsive",
    "seizure",
    "stroke",
    "left arm pain",
    "jaw pain with chest",
    "severe bleeding",
    "overdose",
    "anaphylaxis",
    "allergic reaction severe",
]

# Pre-compile patterns for fast matching (word-boundary, case-insensitive)
_CRITICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE) for kw in CRITICAL_KEYWORDS
]


@dataclass
class HardRuleResult:
    """Outcome of hard-rule screening."""

    triggered: bool = False
    matched_keywords: list[str] = field(default_factory=list)
    urgency_score: int = 0
    urgency_level: str = "NON_URGENT"
    reasoning_trace: list[str] = field(default_factory=list)


def check_hard_rules(text: str) -> HardRuleResult:
    """
    Scan *text* for critical keywords.

    Returns a ``HardRuleResult``.  When ``triggered`` is ``True`` the caller
    must skip the Claude call and use the result directly.
    """
    if not text:
        return HardRuleResult()

    matched: list[str] = []
    for pattern, keyword in zip(_CRITICAL_PATTERNS, CRITICAL_KEYWORDS):
        if pattern.search(text):
            matched.append(keyword)

    if not matched:
        return HardRuleResult()

    return HardRuleResult(
        triggered=True,
        matched_keywords=matched,
        urgency_score=100,
        urgency_level="CRITICAL",
        reasoning_trace=[
            f"AUTO-CRITICAL: Hard rule keyword match — {', '.join(matched)}"
        ],
    )
