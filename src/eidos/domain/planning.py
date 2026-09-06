"""Deterministic projection for goals, commitments, calendar entries and objects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, TypeVar

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    title: str
    status: str = "active"
    progress: float = 0.0


@dataclass(frozen=True, slots=True)
class Commitment:
    commitment_id: str
    title: str
    debtor_id: str
    creditor_id: str
    due_at: str
    status: str = "active"


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    schedule_id: str
    title: str
    starts_at: str
    location_id: str
    status: str = "scheduled"
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorldObject:
    object_id: str
    name: str
    owner_id: str
    custodian_id: str
    location_id: str
    condition: str


@dataclass(frozen=True, slots=True)
class PlanningState:
    goals: dict[str, Goal] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    calendar: dict[str, CalendarEntry] = field(default_factory=dict)
    objects: dict[str, WorldObject] = field(default_factory=dict)

    def apply(self, event: DomainEvent) -> PlanningState:
        payload = event.payload
        goals, commitments = dict(self.goals), dict(self.commitments)
        calendar, objects = dict(self.calendar), dict(self.objects)
        match event.kind:
            case "goal.activated":
                goal_id = _required(payload, "goal_id")
                if goal_id in goals:
                    raise ValueError("Goal already exists")
                goals[goal_id] = Goal(goal_id, _required(payload, "title"))
            case "goal.achieved":
                goal = _existing(goals, payload, "goal_id")
                if not any(item.status == "fulfilled" for item in commitments.values()):
                    raise ValueError("Goal needs an accomplished commitment")
                goals[goal.goal_id] = replace(goal, status="achieved", progress=1.0)
            case "commitment.created":
                commitment_id = _required(payload, "commitment_id")
                if commitment_id in commitments:
                    raise ValueError("Commitment already exists")
                commitments[commitment_id] = Commitment(
                    commitment_id,
                    _required(payload, "title"),
                    _required(payload, "debtor_id"),
                    _required(payload, "creditor_id"),
                    _required(payload, "due_at"),
                )
            case "commitment.fulfilled":
                commitment = _existing(commitments, payload, "commitment_id")
                if commitment.status != "active":
                    raise ValueError("Only active commitments can be fulfilled")
                if not any(item.status == "completed" for item in calendar.values()):
                    raise ValueError("Commitment requires completed scheduled work")
                commitments[commitment.commitment_id] = replace(commitment, status="fulfilled")
            case "schedule.created":
                schedule_id = _required(payload, "schedule_id")
                if schedule_id in calendar:
                    raise ValueError("Schedule entry already exists")
                calendar[schedule_id] = CalendarEntry(
                    schedule_id,
                    _required(payload, "title"),
                    _required(payload, "starts_at"),
                    _required(payload, "location_id"),
                )
            case "schedule.interrupted":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status != "scheduled":
                    raise ValueError("Only scheduled work can be interrupted")
                calendar[entry.schedule_id] = replace(
                    entry, status="interrupted", reason=_required(payload, "reason")
                )
            case "schedule.rescheduled":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status != "interrupted":
                    raise ValueError("Only interrupted work can be rescheduled")
                calendar[entry.schedule_id] = replace(
                    entry, status="scheduled", starts_at=_required(payload, "starts_at")
                )
            case "schedule.completed":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status != "scheduled":
                    raise ValueError("Only scheduled work can complete")
                calendar[entry.schedule_id] = replace(entry, status="completed")
            case "object.registered":
                object_id = _required(payload, "object_id")
                if object_id in objects:
                    raise ValueError("Object already exists")
                objects[object_id] = WorldObject(
                    object_id,
                    _required(payload, "name"),
                    _required(payload, "owner_id"),
                    _required(payload, "custodian_id"),
                    _required(payload, "location_id"),
                    _required(payload, "condition"),
                )
            case "object.condition_changed":
                item = _existing(objects, payload, "object_id")
                objects[item.object_id] = replace(item, condition=_required(payload, "condition"))
        return PlanningState(goals, commitments, calendar, objects)


def project_planning(events: list[DomainEvent]) -> PlanningState:
    state = PlanningState()
    for event in events:
        state = state.apply(event)
    return state


T = TypeVar("T")


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _existing(collection: dict[str, T], payload: Mapping[str, Any], key: str) -> T:
    identifier = _required(payload, key)
    if identifier not in collection:
        raise ValueError(f"Unknown {key}")
    return collection[identifier]
