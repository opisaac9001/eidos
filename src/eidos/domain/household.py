"""Replayable domestic load and completed household work."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent

HOUSEHOLD_TASKS = ("dishes", "laundry", "tidying", "paperwork")


@dataclass(frozen=True, slots=True)
class HouseholdTask:
    task_id: str
    task_kind: str
    amount: float
    text: str
    completed_at: str


@dataclass(frozen=True, slots=True)
class HouseholdState:
    established: bool = False
    loads: dict[str, float] = field(default_factory=lambda: {task: 0.0 for task in HOUSEHOLD_TASKS})
    processed_sources: frozenset[str] = frozenset()
    completed: dict[str, HouseholdTask] = field(default_factory=dict)

    def apply(self, event: DomainEvent) -> HouseholdState:
        loads = dict(self.loads)
        processed = set(self.processed_sources)
        completed = dict(self.completed)
        if event.kind == "household.established":
            if self.established:
                raise ValueError("Household state can only be established once")
            _aware(event, "simulated_at")
            for task in HOUSEHOLD_TASKS:
                loads[task] = _level(event, task)
            return HouseholdState(True, loads, frozenset(), completed)
        if event.kind == "household.load_added":
            if not self.established:
                raise ValueError("Household load requires established household state")
            change_id = _required(event, "change_id")
            if change_id in processed:
                raise ValueError("Household load source was already applied")
            task = _task(event)
            before = _level(event, "from_load")
            if abs(before - loads[task]) > 1e-9:
                raise ValueError("Household load does not match prior state")
            amount = _amount(event, maximum=0.3)
            after = _level(event, "load")
            if abs(after - min(1.0, before + amount)) > 1e-9:
                raise ValueError("Household load result does not match its addition")
            source_id = event.payload.get("source_event_id")
            if source_id is not None:
                if not isinstance(source_id, str) or not source_id:
                    raise ValueError("Household source event ID must be a string")
                if event.causation_id is None or source_id != str(event.causation_id):
                    raise ValueError("Household load must cite its causal source")
            _aware(event, "simulated_at")
            loads[task] = after
            processed.add(change_id)
            return HouseholdState(True, loads, frozenset(processed), completed)
        if event.kind == "household.task_completed":
            if not self.established:
                raise ValueError("Household work requires established household state")
            task_id = _required(event, "task_id")
            if task_id in completed:
                raise ValueError("Household task was already completed")
            task = _task(event)
            before = _level(event, "from_load")
            if abs(before - loads[task]) > 1e-9 or before <= 0:
                raise ValueError("Household task load does not match prior state")
            amount = _amount(event, maximum=0.6)
            after = _level(event, "load")
            if abs(after - max(0.0, before - amount)) > 1e-9:
                raise ValueError("Household task result does not match completed work")
            if event.payload.get("location_id") != "home":
                raise ValueError("Household work must happen at home")
            completed_at = _aware(event, "simulated_at").isoformat()
            loads[task] = after
            completed[task_id] = HouseholdTask(
                task_id,
                task,
                amount,
                _required(event, "text"),
                completed_at,
            )
            return HouseholdState(True, loads, frozenset(processed), completed)
        return self


def project_household(events: Sequence[DomainEvent]) -> HouseholdState:
    state = HouseholdState()
    for event in events:
        state = state.apply(event)
    return state


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Household event requires {key}")
    return value


def _task(event: DomainEvent) -> str:
    task = _required(event, "task_kind")
    if task not in HOUSEHOLD_TASKS:
        raise ValueError("Unknown household task kind")
    return task


def _level(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"Household {key} must be between zero and one")
    return float(value)


def _amount(event: DomainEvent, *, maximum: float) -> float:
    value = event.payload.get("amount")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= maximum:
        raise ValueError(f"Household amount must be positive and no more than {maximum}")
    return float(value)


def _aware(event: DomainEvent, key: str) -> datetime:
    value = datetime.fromisoformat(_required(event, key))
    if value.utcoffset() is None:
        raise ValueError("Household time must be timezone-aware")
    return value
