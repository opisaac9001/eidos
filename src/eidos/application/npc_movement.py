"""Elapsed-time NPC movement and work; no stock hourly location itinerary."""

from datetime import datetime, timedelta
from typing import Callable, Hashable, Sequence

from eidos.application.friends_lives import away_people
from eidos.domain.events import DomainEvent
from eidos.domain.folding import (
    IRREGULAR,
    GroupIndex,
    IncrementalFold,
    events_of,
    kind_index,
    str_match_key,
)
from eidos.domain.npcs import project_npcs
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import project_world_catalog


def npc_movement_events(history: Sequence[DomainEvent], now: datetime) -> list[DomainEvent]:
    if now.utcoffset() is None:
        raise ValueError("NPC movement needs timezone-aware time")
    output: list[DomainEvent] = []
    if not events_of(history, "npc.simulation_started"):
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
    state = project_npcs([*history, *output] if output else history, now)
    catalog = project_world_catalog(history)
    workdays = _employer_workdays(history)
    appointments = _appointments_with_pathos(history)
    own_events = _OWN_EVENTS(history)
    away = away_people(history)
    for actor_id, person in state.people.items():
        if actor_id in away:
            # They live somewhere else now; no more comings and goings around town.
            if person.location_id != "home":
                output.append(
                    DomainEvent(
                        "npc.moved",
                        "pathos",
                        {
                            "actor_id": actor_id,
                            "owner": actor_id,
                            "visibility": "private",
                            "simulated_at": now.isoformat(),
                            "location_id": "home",
                            "reason": "moved away",
                        },
                    )
                )
            continue
        owned = _Owned(own_events, actor_id)

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

        last_needs = owned.latest("npc.needs_changed")
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

        journey = owned.latest("npc.travel_started")
        arrived = {event.payload.get("journey_id") for event in owned.every("npc.moved")}
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

        meeting = next(
            (
                item
                for item in appointments.get(actor_id, ())
                if item[1] - timedelta(hours=2) < now < item[2]
            ),
            None,
        )
        if meeting is not None and person.location_id != "in-transit":
            schedule_id, starts, ends, place = meeting
            # Someone who agreed to meet him turns up, and stays until the time is over.
            if person.location_id == place:
                continue
            try:
                duration = route_duration(person.location_id, place, catalog.route_minutes)
            except ValueError:
                duration = None
            if duration is not None and now >= starts - duration - timedelta(hours=1):
                emit(
                    "npc.travel_started",
                    {
                        "plan_id": f"meet-{schedule_id}",
                        "origin_id": person.location_id,
                        "destination_id": place,
                        "depart_at": now.isoformat(),
                        "arrive_at": (now + duration).isoformat(),
                        "reason": "meeting Pathos as agreed",
                    },
                )
                continue

        workday = workdays.get((actor_id, now.date().isoformat()))
        if workday is not None and person.location_id != "in-transit":
            place, opens, closes = workday
            if opens <= now < closes:
                # The employer keeps the agreed hours: the workshop is open when the rota
                # says so, whatever else is on their mind.
                if person.location_id != place:
                    try:
                        duration = route_duration(person.location_id, place, catalog.route_minutes)
                    except ValueError:
                        continue
                    emit(
                        "npc.travel_started",
                        {
                            "plan_id": f"workday-{now.date().isoformat()}",
                            "origin_id": person.location_id,
                            "destination_id": place,
                            "depart_at": now.isoformat(),
                            "arrive_at": (now + duration).isoformat(),
                            "reason": "opening up for the agreed hours",
                        },
                    )
                continue
            if (
                closes <= now < closes + timedelta(hours=1)
                and person.location_id == place
                and person.plan_status != "active"
            ):
                try:
                    duration = route_duration(place, "home", catalog.route_minutes)
                except ValueError:
                    continue
                emit(
                    "npc.travel_started",
                    {
                        "plan_id": f"workday-{now.date().isoformat()}",
                        "origin_id": place,
                        "destination_id": "home",
                        "depart_at": now.isoformat(),
                        "arrive_at": (now + duration).isoformat(),
                        "reason": "closing up for the day",
                    },
                )
                continue
        if person.plan_status != "active" or person.plan_id is None:
            continue
        plan = owned.latest(
            "npc.plan_created",
            lambda event: event.payload.get("plan_id") == person.plan_id,
        )
        if plan is None:
            continue
        work = owned.latest(
            "npc.activity_started",
            lambda event: event.payload.get("plan_id") == person.plan_id,
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
        started = owned.latest(
            "npc.activity_started",
            lambda event: event.payload.get("plan_id") == person.plan_id,
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
        latest = owned.latest("npc.needs_changed")
        assert latest is not None  # emitted above when none was recorded yet
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


# The kinds of an NPC's own events that movement looks back over.
_OWN_KINDS = frozenset(
    {
        "npc.needs_changed",
        "npc.travel_started",
        "npc.moved",
        "npc.plan_created",
        "npc.activity_started",
    }
)


def _own_key(index: GroupIndex, event: DomainEvent) -> GroupIndex:
    key: Hashable = None
    if event.kind in _OWN_KINDS:
        actor = str_match_key(event.payload.get("actor_id"))
        key = None if actor is None else (actor, event.kind)
    return index.with_event(key, event)


# Events grouped by (actor, kind), maintained incrementally across ticks.
_OWN_EVENTS: IncrementalFold[GroupIndex] = IncrementalFold(GroupIndex, _own_key)


class _Owned:
    """An NPC's own events of the kinds movement reads, then those emitted for them now.

    Exactly the events whose ``actor_id`` equals the NPC's, in history order, without
    walking everything the NPC ever did.
    """

    def __init__(self, index: GroupIndex, actor_id: str) -> None:
        self._index = index
        self._actor_id = actor_id
        self._emitted: list[DomainEvent] = []

    def append(self, event: DomainEvent) -> None:
        self._emitted.append(event)

    def _recorded(self, kind: str) -> list[DomainEvent]:
        return [
            event
            for event in self._index.select((self._actor_id, kind), (IRREGULAR, kind))
            if event.payload.get("actor_id") == self._actor_id
        ]

    def every(self, kind: str) -> list[DomainEvent]:
        return [
            *self._recorded(kind),
            *(event for event in self._emitted if event.kind == kind),
        ]

    def latest(
        self, kind: str, where: Callable[[DomainEvent], bool] | None = None
    ) -> DomainEvent | None:
        for event in reversed(self._emitted):
            if event.kind == kind and (where is None or where(event)):
                return event
        if not self._index.has((IRREGULAR, kind)):
            return self._index.latest((self._actor_id, kind), where)
        return next(
            (event for event in reversed(self._recorded(kind)) if where is None or where(event)),
            None,
        )


def _employer_workdays(
    history: Sequence[DomainEvent],
) -> dict[tuple[str, str], tuple[str, datetime, datetime]]:
    """(employer, date) -> (place, opens, closes) for every shift under a live agreement."""
    index = kind_index(history)
    employers: dict[str, str] = {}
    for event in index.select("work.agreement_accepted", "work.agreement_ended"):
        if event.kind == "work.agreement_accepted":
            employers[str(event.payload.get("agreement_id"))] = str(
                event.payload.get("employer_id")
            )
        elif event.kind == "work.agreement_ended":
            employers.pop(str(event.payload.get("agreement_id")), None)
    days: dict[tuple[str, str], tuple[str, datetime, datetime]] = {}
    if not employers:
        return days
    for event in index.select("schedule.created"):
        employer = employers.get(str(event.payload.get("agreement_id")))
        if employer is None:
            continue
        starts = datetime.fromisoformat(str(event.payload["starts_at"]))
        ends = datetime.fromisoformat(str(event.payload.get("ends_at") or starts))
        days[(employer, starts.date().isoformat())] = (
            str(event.payload["location_id"]),
            starts - timedelta(minutes=30),
            ends + timedelta(minutes=30),
        )
    return days


_CLOSED = frozenset(
    {"schedule.cancelled", "schedule.failed", "schedule.completed", "schedule.interrupted"}
)


def _appointments_with_pathos(
    history: Sequence[DomainEvent],
) -> dict[str, list[tuple[str, datetime, datetime, str]]]:
    """person -> (schedule, starts, ends, place) for each open time agreed with Pathos."""
    agreed: dict[str, tuple[str, str]] = {}  # schedule -> (companion, place)
    open_times: dict[str, tuple[datetime, datetime]] = {}
    for event in kind_index(history).select(
        "schedule.created", "schedule.rescheduled", "schedule.retimed", *_CLOSED
    ):
        payload = event.payload
        schedule_id = str(payload.get("schedule_id"))
        if event.kind in _CLOSED:
            open_times.pop(schedule_id, None)
            continue
        if event.kind == "schedule.created":
            companion, place = payload.get("companion_id"), payload.get("location_id")
            if (
                not isinstance(companion, str)
                or payload.get("actor_id") != "pathos"
                or not isinstance(place, str)
            ):
                continue
            agreed[schedule_id] = (companion, place)
        elif schedule_id not in agreed:
            continue
        starts = datetime.fromisoformat(str(payload["starts_at"]))
        previous_end = open_times.get(schedule_id, (starts, starts))[1]
        raw_end = payload.get("ends_at")
        open_times[schedule_id] = (
            starts,
            datetime.fromisoformat(str(raw_end)) if raw_end else max(starts, previous_end),
        )
    meetings: dict[str, list[tuple[str, datetime, datetime, str]]] = {}
    for schedule_id, (starts, ends) in open_times.items():
        companion, place = agreed[schedule_id]
        meetings.setdefault(companion, []).append((schedule_id, starts, ends, place))
    return meetings
