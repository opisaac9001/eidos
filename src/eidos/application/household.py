"""Accumulate and resolve ordinary domestic work without scripting every day."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.household import HouseholdState
from eidos.domain.routine import RoutineBeat

_COMPLETION = {
    "dishes": (0.55, "Washed the accumulated dishes and reset the kitchen."),
    "laundry": (0.45, "Put a load of laundry through and folded what had dried."),
    "tidying": (0.4, "Put the loose objects and neglected corners of home back in order."),
    "paperwork": (0.35, "Sat down with the household post, receipts, and unfinished paperwork."),
}


def household_foundation_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    if any(event.kind == "household.established" for event in history):
        return []
    return [
        DomainEvent(
            "household.established",
            "pathos",
            {
                "dishes": 0.12,
                "laundry": 0.18,
                "tidying": 0.16,
                "paperwork": 0.08,
                "simulated_at": at.isoformat(),
                "reason": "Starting domestic state",
            },
            correlation_id="pathos-household",
        )
    ]


def household_load_events(
    history: Sequence[DomainEvent], state: HouseholdState, at: datetime
) -> list[DomainEvent]:
    """Add each source once and one small increment for each lived day."""
    if not state.established:
        return []
    output: list[DomainEvent] = []
    current = state
    date = at.date().isoformat()
    if at.hour == 7:
        for task, amount in (("laundry", 0.07), ("tidying", 0.05)):
            change_id = f"daily:{date}:{task}"
            if change_id not in current.processed_sources:
                event = _load_event(current, task, amount, change_id, at, "ordinary daily use")
                output.append(event)
                current = current.apply(event)
    established_index = max(
        index for index, event in enumerate(history) if event.kind == "household.established"
    )
    for source in history[established_index + 1 :]:
        source_id = str(source.event_id)
        mapping = _source_load(source)
        change_id = f"source:{source_id}"
        if mapping is None or change_id in current.processed_sources:
            continue
        task, amount, reason = mapping
        event = _load_event(
            current,
            task,
            amount,
            change_id,
            at,
            reason,
            source=source,
        )
        output.append(event)
        current = current.apply(event)
    return output


def household_adjusted_beat(
    beat: RoutineBeat,
    state: HouseholdState,
    *,
    protected: bool,
    already_completed_today: bool,
) -> tuple[RoutineBeat, str | None]:
    if protected or already_completed_today:
        return beat, None
    if beat.activity in {
        "breakfast",
        "morning_cafe",
        "work",
        "dinner",
        "bedtime",
        "incident_response",
    }:
        return beat, None
    task, load = max(state.loads.items(), key=lambda item: (item[1], item[0]))
    if load < 0.48:
        return beat, None
    _, text = _COMPLETION[task]
    return (
        RoutineBeat(beat.hour, "home", text, min(beat.energy, 0.66), f"household_{task}"),
        f"{task} had accumulated enough to need attention",
    )


def household_completion_events(
    state: HouseholdState, beat: RoutineBeat, at: datetime
) -> list[DomainEvent]:
    prefix = "household_"
    if not beat.activity.startswith(prefix) or beat.location_id != "home":
        return []
    task = beat.activity.removeprefix(prefix)
    if task not in _COMPLETION:
        return []
    amount, text = _COMPLETION[task]
    before = state.loads[task]
    actual = min(amount, before)
    task_id = f"household:{at.date().isoformat()}:{task}"
    if task_id in state.completed or actual <= 0:
        return []
    return [
        DomainEvent(
            "household.task_completed",
            "pathos",
            {
                "task_id": task_id,
                "task_kind": task,
                "from_load": before,
                "load": max(0.0, before - actual),
                "amount": actual,
                "text": text,
                "location_id": "home",
                "simulated_at": at.isoformat(),
            },
            correlation_id=task_id,
        )
    ]


def _source_load(source: DomainEvent) -> tuple[str, float, str] | None:
    if source.kind == "meal.eaten" and source.payload.get("location_id") == "home":
        return ("dishes", 0.14, "a meal was prepared and eaten at home")
    if source.kind == "delivery.received":
        return ("tidying", 0.06, "a delivered object entered the home")
    if source.kind == "finance.obligation_due":
        return ("paperwork", 0.1, "a household obligation needed filing")
    return None


def _load_event(
    state: HouseholdState,
    task: str,
    amount: float,
    change_id: str,
    at: datetime,
    reason: str,
    *,
    source: DomainEvent | None = None,
) -> DomainEvent:
    before = state.loads[task]
    payload: dict[str, object] = {
        "change_id": change_id,
        "task_kind": task,
        "from_load": before,
        "load": min(1.0, before + amount),
        "amount": amount,
        "reason": reason,
        "simulated_at": at.isoformat(),
    }
    if source is not None:
        payload["source_event_id"] = str(source.event_id)
    return DomainEvent(
        "household.load_added",
        "pathos",
        payload,
        causation_id=source.event_id if source is not None else None,
        correlation_id=source.correlation_id if source is not None else change_id,
    )
