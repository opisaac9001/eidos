"""Deterministic projection for goals, commitments, calendar entries and objects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
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
    request_id: str | None = None
    goal_id: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarEntry:
    schedule_id: str
    title: str
    starts_at: str
    location_id: str
    status: str = "scheduled"
    reason: str | None = None
    ends_at: str | None = None
    actor_id: str | None = None
    action: str | None = None
    target_id: str | None = None
    commitment_id: str | None = None
    goal_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorldObject:
    object_id: str
    name: str
    owner_id: str
    custodian_id: str
    location_id: str
    condition: str


@dataclass(frozen=True, slots=True)
class Intention:
    intention_id: str
    actor_id: str
    action: str
    motivation: str
    priority: float
    goal_id: str | None = None
    target_id: str | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class PlanningState:
    goals: dict[str, Goal] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    calendar: dict[str, CalendarEntry] = field(default_factory=dict)
    objects: dict[str, WorldObject] = field(default_factory=dict)
    intentions: dict[str, Intention] = field(default_factory=dict)

    def apply(self, event: DomainEvent) -> PlanningState:
        payload = event.payload
        goals, commitments = dict(self.goals), dict(self.commitments)
        calendar, objects = dict(self.calendar), dict(self.objects)
        intentions = dict(self.intentions)
        match event.kind:
            case "goal.activated":
                goal_id = _required(payload, "goal_id")
                if goal_id in goals:
                    raise ValueError("Goal already exists")
                goals[goal_id] = Goal(goal_id, _required(payload, "title"))
            case "goal.achieved":
                goal = _existing(goals, payload, "goal_id")
                linked_commitments = [
                    item for item in commitments.values() if item.goal_id == goal.goal_id
                ]
                commitment_evidence = linked_commitments or [
                    item for item in commitments.values() if item.goal_id is None
                ]
                if goal.progress < 1 and not any(
                    item.status == "fulfilled" for item in commitment_evidence
                ):
                    raise ValueError("Goal needs completed progress or an accomplished commitment")
                goals[goal.goal_id] = replace(goal, status="achieved", progress=1.0)
            case "goal.progressed":
                goal = _existing(goals, payload, "goal_id")
                if goal.status != "active":
                    raise ValueError("Only active goals can progress")
                delta = payload.get("progress_delta")
                if (
                    isinstance(delta, bool)
                    or not isinstance(delta, (int, float))
                    or not 0 < delta <= 0.5
                ):
                    raise ValueError("Goal progress must be greater than zero and at most 0.5")
                goals[goal.goal_id] = replace(goal, progress=min(1.0, goal.progress + float(delta)))
            case "goal.blocked":
                goal = _existing(goals, payload, "goal_id")
                if goal.status != "active":
                    raise ValueError("Only active goals can become blocked")
                goals[goal.goal_id] = replace(goal, status="blocked")
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
                    request_id=_optional(payload, "request_id"),
                    goal_id=_optional(payload, "goal_id"),
                )
            case "commitment.fulfilled":
                commitment = _existing(commitments, payload, "commitment_id")
                if commitment.status != "active":
                    raise ValueError("Only active commitments can be fulfilled")
                linked_entries = [
                    item
                    for item in calendar.values()
                    if item.commitment_id == commitment.commitment_id
                ]
                schedule_evidence = linked_entries or [
                    item for item in calendar.values() if item.commitment_id is None
                ]
                if not any(item.status == "completed" for item in schedule_evidence):
                    raise ValueError("Commitment requires completed scheduled work")
                commitments[commitment.commitment_id] = replace(commitment, status="fulfilled")
            case "commitment.missed":
                commitment = _existing(commitments, payload, "commitment_id")
                if commitment.status != "active":
                    raise ValueError("Only active commitments can be missed")
                missed_at = datetime.fromisoformat(_required(payload, "simulated_at"))
                if missed_at <= datetime.fromisoformat(commitment.due_at):
                    raise ValueError("A commitment cannot be missed before its deadline")
                commitments[commitment.commitment_id] = replace(commitment, status="missed")
            case "schedule.created":
                schedule_id = _required(payload, "schedule_id")
                if schedule_id in calendar:
                    raise ValueError("Schedule entry already exists")
                calendar[schedule_id] = CalendarEntry(
                    schedule_id,
                    _required(payload, "title"),
                    _required(payload, "starts_at"),
                    _required(payload, "location_id"),
                    ends_at=_optional(payload, "ends_at"),
                    actor_id=_optional(payload, "actor_id"),
                    action=_optional(payload, "action"),
                    target_id=_optional(payload, "target_id"),
                    commitment_id=_optional(payload, "commitment_id"),
                    goal_id=_optional(payload, "goal_id"),
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
                    entry,
                    status="scheduled",
                    starts_at=_required(payload, "starts_at"),
                    ends_at=_optional(payload, "ends_at") or entry.ends_at,
                )
            case "schedule.completed":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status != "scheduled":
                    raise ValueError("Only scheduled work can complete")
                calendar[entry.schedule_id] = replace(entry, status="completed")
            case "schedule.failed":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status not in {"scheduled", "interrupted"}:
                    raise ValueError("Only unfinished scheduled work can fail")
                calendar[entry.schedule_id] = replace(
                    entry, status="failed", reason=_required(payload, "reason")
                )
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
            case "intention.adopted":
                intention_id = _required(payload, "intention_id")
                if intention_id in intentions:
                    raise ValueError("Intention already exists")
                priority = payload.get("priority")
                if not isinstance(priority, (int, float)) or isinstance(priority, bool):
                    raise ValueError("priority is required")
                intentions[intention_id] = Intention(
                    intention_id=intention_id,
                    actor_id=_required(payload, "actor_id"),
                    action=_required(payload, "action"),
                    motivation=_required(payload, "motivation"),
                    priority=float(priority),
                    goal_id=_optional(payload, "goal_id"),
                    target_id=_optional(payload, "target_id"),
                )
            case "intention.completed":
                intention = _existing(intentions, payload, "intention_id")
                if intention.status != "active":
                    raise ValueError("Only active intentions can complete")
                intentions[intention.intention_id] = replace(intention, status="completed")
            case "intention.abandoned":
                intention = _existing(intentions, payload, "intention_id")
                if intention.status != "active":
                    raise ValueError("Only active intentions can be abandoned")
                intentions[intention.intention_id] = replace(intention, status="abandoned")
        return PlanningState(goals, commitments, calendar, objects, intentions)


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


def _optional(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be null or a non-empty string")
    return value


def _existing(collection: dict[str, T], payload: Mapping[str, Any], key: str) -> T:
    identifier = _required(payload, key)
    if identifier not in collection:
        raise ValueError(f"Unknown {key}")
    return collection[identifier]
