"""Turn accepted place discoveries into feasible, self-directed exploration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Sequence

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import CalendarEntry, PlanningState, project_planning
from eidos.domain.routine import RoutineBeat
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog


def exploration_plan_events(
    history: Sequence[DomainEvent], simulated_at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    """Plan two visits to one unconsidered introduced place when time permits."""
    planning = project_planning(list(history))
    planned_sources = {
        str(event.payload["source_registration_id"])
        for event in history
        if event.kind == "goal.activated"
        and isinstance(event.payload.get("source_registration_id"), str)
    }
    registration = next(
        (
            event
            for event in history
            if event.kind == "world.place_registered" and str(event.event_id) not in planned_sources
        ),
        None,
    )
    if registration is None:
        return []
    place_id = str(registration.payload["entity_id"])
    place = catalog.places.get(place_id)
    if place is None:
        return []
    windows = _feasible_windows(planning, simulated_at, catalog, place_id, count=2)
    if len(windows) != 2:
        return []
    goal_id = f"explore-{place_id}"
    source_id = str(registration.event_id)
    common = {
        "source_registration_id": source_id,
        "simulated_at": simulated_at.isoformat(),
    }
    events: list[DomainEvent] = [
        DomainEvent(
            "goal.activated",
            "pathos",
            {
                **common,
                "goal_id": goal_id,
                "title": f"Get to know {place.name}",
                "motivation": f"Curiosity about {place.description.lower()}",
            },
            causation_id=registration.event_id,
            correlation_id=goal_id,
        )
    ]
    for number, starts_at in enumerate(windows, 1):
        schedule_id = f"{goal_id}-visit-{number}"
        events.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    **common,
                    "schedule_id": schedule_id,
                    "title": f"Explore {place.name}",
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                    "location_id": place_id,
                    "actor_id": "pathos",
                    "action": ActionKind.ATTEND.value,
                    "target_id": place_id,
                    "goal_id": goal_id,
                },
                causation_id=registration.event_id,
                correlation_id=goal_id,
            )
        )
    projected = planning
    for event in events:
        projected = projected.apply(event)
    for number, _ in enumerate(windows, 1):
        intention = resolve_intention(
            IntentionProposal(
                proposal_id=f"intend-{goal_id}-visit-{number}",
                intention_id=f"{goal_id}-visit-{number}-intention",
                actor_id="pathos",
                action=ActionKind.ATTEND,
                motivation=f"See enough of {place.name} to form an experience of it.",
                priority=0.45,
                expected_revision=len(history) + len(events),
                goal_id=goal_id,
                target_id=place_id,
            ),
            state=projected,
            actual_revision=len(history) + len(events),
            simulated_at=simulated_at,
        )
        events.extend(intention.events)
        for event in intention.events:
            projected = projected.apply(event)
    return events


def planned_activity_beat(
    planning: PlanningState, simulated_at: datetime, energy: float
) -> RoutineBeat | None:
    """Let an accepted calendar entry override loose routine at its start."""
    entries = sorted(
        (
            entry
            for entry in planning.calendar.values()
            if entry.status == "scheduled"
            and entry.actor_id == "pathos"
            and datetime.fromisoformat(entry.starts_at) == simulated_at
        ),
        key=lambda entry: (entry.commitment_id is None, entry.schedule_id),
    )
    if not entries:
        return None
    entry = entries[0]
    return RoutineBeat(
        simulated_at.hour,
        entry.location_id,
        f"Set out for the planned activity: {entry.title}.",
        max(0.15, energy - 0.04),
        entry.action or "planned_activity",
    )


def _feasible_windows(
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
