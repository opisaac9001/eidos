"""How awake he feels, and what his body tells him, from how he has actually lived.

Not an energy bar that ticks down. Alertness follows the two-process model of sleep
(Borbély): sleep pressure builds the longer he's awake and a short night leaves a debt
that carries over, while the body clock adds its own rhythm (the low before dawn, the
slump after lunch, a second wind in the evening). People notice their body mostly when it
surprises them or has a cause, so sensations come up only then: a heavy head after a
short night, the after-lunch slump, a stiff back after a day at the bench, a rumbling
stomach hours after eating, cabin fever after a day indoors.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.work_rota import is_rota_shift
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

SENSED = "body.sensed"
NIGHT_NEEDED_HOURS = 8.0
# The body clock's own pull on alertness through the day, by hour (interpolated).
_RHYTHM = (
    -0.10, -0.15, -0.20, -0.25, -0.25, -0.20, -0.12, -0.05,
    0.02, 0.06, 0.08, 0.08, 0.05, 0.00, -0.06, -0.05,
    0.00, 0.03, 0.05, 0.06, 0.04, 0.00, -0.04, -0.07,
)  # fmt: skip


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def nights(history: Sequence[DomainEvent], at: datetime, count: int = 3) -> list[float]:
    """Hours slept in each of his last few nights, most recent first."""
    slept: list[float] = []
    ended: datetime | None = None
    for event in reversed(events_of(history, "sleep.started", "sleep.ended")[-12:]):
        when = _at(event)
        if when is None or when > at:
            continue
        if event.kind == "sleep.ended":
            ended = when
        elif ended is not None:
            slept.append((ended - when).total_seconds() / 3600)
            ended = None
            if len(slept) >= count:
                break
    return slept


def hours_awake(history: Sequence[DomainEvent], at: datetime) -> float:
    for event in reversed(events_of(history, "sleep.ended", "sleep.started")[-4:]):
        when = _at(event)
        if when is None or when > at:
            continue
        return (at - when).total_seconds() / 3600 if event.kind == "sleep.ended" else 0.0
    return max(0.0, at.hour - 7.0)


def body_clock(at: datetime) -> float:
    hour = at.hour + at.minute / 60
    low, high = _RHYTHM[int(hour) % 24], _RHYTHM[(int(hour) + 1) % 24]
    return low + (high - low) * (hour - int(hour))


def alertness(history: Sequence[DomainEvent], at: datetime) -> float:
    """0 (barely functioning) to 1 (wide awake), from his days and nights, not a meter."""
    awake = hours_awake(history, at)
    pressure = 1 - math.exp(-awake / 18.2)
    last = nights(history, at)
    debt = sum(
        max(0.0, NIGHT_NEEDED_HOURS - hours) * weight
        for hours, weight in zip(last, (1.0, 0.5, 0.25))
    )
    return round(max(0.05, min(1.0, 0.95 - 0.55 * pressure + body_clock(at) - 0.04 * debt)), 3)


def _sensed_today(history: Sequence[DomainEvent], at: datetime) -> set[str]:
    return {
        str(event.payload.get("sensation"))
        for event in events_of(history, SENSED)[-12:]
        if (when := _at(event)) is not None and when.date() == at.date()
    }


def body_sensation_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    hunger: float,
    weather: str | None,
) -> list[DomainEvent]:
    """At most one bodily sensation this hour, when there's a cause for it."""
    if not awake:
        return []
    already = _sensed_today(history, at)
    up = hours_awake(history, at)
    last_night = (nights(history, at, 1) or [NIGHT_NEEDED_HOURS])[0]
    now = alertness(history, at)
    candidates: list[tuple[str, str, float]] = []
    if up <= 3 and last_night < 6.5:
        candidates.append(
            (
                "heavy_head",
                f"Heavy-headed. Only got about {last_night:.0f} hours last night.",
                -0.25,
            )
        )
    meals = [when for event in events_of(history, "meal.eaten")[-6:] if (when := _at(event))]
    last_meal = max((when for when in meals if when <= at), default=None)
    if 13 <= at.hour <= 15 and last_meal is not None and at - last_meal <= timedelta(hours=3):
        candidates.append(("slump", "That after-lunch slump. Eyelids like lead.", -0.1))
    if hunger >= 0.7 and last_meal is not None and at - last_meal >= timedelta(hours=5):
        candidates.append(
            ("hungry", f"Stomach's rumbling. Haven't eaten since {last_meal:%H:%M}.", -0.15)
        )
    worked = [
        event
        for event in events_of(history, "activity.completed")[-8:]
        if event.payload.get("activity") == "work"
        and is_rota_shift(event.payload.get("schedule_id"))
        and (when := _at(event)) is not None
        and when.date() == at.date()
    ]
    if worked and at.hour >= 17:
        candidates.append(("stiff", "Back's stiff from leaning over the bench all day.", -0.1))
    if 19 <= at.hour <= 21 and now >= alertness(history, at.replace(hour=15)) + 0.04:
        candidates.append(("second_wind", "Bit of a second wind, oddly.", 0.15))
    if at.hour >= 22 and now < 0.62:
        candidates.append(("eyes_going", "Eyes are going. Bed soon.", -0.05))
    if location_id not in {"home", "workshop", "cafe", "in_transit"} and weather in {
        "Light rain",
        "Breezy",
    }:
        candidates.append(
            (
                "chilly",
                "Damp and chilly out here."
                if weather == "Light rain"
                else "Wind's got a bite to it.",
                -0.1,
            )
        )
    if at.hour >= 16 and up >= 8 and _stayed_in(history, at):
        candidates.append(("cooped_up", "Been in all day. Getting a bit of cabin fever.", -0.1))
    for sensation, text, tone in candidates:
        if sensation not in already:
            return [
                DomainEvent(
                    SENSED,
                    "pathos",
                    {
                        "sensation": sensation,
                        "text": text,
                        "tone": tone,
                        "alertness": now,
                        "simulated_at": at.isoformat(),
                    },
                )
            ]
    return []


def _stayed_in(history: Sequence[DomainEvent], at: datetime) -> bool:
    """No trips out today."""
    return not any(
        (when := _at(event)) is not None and when.date() == at.date()
        for event in events_of(history, "pathos.travel_started", "travel.started")[-6:]
    )


def body_now(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What his body's been telling him in the last few hours."""
    return [
        str(event.payload.get("text"))
        for event in events_of(history, SENSED)[-4:]
        if (when := _at(event)) is not None and timedelta(0) <= at - when <= timedelta(hours=3)
    ]
