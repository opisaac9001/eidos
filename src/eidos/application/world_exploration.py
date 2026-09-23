"""Turn accepted place discoveries into feasible, self-directed exploration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.routine import RoutineBeat
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog


def exploration_plan_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    catalog: WorldCatalog,
    planning: PlanningState | None = None,
) -> list[DomainEvent]:
    """Compatibility entry point: an intention does not authorize choosing a date.

    Explicit plans go through the agency/request resolution paths. Keep this
    function side-effect free for callers from older versions.
    """
    return []


def planned_activity_beat(
    planning: PlanningState,
    simulated_at: datetime,
    energy: float,
    *,
    current_location_id: str | None = None,
) -> RoutineBeat | None:
    """Let an accepted calendar entry override loose routine while it is happening."""
    entries = sorted(
        (
            entry
            for entry in planning.calendar.values()
            if entry.status == "scheduled"
            and entry.actor_id == "pathos"
            and datetime.fromisoformat(entry.starts_at)
            <= simulated_at
            < (
                datetime.fromisoformat(entry.ends_at)
                if entry.ends_at is not None
                else datetime.fromisoformat(entry.starts_at) + timedelta(microseconds=1)
            )
        ),
        key=lambda entry: (entry.commitment_id is None, entry.schedule_id),
    )
    if not entries:
        return None
    entry = entries[0]
    starts_at = datetime.fromisoformat(entry.starts_at)
    if simulated_at == starts_at:
        description = (
            f"Set out for the planned activity: {entry.title}."
            if current_location_id is not None and current_location_id != entry.location_id
            else f"Started the planned activity: {entry.title}."
        )
    else:
        description = f"Stayed with the planned activity: {entry.title}."
    return RoutineBeat(
        simulated_at.hour,
        entry.location_id,
        description,
        max(0.15, energy - 0.04),
        entry.action or "planned_activity",
    )


def feasible_activity_windows(
    planning: PlanningState,
    simulated_at: datetime,
    catalog: WorldCatalog,
    place_id: str,
    *,
    count: int,
) -> list[datetime]:
    place = catalog.places[place_id]
    chosen: list[datetime] = []
    day = (simulated_at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(14):
        for hour in range(place.opens_hour, place.closes_hour):
            candidate = day + timedelta(days=day_offset, hours=hour)
            if candidate <= simulated_at or not _fits(
                candidate, place_id, planning.calendar.values(), chosen, catalog
            ):
                continue
            chosen.append(candidate)
            break
        if len(chosen) == count:
            break
    return chosen


def _fits(
    starts_at: datetime,
    location_id: str,
    entries: Iterable[CalendarEntry],
    chosen: Sequence[datetime],
    catalog: WorldCatalog,
) -> bool:
    ends_at = starts_at + timedelta(hours=1)
    if not location_allows_interval(location_id, starts_at, ends_at, catalog.opening_hours):
        return False
    for selected in chosen:
        if starts_at < selected + timedelta(hours=1) and selected < ends_at:
            return False
    for entry in entries:
        if entry.status != "scheduled" or entry.actor_id not in {None, "pathos"}:
            continue
        other_start = datetime.fromisoformat(entry.starts_at)
        other_end = datetime.fromisoformat(entry.ends_at) if entry.ends_at else other_start
        if starts_at < other_end and other_start < ends_at:
            return False
        try:
            if other_end <= starts_at:
                if (
                    other_end
                    + route_duration(entry.location_id, location_id, catalog.route_minutes)
                    > starts_at
                ):
                    return False
            elif (
                ends_at <= other_start
                and ends_at + route_duration(location_id, entry.location_id, catalog.route_minutes)
                > other_start
            ):
                return False
        except ValueError:
            return False
    return True
