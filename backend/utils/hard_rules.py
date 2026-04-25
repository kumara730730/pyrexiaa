"""
Hard-rule emergency keyword detection.

These checks run BEFORE any AI call. If a critical keyword is found the
triage is short-circuited: urgency_score=100, urgency_level=CRITICAL.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Critical keyword list ─────────────────────────────────────────────────────

CRITICAL_KEYWORDS: list[str] = [
    # Cardiac
    "chest pain", "chest tightness", "chest pressure", "heart attack",
    "left arm pain", "left arm heavy", "jaw pain", "radiating pain",
    # Respiratory
    "can't breathe", "cannot breathe", "not breathing", "difficulty breathing",
    "breathing stopped", "choking", "airway",
    # Neurological
    "stroke", "seizure", "unconscious", "unresponsive", "collapsed",
    "sudden numbness", "face drooping", "arm weakness", "speech slurred",
    # Trauma / Bleeding
    "severe bleeding", "blood everywhere", "deep cut", "stabbed", "shot",
    # Allergic
    "anaphylaxis", "severe allergic", "epipen", "throat closing",
    "tongue swelling",
    # Overdose
    "overdose", "took too many pills", "poisoning",
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

    text_lower = text.lower()
    matched: list[str] = [kw for kw in CRITICAL_KEYWORDS if kw in text_lower]

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
