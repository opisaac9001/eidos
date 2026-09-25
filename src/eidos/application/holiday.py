"""A week away in the summer.

Ellis shuts the workshop for the first full week of August every year ("the only week the
radio gets a rest"). Once Patrick has a bit put by, he uses it. In May he books a week
away:
- with whoever he's properly together with, if anyone;
- otherwise sometimes with his closest friend;
- otherwise on his own, which he tells himself he prefers.

It's somewhere ordinary and lovely: a cottage in the Lakes, the Pembrokeshire coast,
Norfolk, or a cheap flight to Lisbon.

The week is a stay away from Alderwick (``on_holiday``), with a few moments he remembers,
and it costs what holidays cost. If money's tight that spring he doesn't go, and notices
he didn't.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.seasons import summer_shutdown
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.world_catalog import WorldCatalog

KIND = "holiday.stage"
ACTIVITY = "on_holiday"
BOOK_MONTH = 5
SOLO_COST_PENCE = 52_000
SHARED_COST_PENCE = 34_000
CUSHION_PENCE = 40_000  # he wants this left afterwards
WITH_FRIEND = 0.6

# place id -> (name, label, description, travel minutes, the moments he remembers)
PLACES: dict[str, tuple[str, str, str, int, tuple[str, str, str]]] = {
    "holiday-lakes": (
        "A cottage near Coniston",
        "Lakes",
        "A slate cottage with a wood burner, a leaking gutter and a view of the Old Man.",
        180,
        (
            "Rain all day, so we read by the wood burner and did a jigsaw with a piece missing. "
            "Perfect, honestly.",
            "Walked up the Old Man of Coniston. Legs like jelly. The view made it stupidly "
            "worth it.",
            "Last night away. Fish and chips on the wall by the lake. Don't want to go back, "
            "and sort of do.",
        ),
    ),
    "holiday-pembrokeshire": (
        "A caravan near St Davids",
        "Pembrokeshire",
        "A caravan on a clifftop field, with a kettle that whistles and a door that sticks.",
        180,
        (
            "Swam in the sea. Freezing. Shrieked. Went back in.",
            "Walked the coast path to a cove with nobody else in it. Sat there for an hour "
            "doing nothing at all.",
            "Last night away. Watched the sun go down from the cliff with a cup of tea. I "
            "should do this every year.",
        ),
    ),
    "holiday-norfolk": (
        "A B&B in Wells-next-the-Sea",
        "Norfolk",
        "A B&B with a landlady who knows everyone, and a beach that goes on forever.",
        170,
        (
            "Walked the beach at Holkham until it felt like the edge of the world.",
            "Crabbing off the quay like I was nine. Caught four. Named them all.",
            "Last night away. Sat outside the pub on the quay till it got cold.",
        ),
    ),
    "holiday-lisbon": (
        "A little flat in Lisbon",
        "Lisbon",
        "A flat up a hill so steep the trams groan, with a balcony over red roofs.",
        180,
        (
            "Ate custard tarts for breakfast, lunch and, if I'm honest, dinner.",
            "Got completely lost in the Alfama and found the best view in the city by accident.",
            "Last night away. Sat on the balcony listening to someone practise the guitar "
            "badly. I'll miss it.",
        ),
    ),
}


def holiday_events(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    *,
    awake: bool,
    location_id: str,
    balance_pence: int,
    rent_pence: int,
    partner: tuple[str, str] | None,
    friend: tuple[str, str] | None,
) -> list[DomainEvent]:
    """Book the week in May, or live it in August. ``partner``/``friend`` are (id, name)."""
    if not awake:
        return []
    return _book(history, at, catalog, balance_pence, rent_pence, partner, friend) or _away(
        history, at, location_id
    )


def _book(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    balance_pence: int,
    rent_pence: int,
    partner: tuple[str, str] | None,
    friend: tuple[str, str] | None,
) -> list[DomainEvent]:
    if at.month != BOOK_MONTH or at.weekday() != 6 or not 8 <= at.day <= 14 or at.hour != 19:
        return []
    holiday_id = f"holiday-{at.year}"
    if any(e.payload.get("holiday_id") == holiday_id for e in events_of(history, KIND)):
        return []
    opened = events_of(history, "finance.account_opened")
    if not opened or at - _time(opened[0]) < timedelta(days=120):
        return []
    company = partner
    if company is None and friend is not None and _roll("with-friend", at.year) < WITH_FRIEND:
        company = friend
    cost = SHARED_COST_PENCE if company else SOLO_COST_PENCE
    if balance_pence < cost + rent_pence + CUSHION_PENCE:
        text = (
            "Everyone's booking summer holidays. Did the maths and I can't this year. Fine. "
            "The workshop week off will be a week of long walks, then."
        )
        skipped = _stage(holiday_id, "skipped", text, at, 0.45)
        return [skipped, _memory(skipped, text, at, 0.45)]
    place_id = sorted(PLACES)[int(_roll("where", at.year) * len(PLACES))]
    name, *_ = PLACES[place_id]
    monday, friday = summer_shutdown(at.year)
    leaves = datetime(monday.year, monday.month, monday.day, 10, tzinfo=at.tzinfo) - timedelta(
        days=2
    )
    back = datetime(friday.year, friday.month, friday.day, 18, tzinfo=at.tzinfo)
    who = f" with {company[1].split()[0]}" if company else ""
    text = f"Booked a week away{who} for the workshop shutdown: {name.lower()}. " + (
        "Split the cost, which helped." if company else "Just me. I think I'll like it."
    )
    booked = _stage(
        holiday_id,
        "booked",
        text,
        at,
        0.6,
        place_id=place_id,
        cost_pence=cost,
        companion_id=company[0] if company else None,
        starts_at=leaves.isoformat(),
        ends_at=back.isoformat(),
    )
    output = [booked, _memory(booked, text, at, 0.6)]
    if place_id not in catalog.places:
        output.append(_register(place_id, catalog, at, booked))
    intention_id = f"{holiday_id}-intention"
    companion = company[0] if company and company[0] in catalog.people else None
    output += [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": holiday_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place_id,
                "goal_id": None,
                "priority": 0.9,
                "motivation": "A week away.",
                "simulated_at": at.isoformat(),
            },
            causation_id=booked.event_id,
            correlation_id=holiday_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": holiday_id,
                "intention_id": intention_id,
                "title": f"A week away: {name}",
                "starts_at": leaves.isoformat(),
                "ends_at": back.isoformat(),
                "location_id": place_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place_id,
                "resource_id": None,
                "companion_id": companion,
                "activity_type": ACTIVITY,
                "source": "holiday",
                "simulated_at": at.isoformat(),
            },
            causation_id=booked.event_id,
            correlation_id=holiday_id,
        ),
    ]
    return output


def _away(history: Sequence[DomainEvent], at: datetime, location_id: str) -> list[DomainEvent]:
    """A few moments he'll remember from the week."""
    if location_id not in PLACES:
        return []
    booked = next(
        (
            e
            for e in reversed(events_of(history, KIND))
            if e.payload.get("stage") == "booked" and e.payload.get("place_id") == location_id
        ),
        None,
    )
    if booked is None:
        return []
    first = datetime.fromisoformat(str(booked.payload["starts_at"])).date()
    day = (at.date() - first).days + 1
    moments = PLACES[location_id][4]
    slot = {(2, 20): 0, (4, 14): 1, (6, 20): 2}.get((day, at.hour))
    if slot is None:
        return []
    holiday_id = str(booked.payload["holiday_id"])
    if any(
        e.payload.get("holiday_id") == holiday_id and e.payload.get("moment") == slot
        for e in events_of(history, KIND)
    ):
        return []
    text = moments[slot]
    if not booked.payload.get("companion_id"):
        text = text.replace(" we ", " I ").replace("We ", "I ")
    moment = _stage(holiday_id, "moment", text, at, 0.65, moment=slot, place_id=location_id)
    return [moment, _memory(moment, text, at, 0.65)]


def _register(
    place_id: str, catalog: WorldCatalog, at: datetime, cause: DomainEvent
) -> DomainEvent:
    from eidos.application.town_pack import _free_spot

    name, label, description, minutes, _ = PLACES[place_id]
    occupied = [(place.x, place.y) for place in catalog.places.values()]
    x, y = _free_spot(92, 8, occupied)
    return DomainEvent(
        "world.place_registered",
        "pathos",
        {
            "entity_id": place_id,
            "entity_kind": "place",
            "name": name,
            "label": label,
            "description": description,
            "connected_to_id": "station" if "station" in catalog.places else "home",
            "x": x,
            "y": y,
            "opens_hour": 0,
            "closes_hour": 24,
            "travel_minutes": minutes,
            "purpose": "Somewhere he went on holiday.",
            "origin": "holiday",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def holiday_costs(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, KIND)):
        if at - _time(event) > timedelta(days=2):
            break
        if event.payload.get("stage") == "booked":
            output.append(
                (
                    f"{event.payload['holiday_id']}",
                    int(event.payload["cost_pence"]),
                    "A week away: travel and somewhere to stay",
                )
            )
    return output


def holiday_context(history: Sequence[DomainEvent], at: datetime) -> dict[str, str] | None:
    stages = [e for e in events_of(history, KIND) if at - _time(e) <= timedelta(days=120)]
    if not stages:
        return None
    return {"lately": str(stages[-1].payload["text"])}


def _stage(
    holiday_id: str, stage: str, text: str, at: datetime, importance: float, **extra: object
) -> DomainEvent:
    return DomainEvent(
        KIND,
        "pathos",
        {
            "holiday_id": holiday_id,
            "stage": stage,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **{key: value for key, value in extra.items() if value is not None},
        },
        correlation_id=holiday_id,
    )


def _memory(source: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "milestone",
            "source": "lived-holiday",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **(
                {"location_id": source.payload["place_id"]}
                if isinstance(source.payload.get("place_id"), str)
                else {}
            ),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
