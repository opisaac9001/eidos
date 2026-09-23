"""Execute accepted trips over elapsed time, never invent a past departure."""

from datetime import datetime
from typing import Sequence

from eidos.application.activity_execution import _timeline
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.scenes import project_scenes
from eidos.domain.state import replay_state
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import WorldCatalog


def current_journey(history: Sequence[DomainEvent]) -> DomainEvent | None:
    closed = {e.payload.get("journey_id") for e in history if e.kind == "pathos.travel_arrived"}
    return next(
        (
            e
            for e in reversed(history)
            if e.kind == "pathos.travel_started" and str(e.event_id) not in closed
        ),
        None,
    )


def journey_context(
    history: Sequence[DomainEvent], now: datetime, catalog: WorldCatalog
) -> dict[str, object] | None:
    journey = current_journey(history)
    if journey is None:
        return None
    p = journey.payload
    start, end = (datetime.fromisoformat(str(p[key])) for key in ("depart_at", "arrive_at"))
    return {
        "origin_id": p["origin_id"],
        "destination_id": p["destination_id"],
        "origin": catalog.location_name(str(p["origin_id"])),
        "destination": catalog.location_name(str(p["destination_id"])),
        "depart_at": p["depart_at"],
        "arrive_at": p["arrive_at"],
        "remaining_minutes": max(0, (end - now).total_seconds() / 60),
        "progress": max(
            0, min(1, (now - start).total_seconds() / max(1, (end - start).total_seconds()))
        ),
        "schedule_id": p["schedule_id"],
        "action_authority": False,
    }


def journey_window_events(
    history: Sequence[DomainEvent],
    planning: PlanningState,
    catalog: WorldCatalog,
    since: datetime,
    now: datetime,
) -> list[DomainEvent]:
    if since.utcoffset() is None or now.utcoffset() is None or now < since:
        raise ValueError("Journeys require a forward, timezone-aware interval")
    points = {since, now}
    entries = [
        e for e in planning.calendar.values() if e.status == "scheduled" and e.actor_id == "pathos"
    ]
    if not entries and current_journey(history) is None:
        return []
    # Test all route-sized departure boundaries. The actual origin is checked at
    # execution; these times grant no action or presence by themselves.
    for entry in entries:
        start = datetime.fromisoformat(entry.starts_at)
        if start <= now:
            points.add(max(since, start))
        for origin in catalog.places:
            try:
                at = start - route_duration(origin, entry.location_id, catalog.route_minutes)
            except ValueError:
                continue
            if since <= at <= now:
                points.add(at)
    for at, _, event in _timeline(history, now):
        if since <= at and event.kind in {
            "sleep.ended",
            "scene.ended",
            "scene.interrupted",
            "pathos.moved",
            "incident.response_completed",
            "incident.response_abandoned",
        }:
            points.add(at)
    output: list[DomainEvent] = []
    active = current_journey(history)
    if active:
        arrival = datetime.fromisoformat(str(active.payload["arrive_at"]))
        if arrival <= now:
            points.add(max(since, arrival))
    while points:
        at = min(points)
        points.remove(at)
        visible = [e for _, _, e in _timeline([*history, *output], at)]
        state = replay_state(visible)
        active = current_journey(visible)
        if active:
            arrival = datetime.fromisoformat(str(active.payload["arrive_at"]))
            if at >= arrival:
                arrived = DomainEvent(
                    "pathos.travel_arrived",
                    "pathos",
                    {
                        **active.payload,
                        "journey_id": str(active.event_id),
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=active.event_id,
                    correlation_id=active.correlation_id,
                )
                moved = DomainEvent(
                    "pathos.moved",
                    "pathos",
                    {
                        "location_id": active.payload["destination_id"],
                        "from_location_id": active.payload["origin_id"],
                        "journey_id": str(active.event_id),
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=arrived.event_id,
                    correlation_id=active.correlation_id,
                )
                output.extend((arrived, moved))
                state = state.apply(moved)
            else:
                continue
        if not state.awake or state.location_id == "in_transit":
            continue
        resolved = {
            e.payload.get("incident_id")
            for e in visible
            if e.kind in {"incident.response_completed", "incident.response_abandoned"}
        }
        if any(
            e.kind == "incident.response_started" and e.payload.get("incident_id") not in resolved
            for e in visible
        ):
            continue
        if any(
            s.status in {"active", "paused"} and "pathos" in {s.initiator_id, s.partner_id}
            for s in project_scenes(visible).scenes.values()
        ):
            continue
        for entry in sorted(
            entries, key=lambda e: (e.starts_at, e.commitment_id is None, e.schedule_id)
        ):
            end = datetime.fromisoformat(entry.ends_at or entry.starts_at)
            if end < at or (end == at and entry.ends_at) or state.location_id == entry.location_id:
                continue
            # A plan created later in this batch cannot authorize an earlier trip.
            origins = [
                e
                for e in history
                if e.kind in {"schedule.created", "schedule.rescheduled"}
                and e.payload.get("schedule_id") == entry.schedule_id
            ]
            if origins and origins[-1] not in visible:
                continue
            try:
                duration = route_duration(
                    state.location_id, entry.location_id, catalog.route_minutes
                )
            except ValueError:
                continue
            if at < datetime.fromisoformat(entry.starts_at) - duration:
                continue
            # Do not walk away from other ongoing accepted work.
            if any(
                other.schedule_id != entry.schedule_id
                and datetime.fromisoformat(other.starts_at)
                <= at
                < datetime.fromisoformat(other.ends_at or other.starts_at)
                for other in entries
            ):
                continue
            arrival = at + duration
            departure = DomainEvent(
                "pathos.travel_started",
                "pathos",
                {
                    "origin_id": state.location_id,
                    "destination_id": entry.location_id,
                    "depart_at": at.isoformat(),
                    "arrive_at": arrival.isoformat(),
                    "schedule_id": entry.schedule_id,
                    "simulated_at": at.isoformat(),
                },
                causation_id=origins[-1].event_id if origins else None,
                correlation_id=entry.schedule_id,
            )
            output.append(departure)
            if arrival <= now:
                points.add(arrival)
            break
    return output
