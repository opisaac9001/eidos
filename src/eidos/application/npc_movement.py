"""Elapsed-time NPC movement and work; no stock hourly location itinerary."""

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import project_world_catalog


def npc_movement_events(history: Sequence[DomainEvent], now: datetime) -> list[DomainEvent]:
    if now.utcoffset() is None:
        raise ValueError("NPC movement needs timezone-aware time")
    output: list[DomainEvent] = []
    if not any(event.kind == "npc.simulation_started" for event in history):
        output.append(
            DomainEvent(
                "npc.simulation_started",
                "pathos",
                {
                    "simulated_at": now.isoformat(),
                    "schema_version": 2,
                },
            )
        )
    state = project_npcs([*history, *output], now)
    catalog = project_world_catalog(history)
    for actor_id, person in state.people.items():
        owned = [event for event in history if event.payload.get("actor_id") == actor_id]

        def emit(
            kind: str,
            payload: dict[str, object],
            cause: DomainEvent | None = None,
            at: datetime = now,
        ) -> DomainEvent:
            event = DomainEvent(
                kind,
                "pathos",
                {
                    "actor_id": actor_id,
                    "owner": actor_id,
                    "visibility": "private",
                    "simulated_at": at.isoformat(),
                    **payload,
                },
                causation_id=cause.event_id if cause else None,
                correlation_id=person.plan_id,
            )
            output.append(event)
            owned.append(event)
            return event

        last_needs = next(
            (event for event in reversed(owned) if event.kind == "npc.needs_changed"), None
        )
        elapsed = (
            (now - datetime.fromisoformat(str(last_needs.payload["simulated_at"]))).total_seconds()
            / 3600
            if last_needs
            else 0
        )
        if last_needs is None or elapsed >= 0.25:
            # Baseline rates are per elapsed hour, not per invocation.
            energy_rate = 0.035 if person.location_id == "home" else -0.025
            emit(
                "npc.needs_changed",
                {
                    "energy": max(0.0, min(1.0, person.energy + elapsed * energy_rate)),
                    "connection": max(0.0, person.connection - elapsed * 0.018),
                    "purpose": max(0.0, person.purpose - elapsed * 0.014),
                },
                last_needs,
            )

        journey = next(
            (event for event in reversed(owned) if event.kind == "npc.travel_started"), None
        )
        arrived = {event.payload.get("journey_id") for event in owned if event.kind == "npc.moved"}
        if journey is not None and str(journey.event_id) not in arrived:
            arrive_at = datetime.fromisoformat(str(journey.payload["arrive_at"]))
            if now < arrive_at:
                continue
            emit(
                "npc.moved",
                {
                    "location_id": journey.payload["destination_id"],
                    "journey_id": str(journey.event_id),
                    "plan_id": journey.payload["plan_id"],
                },
                journey,
                arrive_at,
            )
            person = project_npcs([*history, *output], now).people[actor_id]

        if person.plan_status != "active" or person.plan_id is None:
            continue
        plan = next(
            (
                event
                for event in reversed(owned)
                if event.kind == "npc.plan_created"
                and event.payload.get("plan_id") == person.plan_id
            ),
            None,
        )
        if plan is None:
            continue
        work = next(
            (
                event
                for event in reversed(owned)
                if event.kind == "npc.activity_started"
                and event.payload.get("plan_id") == person.plan_id
            ),
            None,
        )
        completed_in_time = (
            work is not None
            and person.plan_due_at is not None
            and datetime.fromisoformat(str(work.payload["ends_at"])) <= person.plan_due_at
        )
        if person.plan_due_at is not None and now > person.plan_due_at and not completed_in_time:
            expired = emit(
                "npc.plan_expired",
                {
                    "plan_id": person.plan_id,
                    "reason": "No completed activity before the chosen deadline",
                },
                plan,
            )
            if person.plan_goal_id is not None:
                emit(
                    "npc.goal_abandoned",
                    {"goal_id": person.plan_goal_id, "reason": "The supporting plan expired"},
                    expired,
                )
            continue
        if person.plan_scheduled_for is not None and now < person.plan_scheduled_for:
            continue
        destination = person.plan_location_id
        if destination is None or destination not in catalog.places:
            continue
        if person.location_id != destination:
            try:
                duration = route_duration(person.location_id, destination, catalog.route_minutes)
            except ValueError:
                continue
            # Depart when the choice is executed, never backdate travel to fake punctuality.
            emit(
                "npc.travel_started",
                {
                    "plan_id": person.plan_id,
                    "origin_id": person.location_id,
                    "destination_id": destination,
                    "depart_at": now.isoformat(),
                    "arrive_at": (now + duration).isoformat(),
                },
                plan,
            )
            continue
        started = next(
            (
                event
                for event in reversed(owned)
                if event.kind == "npc.activity_started"
                and event.payload.get("plan_id") == person.plan_id
            ),
            None,
        )
        if started is None:
            if not location_allows_interval(
                destination, now, now + timedelta(hours=1), catalog.opening_hours
            ):
                continue
            emit(
                "npc.activity_started",
                {
                    "plan_id": person.plan_id,
                    "location_id": destination,
                    "action": person.plan_action,
                    "ends_at": (now + timedelta(hours=1)).isoformat(),
                },
                plan,
            )
            continue
        ends_at = datetime.fromisoformat(str(started.payload["ends_at"]))
        if now < ends_at:
            continue
        activity = emit(
            "npc.activity_recorded",
            {
                "plan_id": person.plan_id,
                "location_id": destination,
                "action": person.plan_action,
                "activity": person.plan_title or "chosen activity",
            },
            started,
            ends_at,
        )
        latest = next(event for event in reversed(owned) if event.kind == "npc.needs_changed")
        levels = {key: float(latest.payload[key]) for key in ("energy", "connection", "purpose")}
        need = person.plan_need
        company = destination != "home" and any(
            other.actor_id != actor_id and other.location_id == destination
            for other in project_npcs([*history, *output], now).people.values()
        )
        if need in levels and (need != "connection" or company):
            levels[need] = min(1.0, levels[need] + 0.25)
            emit("npc.needs_changed", dict(levels), activity)
        completed = emit("npc.plan_completed", {"plan_id": person.plan_id}, activity, ends_at)
        if person.plan_goal_id is not None:
            emit("npc.goal_achieved", {"goal_id": person.plan_goal_id}, completed, ends_at)
    return output
