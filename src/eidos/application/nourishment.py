"""Ordinary, replayable nourishment driven by bodily pressure and opportunity."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState

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
    return [
        DomainEvent(
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
                "reason": (
                    "hunger became difficult to ignore"
                    if urgent
                    else "hunger and a free moment aligned"
                ),
                "simulated_at": at.isoformat(),
            },
            correlation_id=meal_id,
        )
    ]
