"""Quick test of _deterministic_rerank — run from backend/."""

import json
import sys

sys.path.insert(0, ".")
from services.claude_service import _deterministic_rerank

queue = [
    {"patient_id": "P1", "urgency_level": "HIGH",     "wait_minutes": 45, "voice_distress_score": 3},
    {"patient_id": "P2", "urgency_level": "CRITICAL",  "wait_minutes": 10, "voice_distress_score": 5},
    {"patient_id": "P3", "urgency_level": "MODERATE",  "wait_minutes": 60, "voice_distress_score": 8},
    {"patient_id": "P4", "urgency_level": "CRITICAL",  "wait_minutes": 25, "voice_distress_score": 2},
    {"patient_id": "P5", "urgency_level": "HIGH",      "wait_minutes": 30, "voice_distress_score": 9},
    {"patient_id": "P6", "urgency_level": "LOW",       "wait_minutes": 90, "voice_distress_score": 1},
    {"patient_id": "P7", "urgency_level": "HIGH",      "wait_minutes": 50, "voice_distress_score": 2},
]

result = _deterministic_rerank(queue)
ordered = [
    f"{r['patient_id']} ({r['urgency_level']}, wait={r['wait_minutes']}m, distress={r['voice_distress_score']})"
    for r in result
]

print(json.dumps({"ordered_ids": [r["patient_id"] for r in result]}, indent=2))
print()
for i, entry in enumerate(ordered, 1):
    print(f"  {i}. {entry}")
