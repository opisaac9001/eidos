"""Ordinary, replayable nourishment driven by bodily pressure and opportunity."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.state import PathosState

PROVISIONS_ID = "household-provisions"

_MEAL_WINDOWS = {
    "breakfast": range(7, 10),
    "lunch": range(12, 15),
    "evening_meal": range(18, 22),
}

_DESCRIPTIONS = {
    "home": (
        "Made something simple and ate at the kitchen table.",
        "Put together a modest meal from what was in the kitchen.",
        "Ate quietly at home and let the pause restore some energy.",
    ),
    "cafe": (
        "Ate something simple at Juniper Café.",
        "Paused for an unhurried bite at the café.",
        "Found a small table and ate before continuing the day.",
    ),
    "away": (
        "Stopped to eat something brought along for the day.",
        "Found a place to sit and ate a simple packed meal.",
        "Paused what he was doing long enough to eat.",
    ),
}

_MEAL_ACTIVITY_TYPES = frozenset(
    {
        "breakfast",
        "cook_food",
        "eat_meal",
        "evening_meal",
        "lunch",
        "make_breakfast",
        "make_dinner",
        "make_lunch",
        "meal",
        "meal_preparation",
        "prepare_and_eat_meal",
        "prepare_food",
        "snack",
    }
)


def planned_meal_kind(entry: CalendarEntry) -> str | None:
    """Recognize an agency meal without treating any mention of food as eating."""
    activity_type = (entry.activity_type or "").casefold()
    title = entry.title.casefold()
    if activity_type not in _MEAL_ACTIVITY_TYPES:
        return None
    if "breakfast" in activity_type or "breakfast" in title:
        return "breakfast"
    if "lunch" in activity_type or "lunch" in title:
        return "lunch"
    if "dinner" in activity_type or "evening" in activity_type or "dinner" in title:
        return "evening_meal"
    if "snack" in activity_type or "snack" in title:
        return "snack"
    starts_at = datetime.fromisoformat(entry.starts_at)
    return next((name for name, hours in _MEAL_WINDOWS.items() if starts_at.hour in hours), "snack")


def pending_planned_meal(planning: PlanningState, at: datetime) -> bool:
    """Keep reflex nourishment from pre-empting a meal Patrick already chose."""
    horizon = at + timedelta(hours=1)
    return any(
        entry.status == "scheduled"
        and entry.actor_id in {None, "pathos"}
        and planned_meal_kind(entry) is not None
        and datetime.fromisoformat(entry.starts_at) <= horizon
        and datetime.fromisoformat(entry.ends_at or entry.starts_at) >= at
        for entry in planning.calendar.values()
    )


def nourishment_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    planning: PlanningState,
    available_pence: int,
    *,
    pathos_busy: bool,
    planned_schedule_id: str | None = None,
    planned_meal_kind: str | None = None,
) -> list[DomainEvent]:
    """Eat within a flexible meal window, or later when hunger becomes pressing."""
    if at.utcoffset() is None:
        raise ValueError("Meal time must be timezone-aware")
    if not state.awake or pathos_busy or state.hunger < 0.22:
        return []

    meal_kind = planned_meal_kind or next(
        (name for name, hours in _MEAL_WINDOWS.items() if at.hour in hours), None
    )
    urgent = state.hunger >= 0.78
    if meal_kind is None and not urgent:
        return []
    if meal_kind is None:
        meal_kind = "snack"

    date = at.date().isoformat()
    meal_id = (
        f"meal-plan:{planned_schedule_id}"
        if planned_schedule_id is not None
        else f"meal:{date}:{meal_kind}"
    )
    completed = {
        str(event.payload["meal_id"])
        for event in history
        if event.kind == "meal.eaten" and isinstance(event.payload.get("meal_id"), str)
    }
    if meal_id in completed:
        return []
    unavailable_here = any(
        event.kind == "meal.unavailable"
        and event.payload.get("meal_id") == meal_id
        and event.payload.get("location_id") == state.location_id
        for event in history
    )
    if unavailable_here:
        return []
    if meal_kind == "snack":
        recent = [
            datetime.fromisoformat(str(event.payload["simulated_at"]))
            for event in history
            if event.kind == "meal.eaten" and isinstance(event.payload.get("simulated_at"), str)
        ]
        if recent and at - max(recent) < timedelta(hours=4):
            return []

    reduction = 0.27 if meal_kind == "snack" else 0.46
    hunger_after = max(0.04, state.hunger - reduction)
    energy_after = min(1.0, state.energy + (0.04 if meal_kind == "snack" else 0.07))
    place = state.location_id if state.location_id in {"home", "cafe"} else "away"
    options = _DESCRIPTIONS[place]
    sample = sha256(f"{meal_id}:{state.location_id}".encode()).digest()[0]
    description = options[sample % len(options)]
    provisions = planning.objects.get(PROVISIONS_ID)
    uses_household_stock = state.location_id != "cafe"
    cannot_afford_cafe = not uses_household_stock and available_pence < 600
    if cannot_afford_cafe or (
        uses_household_stock and (provisions is None or not provisions.quantity)
    ):
        reason = (
            "The household balance could not cover a cafe meal."
            if cannot_afford_cafe
            else "There were no household provisions available here."
        )
        return [
            DomainEvent(
                "meal.unavailable",
                "pathos",
                {
                    "meal_id": meal_id,
                    "meal_kind": meal_kind,
                    "location_id": state.location_id,
                    "reason": reason,
                    "simulated_at": at.isoformat(),
                },
                correlation_id=meal_id,
            )
        ]
    meal = DomainEvent(
        "meal.eaten",
        "pathos",
        {
            "meal_id": meal_id,
            "meal_kind": meal_kind,
            "text": description,
            "location_id": state.location_id,
            "hunger_before": state.hunger,
            "hunger_after": hunger_after,
            "energy_after": energy_after,
            "provision_source": "household_stock" if uses_household_stock else "cafe_service",
            "provision_object_id": PROVISIONS_ID if uses_household_stock else None,
            "reason": (
                "he followed through on a meal he had chosen"
                if planned_schedule_id is not None
                else "hunger became difficult to ignore"
                if urgent
                else "hunger and a free moment aligned"
            ),
            "source_schedule_id": planned_schedule_id,
            "simulated_at": at.isoformat(),
        },
        correlation_id=meal_id,
    )
    if not uses_household_stock or provisions is None or provisions.quantity is None:
        return [meal]
    stock = DomainEvent(
        "object.stock_changed",
        "pathos",
        {
            "object_id": PROVISIONS_ID,
            "from_quantity": provisions.quantity,
            "quantity": provisions.quantity - 1,
            "reason": "One meal portion was actually eaten.",
            "simulated_at": at.isoformat(),
        },
        causation_id=meal.event_id,
        correlation_id=meal_id,
    )
    return [meal, stock]


def provision_foundation_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Add owned starting provisions once without rewriting established worlds."""
    if any(
        event.kind == "object.registered" and event.payload.get("object_id") == PROVISIONS_ID
        for event in history
    ):
        return []
    return [
        DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": PROVISIONS_ID,
                "name": "Household provisions",
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "home",
                "condition": "usable",
                "quantity": 12,
                "reorder_at": 3,
                "unit": "meal portions",
                "simulated_at": at.isoformat(),
                "source": "starting-household-state-v1",
            },
            correlation_id="household-provisions",
        )
    ]
