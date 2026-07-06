"""Day-aware pattern relevance — pause weekday-only routines on days off.

The deterministic engine mines routines from a mix of weekdays and weekends,
then applies them uniformly. A strictly-weekday routine (a school run, an
office commute, a weekday alarm) therefore gets falsely flagged as a *missed
routine* on a Sunday or a festival day.

This module asks an LLM — ONLY on weekends and festival days — which learned
routines still apply today and which should be paused. Key guarantees that keep
it aligned with the rest of the engine:

* On an ordinary weekday it is a **no-op**: no LLM call, patterns untouched.
* The LLM can only **pause** existing routines; it never invents new ones.
* Safety-net detectors (device-active-too-long, duration) don't depend on
  routine patterns, so pausing a routine never suppresses a safety alarm.
* If the LLM is unavailable, a conservative keyword heuristic is used, so the
  feature still degrades gracefully.

The result is cached per (household, day, routine-set) so the LLM runs at most
once per day per home even though the frontend re-evaluates on every change.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from patterns.app.config import get_settings
from patterns.logic.pattern_intelligence import _call_groq_json
from patterns.models.context import DayAdaptation, PausedRoutine
from patterns.models.patterns import BasePattern

logger = logging.getLogger(__name__)

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Conservative fallback: routines whose device/description mentions any of these
# are treated as weekday-only when the LLM is unavailable on a day off.
_WEEKDAY_KEYWORDS = (
    "school", "college", "office", "work", "commute", "bus",
    "tuition", "class", "gym", "job", "shift",
)

# Cache LLM verdicts for a day so repeated evaluations don't re-call it.
_CACHE_TTL_SECONDS = 1800  # 30 min
_cache: dict[str, tuple[float, set[str], bool]] = {}


@dataclass
class DayInfo:
    """The resolved 'what day is it' context the filter reasons over."""

    dow: str                       # "Mon".."Sun"
    day_type: str                  # "weekday" | "weekend"
    festival: str | None = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_special(self) -> bool:
        """Only weekends and festival days trigger filtering."""
        return self.day_type == "weekend" or bool(self.festival)

    @property
    def cache_key(self) -> str:
        return f"{self.now.date().isoformat()}|{self.day_type}|{self.festival or ''}"

    def label(self) -> str:
        if self.festival:
            return self.festival
        return "the weekend" if self.day_type == "weekend" else "a weekday"


def resolve_day(
    now: datetime | None,
    override: dict | None = None,
) -> DayInfo:
    """Resolve the day context from the clock, with an optional demo override.

    ``override`` (from the frontend day selector) may set ``day_type`` to force
    "weekday"/"weekend" regardless of the real date, and ``festival`` to name a
    festive day. When absent, the weekday/weekend split is derived from ``now``.
    """
    now = now or datetime.now(timezone.utc)
    override = override or {}

    forced = (override.get("day_type") or "").strip().lower()
    if forced in {"weekday", "weekend"}:
        day_type = forced
    else:
        day_type = "weekend" if now.weekday() >= 5 else "weekday"

    festival = (override.get("festival") or "").strip() or None
    return DayInfo(dow=_DOW[now.weekday()], day_type=day_type, festival=festival, now=now)


def _routine_view(patterns: list[BasePattern]) -> list[dict]:
    """A token-light summary of each routine for the LLM to judge."""
    out = []
    for p in patterns:
        desc = _describe(p)
        if not desc:
            continue
        t = getattr(p, "usual_time", None) or getattr(p, "usual_start_time", None)
        out.append(
            {
                "pattern_id": p.pattern_id,
                "description": desc,
                "time": t,
                "confidence": p.confidence,
            }
        )
    return out


def _describe(p: BasePattern) -> str:
    dev = getattr(p, "device", None)
    act = getattr(p, "action", None)
    if dev and act:
        return f"{dev} {act}"
    return getattr(p, "description", "") or ""


SYSTEM_PROMPT = """You are a household-routine analyst. A deterministic engine learned a home's
daily routines from smart-home history and normally expects them EVERY day. But
today is not an ordinary working weekday, so some routines should be paused.

You are told the day (weekend and/or a named festival) and the list of learned
routines (each with an id, a short description, and its usual time).

Pause a routine ONLY if it is clearly tied to a working/school weekday and would
not naturally happen on a day off — for example: school drop-offs, college or
office departures, weekday morning alarms, and work commutes.

KEEP everyday home routines even if they usually shift later on a holiday — for
example: meals, tea/chai, prayer/pooja, lights, TV, water motor, sleep.

Be conservative: when unsure, KEEP the routine. Never invent routines.

Return STRICT JSON only:
{"paused":[{"pattern_id":"<id>","reason":"<short reason it doesn't apply today>"}]}"""


async def _llm_paused_ids(day: DayInfo, routines: list[dict]) -> set[str] | None:
    """Ask the LLM which routine ids to pause today. None if unavailable."""
    settings = get_settings()
    day_desc = "the weekend" if day.day_type == "weekend" else "a weekday"
    if day.festival:
        day_desc += f", and it is {day.festival} (a festival)"
    user_payload = {
        "today": {"day_of_week": day.dow, "description": day_desc},
        "routines": routines,
    }
    result = await _call_groq_json(SYSTEM_PROMPT, json.dumps(user_payload), settings)
    if not isinstance(result, dict):
        return None
    paused = result.get("paused")
    if not isinstance(paused, list):
        return None
    ids = {
        item.get("pattern_id")
        for item in paused
        if isinstance(item, dict) and item.get("pattern_id")
    }
    return ids


def _fallback_paused_ids(routines: list[dict]) -> set[str]:
    """Keyword heuristic used when the LLM is unavailable on a day off."""
    paused: set[str] = set()
    for r in routines:
        blob = f"{r['pattern_id']} {r['description']}".lower()
        if any(kw in blob for kw in _WEEKDAY_KEYWORDS):
            paused.add(r["pattern_id"])
    return paused


async def adapt_patterns(
    household_id: str,
    patterns: list[BasePattern],
    day: DayInfo,
) -> tuple[list[BasePattern], DayAdaptation]:
    """Return (patterns to use today, adaptation record).

    On an ordinary weekday nothing is filtered. On a weekend/festival the
    weekday-only routines are paused (LLM-decided, cached, keyword fallback).
    """
    if not day.is_special or not patterns:
        return patterns, DayAdaptation(
            active=False, day_type=day.day_type, festival=day.festival, kept_count=len(patterns)
        )

    routines = _routine_view(patterns)
    # Cache key also folds in the routine ids so a changed pattern-set re-runs.
    routine_sig = ",".join(sorted(r["pattern_id"] for r in routines))
    key = f"{household_id}|{day.cache_key}|{hash(routine_sig)}"

    cached = _cache.get(key)
    now_ts = time.monotonic()
    if cached and now_ts - cached[0] < _CACHE_TTL_SECONDS:
        paused_ids, llm_powered = cached[1], cached[2]
    else:
        paused_ids = await _llm_paused_ids(day, routines)
        llm_powered = paused_ids is not None
        if paused_ids is None:
            paused_ids = _fallback_paused_ids(routines)
        _cache[key] = (now_ts, paused_ids, llm_powered)

    kept = [p for p in patterns if p.pattern_id not in paused_ids]
    by_id = {r["pattern_id"]: r["description"] for r in routines}
    paused_records = [
        PausedRoutine(
            pattern_id=pid,
            description=by_id.get(pid, pid),
            reason=f"weekday-only routine paused for {day.label()}",
        )
        for pid in paused_ids
    ]

    adaptation = DayAdaptation(
        active=bool(paused_records),
        day_type=day.day_type,
        festival=day.festival,
        llm_powered=llm_powered,
        kept_count=len(kept),
        paused=paused_records,
    )
    return kept, adaptation
