"""Deterministic pattern engine.

Exposes a single ``extract_all`` entry point that runs every extractor over a
window of events and returns the combined list of learned patterns.
"""
from __future__ import annotations

from safety.models.events import Event
from safety.models.patterns import BasePattern
from safety.pattern_engine.duration2 import extract_duration_patterns
from safety.pattern_engine.sequence_based_2 import extract_sequence_patterns
from safety.pattern_engine.time_based2 import extract_time_patterns


def extract_all(household_id: str, events: list[Event]) -> list[BasePattern]:
    patterns: list[BasePattern] = []
    patterns.extend(extract_time_patterns(household_id, events))
    patterns.extend(extract_sequence_patterns(household_id, events))
    patterns.extend(extract_duration_patterns(household_id, events))
    return patterns


__all__ = [
    "extract_all",
    "extract_time_patterns",
    "extract_sequence_patterns",
    "extract_duration_patterns",
]
