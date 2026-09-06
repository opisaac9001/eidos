"""Deterministic projection for goals, commitments, calendar entries and objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping, TypeVar

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class Goal:
    goal_id: str
    title: str
    motivation: str | None = None
    status: str = "active"
    progress: float = 0.0
    reason: str | None = None


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
    terms_version: int = 1


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
    resource_id: str | None = None
    companion_id: str | None = None
    activity_type: str | None = None
    source_proposal_id: str | None = None
    intention_id: str | None = None
    goal_progress_delta: float | None = None


@dataclass(frozen=True, slots=True)
class WorldObject:
    object_id: str
    name: str
    owner_id: str
    custodian_id: str
    location_id: str
    condition: str
    quantity: int | None = None
    reorder_at: int | None = None
    unit: str | None = None


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

    def materialized_state(self) -> Mapping[str, Any]:
        """Return a disposable JSON-safe snapshot of this replay projection."""
        return {
            "goals": [asdict(value) for value in self.goals.values()],
            "commitments": [asdict(value) for value in self.commitments.values()],
            "calendar": [asdict(value) for value in self.calendar.values()],
            "objects": [asdict(value) for value in self.objects.values()],
            "intentions": [asdict(value) for value in self.intentions.values()],
        }

    @classmethod
    def from_materialized_state(cls, raw: Mapping[str, Any]) -> PlanningState:
        """Restore a checked disposable snapshot; event history remains authoritative."""
        expected = {"goals", "commitments", "calendar", "objects", "intentions"}
        if set(raw) != expected:
            raise ValueError("Materialized planning fields do not match schema v1")
        object_records = raw["objects"]
        if isinstance(object_records, list):
            object_records = [
                {**value, "quantity": None, "reorder_at": None, "unit": None}
                if isinstance(value, dict)
                and set(value)
                == {"object_id", "name", "owner_id", "custodian_id", "location_id", "condition"}
                else value
                for value in object_records
            ]
        calendar_records = raw["calendar"]
        if isinstance(calendar_records, list):
            calendar_records = [
                {
                    "companion_id": None,
                    "activity_type": None,
                    "source_proposal_id": None,
                    "intention_id": None,
                    "goal_progress_delta": None,
                    **value,
                }
                if isinstance(value, dict)
                else value
                for value in calendar_records
            ]
        state = cls(
            goals=_restore_records(raw["goals"], Goal, "goal_id"),
            commitments=_restore_records(raw["commitments"], Commitment, "commitment_id"),
            calendar=_restore_records(calendar_records, CalendarEntry, "schedule_id"),
            objects=_restore_records(object_records, WorldObject, "object_id"),
            intentions=_restore_records(raw["intentions"], Intention, "intention_id"),
        )
        _validate_materialized_planning(state)
        return state

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
                goals[goal_id] = Goal(
                    goal_id,
                    _required(payload, "title"),
                    motivation=_optional(payload, "motivation"),
                )
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
            case "goal.abandoned":
                goal = _existing(goals, payload, "goal_id")
                if goal.status not in {"active", "blocked"}:
                    raise ValueError("Only unfinished goals can be abandoned")
                if any(
                    item.goal_id == goal.goal_id and item.status == "active"
                    for item in commitments.values()
                ):
                    raise ValueError("An active external commitment cannot be abandoned")
                if any(
                    item.goal_id == goal.goal_id and item.status in {"scheduled", "interrupted"}
                    for item in calendar.values()
                ):
                    raise ValueError("Goal schedules must be resolved before abandonment")
                if any(
                    item.goal_id == goal.goal_id and item.status == "active"
                    for item in intentions.values()
                ):
                    raise ValueError("Goal intentions must be resolved before abandonment")
                goals[goal.goal_id] = replace(
                    goal, status="abandoned", reason=_required(payload, "reason")
                )
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
            case "commitment.renegotiated":
                commitment = _existing(commitments, payload, "commitment_id")
                if commitment.status != "active":
                    raise ValueError("Only active commitments can be renegotiated")
                if _required(payload, "actor_id") != commitment.creditor_id:
                    raise ValueError("Only the creditor can accept changed commitment terms")
                if _required(payload, "from_due_at") != commitment.due_at:
                    raise ValueError("Renegotiation does not match the current deadline")
                version = payload.get("terms_version")
                if version != commitment.terms_version + 1:
                    raise ValueError("Commitment terms version must advance exactly once")
                due_at = _required(payload, "due_at")
                if datetime.fromisoformat(due_at).utcoffset() is None:
                    raise ValueError("Commitment deadline needs a timezone")
                commitments[commitment.commitment_id] = replace(
                    commitment, due_at=due_at, terms_version=int(version)
                )
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
                    resource_id=_optional(payload, "resource_id"),
                    companion_id=_optional(payload, "companion_id"),
                    activity_type=_optional(payload, "activity_type"),
                    source_proposal_id=_optional(payload, "source_proposal_id"),
                    intention_id=_optional(payload, "intention_id"),
                    goal_progress_delta=_optional_bounded_float(payload, "goal_progress_delta"),
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
            case "schedule.retimed":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status not in {"scheduled", "interrupted"}:
                    raise ValueError("Only unfinished work can be retimed")
                if _required(payload, "from_starts_at") != entry.starts_at:
                    raise ValueError("Retiming does not match the current schedule")
                starts_at = _required(payload, "starts_at")
                ends_at = _required(payload, "ends_at")
                start, end = datetime.fromisoformat(starts_at), datetime.fromisoformat(ends_at)
                if start.utcoffset() is None or end.utcoffset() is None or end <= start:
                    raise ValueError("Retimed work needs a valid aware interval")
                calendar[entry.schedule_id] = replace(
                    entry,
                    status="scheduled",
                    reason=_required(payload, "reason"),
                    starts_at=starts_at,
                    ends_at=ends_at,
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
            case "schedule.cancelled":
                entry = _existing(calendar, payload, "schedule_id")
                if entry.status not in {"scheduled", "interrupted"}:
                    raise ValueError("Only unfinished scheduled work can be cancelled")
                calendar[entry.schedule_id] = replace(
                    entry, status="cancelled", reason=_required(payload, "reason")
                )
            case "object.registered":
                object_id = _required(payload, "object_id")
                if object_id in objects:
                    raise ValueError("Object already exists")
                item = WorldObject(
                    object_id,
                    _required(payload, "name"),
                    _required(payload, "owner_id"),
                    _required(payload, "custodian_id"),
                    _required(payload, "location_id"),
                    _required(payload, "condition"),
                    _optional_nonnegative_int(payload, "quantity"),
                    _optional_nonnegative_int(payload, "reorder_at"),
                    _optional(payload, "unit"),
                )
                _validate_object_stock(item)
                objects[object_id] = item
            case "object.condition_changed":
                item = _existing(objects, payload, "object_id")
                objects[item.object_id] = replace(item, condition=_required(payload, "condition"))
            case "object.stock_changed":
                item = _existing(objects, payload, "object_id")
                if item.quantity is None:
                    raise ValueError("Only quantified objects can change stock")
                previous = payload.get("from_quantity")
                quantity = payload.get("quantity")
                if previous != item.quantity:
                    raise ValueError("Stock change does not match current quantity")
                if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                    raise ValueError("Object stock must be a non-negative integer")
                objects[item.object_id] = replace(item, quantity=quantity)
            case "object.custody_changed":
                item = _existing(objects, payload, "object_id")
                if item.custodian_id != _required(payload, "from_custodian_id"):
                    raise ValueError("Object custody source does not match current state")
                objects[item.object_id] = replace(
                    item, custodian_id=_required(payload, "to_custodian_id")
                )
            case "object.ownership_changed":
                item = _existing(objects, payload, "object_id")
                if item.owner_id != _required(payload, "from_owner_id"):
                    raise ValueError("Object ownership source does not match current state")
                objects[item.object_id] = replace(item, owner_id=_required(payload, "to_owner_id"))
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


def _restore_records(raw: Any, record_type: type[T], id_field: str) -> dict[str, T]:
    if not isinstance(raw, list):
        raise ValueError("Materialized planning collection must be an ordered list")
    expected_fields = set(getattr(record_type, "__dataclass_fields__"))
    restored: dict[str, T] = {}
    for value in raw:
        key = value.get(id_field) if isinstance(value, dict) else None
        if (
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, dict)
            or set(value) != expected_fields
            or key in restored
        ):
            raise ValueError("Materialized planning record does not match schema v1")
        try:
            restored[key] = record_type(**value)
        except TypeError:
            raise ValueError("Materialized planning record is invalid") from None
    return restored


def _validate_materialized_planning(state: PlanningState) -> None:
    def text(value: object, *, optional: bool = False) -> bool:
        return (optional and value is None) or isinstance(value, str) and bool(value.strip())

    for goal in state.goals.values():
        if (
            not all(text(value) for value in (goal.goal_id, goal.title, goal.status))
            or not text(goal.motivation, optional=True)
            or not text(goal.reason, optional=True)
            or isinstance(goal.progress, bool)
            or not isinstance(goal.progress, (int, float))
            or not 0 <= goal.progress <= 1
            or goal.status not in {"active", "blocked", "achieved", "abandoned"}
        ):
            raise ValueError("Materialized goal is invalid")
    for commitment in state.commitments.values():
        if (
            not all(
                text(value)
                for value in (
                    commitment.commitment_id,
                    commitment.title,
                    commitment.debtor_id,
                    commitment.creditor_id,
                    commitment.due_at,
                    commitment.status,
                )
            )
            or not all(
                text(value, optional=True) for value in (commitment.request_id, commitment.goal_id)
            )
            or commitment.status not in {"active", "fulfilled", "missed"}
            or isinstance(commitment.terms_version, bool)
            or not isinstance(commitment.terms_version, int)
            or commitment.terms_version < 1
        ):
            raise ValueError("Materialized commitment is invalid")
        _aware(commitment.due_at)
    for entry in state.calendar.values():
        if not all(
            text(value)
            for value in (entry.schedule_id, entry.title, entry.starts_at, entry.location_id)
        ) or not all(
            text(value, optional=True)
            for value in (
                entry.reason,
                entry.ends_at,
                entry.actor_id,
                entry.action,
                entry.target_id,
                entry.commitment_id,
                entry.goal_id,
                entry.resource_id,
            )
        ):
            raise ValueError("Materialized calendar entry is invalid")
        if entry.status not in {
            "scheduled",
            "interrupted",
            "completed",
            "failed",
            "cancelled",
        }:
            raise ValueError("Materialized calendar status is invalid")
        _aware(entry.starts_at)
        if entry.ends_at is not None:
            _aware(entry.ends_at)
    for item in state.objects.values():
        if not all(
            text(value)
            for value in (
                item.object_id,
                item.name,
                item.owner_id,
                item.custodian_id,
                item.location_id,
                item.condition,
            )
        ):
            raise ValueError("Materialized object is invalid")
        _validate_object_stock(item)
    for intention in state.intentions.values():
        if (
            not all(
                text(value)
                for value in (
                    intention.intention_id,
                    intention.actor_id,
                    intention.action,
                    intention.motivation,
                    intention.status,
                )
            )
            or not all(
                text(value, optional=True) for value in (intention.goal_id, intention.target_id)
            )
            or isinstance(intention.priority, bool)
            or not isinstance(intention.priority, (int, float))
            or not 0 <= intention.priority <= 1
            or intention.status not in {"active", "completed", "abandoned"}
        ):
            raise ValueError("Materialized intention is invalid")


def _aware(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Materialized planning time is invalid") from None
    if parsed.utcoffset() is None:
        raise ValueError("Materialized planning time must be timezone-aware")


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


def _optional_bounded_float(payload: Mapping[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 0.5:
        raise ValueError(f"{key} must be greater than zero and at most 0.5")
    return float(value)


def _optional_nonnegative_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be null or a non-negative integer")
    return value


def _validate_object_stock(item: WorldObject) -> None:
    fields = (item.quantity, item.reorder_at, item.unit)
    if all(value is None for value in fields):
        return
    if (
        item.quantity is None
        or item.reorder_at is None
        or not isinstance(item.unit, str)
        or not item.unit.strip()
    ):
        raise ValueError("Quantified objects need quantity, reorder threshold, and unit")


def _existing(collection: dict[str, T], payload: Mapping[str, Any], key: str) -> T:
    identifier = _required(payload, key)
    if identifier not in collection:
        raise ValueError(f"Unknown {key}")
    return collection[identifier]
