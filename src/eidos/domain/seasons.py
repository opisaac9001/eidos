"""Deterministic simulation seasons recorded as replayable world facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of


@dataclass(frozen=True, slots=True)
class SeasonState:
    name: str
    since: str


def season_for(at: datetime) -> str:
    if at.utcoffset() is None:
        raise ValueError("Season time must be timezone-aware")
    month = at.month
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "autumn"


def project_season(events: Sequence[DomainEvent]) -> SeasonState | None:
    state = None
    for event in events_of(events, "world.season_changed"):
        name = event.payload.get("season")
        since = event.payload.get("simulated_at")
        if name not in {"winter", "spring", "summer", "autumn"}:
            raise ValueError("Unknown season")
        if not isinstance(since, str):
            raise ValueError("Season change requires simulation time")
        parsed = datetime.fromisoformat(since)
        if parsed.utcoffset() is None:
            raise ValueError("Season change time must be timezone-aware")
        state = SeasonState(str(name), parsed.isoformat())
    return state


def season_change_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    current = season_for(at)
    previous = project_season(history)
    if previous is not None and previous.name == current:
        return []
    changed = DomainEvent(
        "world.season_changed",
        "pathos",
        {
            "season": current,
            "previous_season": previous.name if previous else None,
            "simulated_at": at.isoformat(),
            "source": "simulation-calendar-v1",
        },
        correlation_id=f"season-{current}-{at:%Y-%m}",
    )
    return [changed]
