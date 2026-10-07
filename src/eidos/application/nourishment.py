"""Ordinary, replayable nourishment driven by bodily pressure and opportunity."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.day_rhythm import hour_today
from eidos.application.work_rota import is_rota_shift
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
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
    "hosted": (
        "Mum's cooking. Second helpings were not optional.",
        "Ate with everyone round the kitchen table, talking over each other.",
        "Leftovers, eaten standing up in Mum's kitchen, which is the best way.",
    ),
    "away": (
        "Stopped to eat something brought along for the day.",
        "Found a place to sit and ate a simple packed meal.",
        "Paused what he was doing long enough to eat.",
    ),
}

# Meals keep their rough place in the day and drift: (usual hour, earlier, later), on a
# shift day and a day off. Breakfast is later and slower on a day off; lunch at work tends
# to be late.
_MEAL_HOURS = {
    "breakfast": ((7, 0, 1), (9, 1, 1)),
    "lunch": ((13, 0, 1), (13, 1, 1)),
    "evening_meal": ((19, 0, 1), (19, 1, 1)),
}
# How long each stays the meal it is: breakfast that late is lunch.
_MEAL_SPAN = {"breakfast": 2, "lunch": 3, "evening_meal": 3}
# What an evening at home actually comes to.
_COOKED = (
    "Made a mushroom risotto, slowly, with a record on.",
    "Cooked a big pot of dal; there's enough for tomorrow.",
    "Roasted a tray of veg and made a proper gravy for once.",
    "Made shakshuka and ate it out of the pan.",
    "Tried a new curry recipe; too much cumin, but good.",
)
_TIRED = (
    "Beans on toast; too tired for anything else.",
    "Pasta and pesto from a jar, eaten on the sofa.",
    "Cheese on toast, which counts as tea.",
)
_TAKEAWAY = (
    "Got chips from the chippy on the way home and ate them out of the paper.",
    "Ordered a curry, which I'd been thinking about all afternoon.",
    "Pizza, delivered, eaten in front of something on telly.",
)
_SLOW_BREAKFAST = (
    "Made a proper breakfast, eggs and a pot of coffee, no rush.",
    "Porridge with a sliced banana, and the first coffee by the window.",
)
_QUICK_BREAKFAST = (
    "Toast standing up, coffee in a travel mug.",
    "A bowl of cereal at the counter, one eye on the clock.",
)


# Places where someone else feeds him.
HOSTED = frozenset({"wye-home"})

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

    date = at.date().isoformat()
    completed = {
        str(event.payload["meal_id"])
        for event in events_of(history, "meal.eaten", "meal.skipped")[-12:]
        if isinstance(event.payload.get("meal_id"), str)
    }
    working = working_day(planning, at)
    meal_kind = planned_meal_kind or next(
        (
            name
            for name in _MEAL_HOURS
            if _due(name, at, working) and f"meal:{date}:{name}" not in completed
        ),
        None,
    )
    urgent = state.hunger >= 0.78
    if meal_kind is None and not urgent:
        return []
    if meal_kind is None:
        meal_kind = "snack"

    meal_id = (
        f"meal-plan:{planned_schedule_id}"
        if planned_schedule_id is not None
        else f"meal:{date}:{meal_kind}"
    )
    if meal_id in completed:
        return []
    # Some work mornings there's no time, and breakfast doesn't happen.
    if (
        meal_kind == "breakfast"
        and planned_schedule_id is None
        and working
        and state.location_id == "home"
        and (_roll("no-breakfast", date) < 0.15 or _running_late(history, at))
    ):
        from eidos.application.bookings import remember

        skipped = DomainEvent(
            "meal.skipped",
            "pathos",
            {
                "meal_id": meal_id,
                "meal_kind": meal_kind,
                "text": "No time for breakfast; I'll get something later.",
                "location_id": state.location_id,
                "simulated_at": at.isoformat(),
            },
            correlation_id=meal_id,
        )
        return [
            skipped,
            remember(
                skipped, "No time for breakfast this morning.", at, 0.2,
                origin="lived-body", category="experience",
            ),
        ]  # fmt: skip
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
    hosted = state.location_id in HOSTED
    place = (
        "hosted"
        if hosted
        else state.location_id
        if state.location_id in {"home", "cafe"}
        else "away"
    )
    # A takeaway on a Friday, or when he's shattered, if there's the money for it.
    takeaway = (
        meal_kind == "evening_meal"
        and planned_schedule_id is None
        and place == "home"
        and available_pence >= 2_500
        and _roll("takeaway", date)
        < (0.4 if state.energy < 0.35 else 0.35 if at.weekday() == 4 else 0.04)
    )
    options = (
        _TAKEAWAY
        if takeaway
        else _home_meal(meal_kind, working, state.energy)
        if place == "home" and planned_schedule_id is None
        else _DESCRIPTIONS[place]
    )
    sample = sha256(f"{meal_id}:{state.location_id}".encode()).digest()[0]
    description = options[sample % len(options)]
    provisions = planning.objects.get(PROVISIONS_ID)
    uses_household_stock = state.location_id != "cafe" and not hosted and not takeaway
    cannot_afford_cafe = state.location_id == "cafe" and available_pence < 600
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
            "provision_source": "household_stock"
            if uses_household_stock
            else "family_table"
            if hosted
            else "takeaway"
            if takeaway
            else "cafe_service",
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


def working_day(planning: PlanningState, at: datetime) -> bool:
    """Whether he has a shift today."""
    return any(
        is_rota_shift(entry.schedule_id)
        and entry.status in {"scheduled", "active", "completed"}
        and entry.starts_at[:10] == at.date().isoformat()
        for entry in planning.calendar.values()
    )


def _due(kind: str, at: datetime, working: bool) -> bool:
    usual, earlier, later = _MEAL_HOURS[kind][0 if working else 1]
    starts = hour_today(kind, at.date(), usual, earlier, later)
    return starts <= at.hour < starts + _MEAL_SPAN[kind]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _running_late(history: Sequence[DomainEvent], at: datetime) -> bool:
    return any(
        e.payload.get("kind") == "cutting_it_fine"
        and str(e.payload.get("simulated_at", ""))[:10] == at.date().isoformat()
        for e in events_of(history, "happening.occurred")[-5:]
    )


def _home_meal(kind: str, working: bool, energy: float) -> tuple[str, ...]:
    if kind == "breakfast":
        return _QUICK_BREAKFAST if working else _SLOW_BREAKFAST
    if kind == "evening_meal":
        return (
            _TIRED
            if working and energy < 0.45
            else _COOKED
            if not working
            else _DESCRIPTIONS["home"] + _TIRED[:1]
        )
    return _DESCRIPTIONS["home"]


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
