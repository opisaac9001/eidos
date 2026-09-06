"""Ordinary, replayable nourishment driven by bodily pressure and opportunity."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
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


def nourishment_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    planning: PlanningState,
    *,
    pathos_busy: bool,
) -> list[DomainEvent]:
    """Eat within a flexible meal window, or later when hunger becomes pressing."""
    if at.utcoffset() is None:
        raise ValueError("Meal time must be timezone-aware")
    if not state.awake or pathos_busy or state.hunger < 0.22:
        return []

    meal_kind = next((name for name, hours in _MEAL_WINDOWS.items() if at.hour in hours), None)
    urgent = state.hunger >= 0.78
    if meal_kind is None and not urgent:
        return []
    if meal_kind is None:
        meal_kind = "snack"

    date = at.date().isoformat()
    meal_id = f"meal:{date}:{meal_kind}"
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
    if uses_household_stock and (provisions is None or not provisions.quantity):
        return [
            DomainEvent(
                "meal.unavailable",
                "pathos",
                {
                    "meal_id": meal_id,
                    "meal_kind": meal_kind,
                    "location_id": state.location_id,
                    "reason": "There were no household provisions available here.",
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
                "hunger became difficult to ignore"
                if urgent
                else "hunger and a free moment aligned"
            ),
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
