"""Things Patrick comes to want, saves for, and eventually owns.

Money only means something if it can become part of a life. A want forms from who he is
becoming, never from an advert: the value he has been living most, or a hope he holds
about himself, points toward one ordinary thing. He sits with it for a few days, saves
until he could buy it and still keep a cushion, and picks it up on a free day while he
is out. The thing then exists: an owned object his plans can use. A want that stays out
of reach for two months, or that no longer fits him, is quietly let go.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.work_rota import SHIFT_WEEKDAYS
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import project_selfhood

RESERVE_PENCE = 20_000
CONSIDER_FOR = timedelta(days=3)
GIVE_UP_AFTER = timedelta(days=60)
WANT_SPACING = timedelta(days=21)


@dataclass(frozen=True, slots=True)
class WantOption:
    want_id: str
    value_id: str
    item: str
    object_name: str
    price_pence: int
    reason: str


# Ordinary things that fit his authored interests and the values he lives by.
OPTIONS: tuple[WantOption, ...] = (
    WantOption(
        "film-camera",
        "curiosity",
        "a secondhand film camera",
        "Secondhand film camera",
        8_500,
        "I keep noticing things I'd like to look at more slowly.",
    ),
    WantOption(
        "hand-plane",
        "craft",
        "a proper hand plane for the workbench",
        "Block plane",
        6_000,
        "I want to do the finishing properly instead of making do.",
    ),
    WantOption(
        "coffee-grinder",
        "autonomy",
        "a hand grinder for filter coffee",
        "Hand coffee grinder",
        3_500,
        "A slow morning that's actually mine starts with decent coffee.",
    ),
    WantOption(
        "cookbook",
        "care",
        "a good vegetarian cookbook to cook for people",
        "Vegetarian cookbook",
        2_200,
        "I'd like to be able to feed people properly when they come round.",
    ),
    WantOption(
        "notebook",
        "reliability",
        "a sturdy notebook and a decent pen",
        "Notebook and pen",
        2_800,
        "If I wrote things down I might stop letting the small ones slip.",
    ),
    WantOption(
        "record-player",
        "curiosity",
        "a second-hand record player",
        "Record player",
        12_000,
        "I miss listening to a whole record the way it was meant to be heard.",
    ),
)
_BY_ID: Mapping[str, WantOption] = {option.want_id: option for option in OPTIONS}


def want_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    *,
    balance_pence: int,
    location_id: str,
    awake: bool,
) -> list[DomainEvent]:
    """At most one want is alive at a time; this advances its whole lifecycle."""
    active, last_formed = _active_want(history)
    if active is not None:
        return _pursue(active, simulated_at, balance_pence, location_id, awake)
    if simulated_at.hour != 11 or simulated_at.weekday() != 5:
        return []
    if last_formed is not None and simulated_at - last_formed < WANT_SPACING:
        return []
    option = _fitting_option(history, simulated_at)
    if option is None:
        return []
    return [
        DomainEvent(
            "want.formed",
            "pathos",
            {
                "want_id": f"want-{option.want_id}-{simulated_at.date().isoformat()}",
                "option_id": option.want_id,
                "item": option.item,
                "value_id": option.value_id,
                "price_pence": option.price_pence,
                "reason": option.reason,
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=f"want-{option.want_id}",
        )
    ]


def _fitting_option(history: Sequence[DomainEvent], at: datetime) -> WantOption | None:
    """The value he has lived most lately (or hopes to live) picks the thing he wants."""
    state = project_selfhood(history)
    owned = {
        str(event.payload.get("option_id"))
        for event in history
        if event.kind in {"want.purchased", "want.released"}
    }
    hoped = [item.value_id for item in state.active_aspirations() if item.kind == "hoped"]
    lived: dict[str, int] = {}
    for item in state.recent_evidence(at):
        if item.direction > 0:
            lived[item.value_id] = lived.get(item.value_id, 0) + 1
    ranked = [*hoped, *sorted(lived, key=lambda value: (-lived[value], value))]
    if not ranked or sum(lived.values()) < 6:
        return None
    for value_id in ranked:
        for option in OPTIONS:
            if option.value_id == value_id and option.want_id not in owned:
                return option
    return None


def _active_want(history: Sequence[DomainEvent]) -> tuple[DomainEvent | None, datetime | None]:
    active: DomainEvent | None = None
    last_formed: datetime | None = None
    for event in history:
        if event.kind == "want.formed":
            active = event
            last_formed = datetime.fromisoformat(str(event.payload["simulated_at"]))
        elif event.kind in {"want.purchased", "want.released"} and active is not None:
            if event.payload.get("want_id") == active.payload.get("want_id"):
                active = None
    return active, last_formed


def _pursue(
    want: DomainEvent,
    at: datetime,
    balance_pence: int,
    location_id: str,
    awake: bool,
) -> list[DomainEvent]:
    formed = datetime.fromisoformat(str(want.payload["simulated_at"]))
    price = int(want.payload["price_pence"])
    want_id = str(want.payload["want_id"])
    option = _BY_ID.get(str(want.payload["option_id"]))
    if at - formed >= GIVE_UP_AFTER or option is None:
        return [
            DomainEvent(
                "want.released",
                "pathos",
                {
                    "want_id": want_id,
                    "option_id": want.payload["option_id"],
                    "reason": "it stayed out of reach long enough that I stopped thinking about it",
                    "simulated_at": at.isoformat(),
                },
                causation_id=want.event_id,
                correlation_id=want.correlation_id,
            )
        ]
    free_day = at.weekday() not in SHIFT_WEEKDAYS
    out_and_about = awake and location_id not in {"home", "in_transit", "workshop"}
    if (
        at - formed < CONSIDER_FOR
        or not free_day
        or not out_and_about
        or not 10 <= at.hour < 17
        or balance_pence < price + RESERVE_PENCE
    ):
        return []
    purchased = DomainEvent(
        "want.purchased",
        "pathos",
        {
            "want_id": want_id,
            "option_id": option.want_id,
            "item": option.item,
            "value_id": option.value_id,
            "price_pence": price,
            "bought_at_location_id": location_id,
            "simulated_at": at.isoformat(),
        },
        causation_id=want.event_id,
        correlation_id=want.correlation_id,
    )
    object_id = f"owned-{option.want_id}"
    # The ledger charges the purchase from this event, like every other expense.
    return [
        purchased,
        DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": object_id,
                "name": option.object_name,
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "home",
                "condition": "good",
                "source": "personal-purchase",
                "simulated_at": at.isoformat(),
            },
            causation_id=purchased.event_id,
            correlation_id=want.correlation_id,
        ),
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"Finally picked up {option.item}. Saved up for it.",
                "simulated_at": at.isoformat(),
                "category": "milestone",
                "source": "lived-purchase",
                "source_event_id": str(purchased.event_id),
                "location_id": location_id,
                "owner": "pathos",
                "importance": 0.6,
                "confidence": 1.0,
            },
            causation_id=purchased.event_id,
            correlation_id=want.correlation_id,
        ),
    ]


def wants_view(history: Sequence[DomainEvent], balance_pence: int) -> dict[str, object]:
    """What he is saving toward, and what saving has already become part of his life."""
    active, _ = _active_want(history)
    owned = [
        {
            "item": str(event.payload.get("item")),
            "value_id": str(event.payload.get("value_id")),
            "at": str(event.payload.get("simulated_at")),
        }
        for event in history
        if event.kind == "want.purchased"
    ]
    return {
        "saving_for": None
        if active is None
        else {
            "item": active.payload["item"],
            "reason": active.payload["reason"],
            "value_id": active.payload["value_id"],
            "price_pence": active.payload["price_pence"],
            "saved_pence": max(
                0, min(int(active.payload["price_pence"]), balance_pence - RESERVE_PENCE)
            ),
            "since": active.payload["simulated_at"],
        },
        "bought": owned[-6:][::-1],
    }
