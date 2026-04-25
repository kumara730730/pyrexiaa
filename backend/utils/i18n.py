"""
Language detection helper.

Uses ``langdetect`` for automatic detection with a fallback to the
language code provided by the client.
"""

from __future__ import annotations

from langdetect import detect, LangDetectException


def detect_language(text: str, fallback: str = "en") -> str:
    """
    Return an ISO 639-1 language code for *text*.

    Falls back to *fallback* when detection confidence is too low or the
    library raises an exception (e.g. on very short strings).
    """
    if not text or len(text.strip()) < 10:
        return fallback
    try:
        return detect(text)
    except LangDetectException:
        return fallback
