"""Friends who have moved away: the calls, and a weekend visit.

A friend who moves to another city doesn't vanish; the friendship changes shape. Every few
weeks one of them rings (more often with a close friend, less as the months go by with a
newer one) and they catch up: the new job, the rent, the flat with no light. And once, a
few months after they've gone, if they're close and he can afford the train, he goes to
stay for a weekend: their sofa, their new local, their city shown off to him.

Each call is a ``friend.kept_in_touch`` event, a small shared moment that keeps the
friendship alive at a distance. The visit is a plan (``friend.visit_planned``) that causes
its booking, to a far-off place registered the first time he goes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.bookings import book, remember
from eidos.application.pronouns import in_his_words
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.world_catalog import WorldCatalog

CALL = "friend.kept_in_touch"
VISIT = "friend.visit_planned"
CALL_HOUR = 19
CLOSE = 6.0
KEEPS_IN_TOUCH_FROM = 4.0
CALL_CHANCE = {"close": 0.2, "friend": 0.08}  # per Sunday evening
VISIT_AFTER = timedelta(days=60)
VISIT_BY = timedelta(days=270)
VISIT_CHANCE = 0.2  # per Sunday once it's time
FARE_PENCE = 5_500
ORIGIN = "lived-far-friend"

NEWS = (
    "the new job's hard but good",
    "the rent's criminal and the flat has no light",
    "they've found a pub they like almost as much as the Crown",
    "they've joined a five-a-side team and are terrible",
    "they miss the river walk, apparently",
    "they've been adopted by a neighbour's cat",
)


def place_for(city: str) -> str:
    return f"city-{city.lower()}"


def far_friend_events(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    *,
    awake: bool,
    location_id: str,
    away: Mapping[str, tuple[str, datetime]],
    depths: Mapping[str, float],
    names: Mapping[str, str],
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    """``away`` maps friend -> (city, when they moved)."""
    if not awake:
        return []
    return (
        _visit(history, at, catalog, away, depths, names, balance_pence, rent_pence)
        or _call(history, at, away, depths, names)
        or _while_visiting(history, at, location_id, names)
    )


def _call(
    history: Sequence[DomainEvent],
    at: datetime,
    away: Mapping[str, tuple[str, datetime]],
    depths: Mapping[str, float],
    names: Mapping[str, str],
) -> list[DomainEvent]:
    if at.weekday() != 6 or at.hour != CALL_HOUR:
        return []
    for person, (city, moved) in sorted(away.items()):
        depth = depths.get(person, 0.0)
        if depth < KEEPS_IN_TOUCH_FROM:
            continue
        chance = CALL_CHANCE["close" if depth >= CLOSE else "friend"]
        if depth < CLOSE:
            chance *= max(0.25, 1 - (at - moved).days / 730)  # newer friendships thin out
        if _roll("call", person, at.date().isoformat()) >= chance:
            continue
        name = _first(names, person)
        news = NEWS[int(_roll("news", person, at.date().isoformat()) * len(NEWS))]
        text = in_his_words(
            f"Rang {name} in {city} for an hour. Sounds like {news}. Felt like no time had passed.",
            person,
        )
        event = DomainEvent(
            CALL,
            "pathos",
            {
                "person_id": person,
                "city": city,
                "text": text,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"far-{person}",
        )
        return [event, remember(event, text, at, 0.4, origin=ORIGIN, person_id=person)]
    return []


def _visit(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    away: Mapping[str, tuple[str, datetime]],
    depths: Mapping[str, float],
    names: Mapping[str, str],
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    if at.weekday() != 6 or at.hour != 18:
        return []
    visited = {str(e.payload["person_id"]) for e in events_of(history, VISIT)}
    for person, (city, moved) in sorted(away.items()):
        if person in visited or depths.get(person, 0.0) < CLOSE:
            continue
        if not VISIT_AFTER <= at - moved <= VISIT_BY:
            continue
        if balance_pence < FARE_PENCE + rent_pence + 5_000:
            continue
        if _roll("visit", person, at.date().isoformat()) >= VISIT_CHANCE:
            continue
        name = _first(names, person)
        friday = (at + timedelta(days=12)).replace(hour=18, minute=0, second=0, microsecond=0)
        sunday = friday + timedelta(days=2, hours=-2)
        place_id = place_for(city)
        text = in_his_words(
            f"Booked the train to see {name} in {city} the weekend after next. They've "
            "promised the sofa's comfier than it looks.",
            person,
        )
        plan = DomainEvent(
            VISIT,
            "pathos",
            {
                "person_id": person,
                "city": city,
                "place_id": place_id,
                "starts_at": friday.isoformat(),
                "ends_at": sunday.isoformat(),
                "text": text,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"far-visit-{person}",
        )
        output = [plan, remember(plan, text, at, 0.5, origin=ORIGIN, person_id=person)]
        if place_id not in catalog.places:
            output.append(_register(place_id, city, catalog, at, plan))
        output += book(
            plan,
            schedule_id=f"visit-{person}-{friday.date().isoformat()}",
            title=f"A weekend with {name} in {city}",
            starts=friday,
            ends=sunday,
            place_id=place_id,
            activity_type="visiting_a_friend",
            source="far_friends",
            motivation=f"Seeing {name}.",
            at=at,
            priority=0.9,
        )
        return output
    return []


_MOMENTS = {
    (1, 22): "Saturday in {city} with {name}: the market, the river, and their new local, which "
    "they're right about. We talked until two.",
    (2, 12): "Hungover breakfast with {name} before the train home. Promised it won't be so long "
    "next time. Meant it.",
}


def _while_visiting(
    history: Sequence[DomainEvent], at: datetime, location_id: str, names: Mapping[str, str]
) -> list[DomainEvent]:
    if not location_id.startswith("city-"):
        return []
    plan = next(
        (
            e
            for e in reversed(events_of(history, VISIT))
            if e.payload.get("place_id") == location_id
        ),
        None,
    )
    if plan is None:
        return []
    day = (at.date() - datetime.fromisoformat(str(plan.payload["starts_at"])).date()).days
    template = _MOMENTS.get((day, at.hour))
    if template is None:
        return []
    person = str(plan.payload["person_id"])
    key = f"visit-{person}-{day}"
    if any(e.payload.get("moment_id") == key for e in events_of(history, CALL)):
        return []
    text = in_his_words(
        template.format(city=plan.payload["city"], name=_first(names, person)), person
    )
    event = DomainEvent(
        CALL,
        "pathos",
        {
            "person_id": person,
            "city": plan.payload["city"],
            "moment_id": key,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"far-visit-{person}",
    )
    return [
        event,
        remember(event, text, at, 0.65, origin=ORIGIN, person_id=person, location_id=location_id),
    ]


def _register(
    place_id: str, city: str, catalog: WorldCatalog, at: datetime, cause: DomainEvent
) -> DomainEvent:
    from eidos.application.town_pack import _free_spot

    occupied = [(place.x, place.y) for place in catalog.places.values()]
    x, y = _free_spot(8, 92, occupied)
    return DomainEvent(
        "world.place_registered",
        "pathos",
        {
            "entity_id": place_id,
            "entity_kind": "place",
            "name": city,
            "label": city,
            "description": f"{city}, where a friend of his lives now.",
            "connected_to_id": "station" if "station" in catalog.places else "home",
            "x": x,
            "y": y,
            "opens_hour": 0,
            "closes_hour": 24,
            "travel_minutes": 180,
            "purpose": "A friend's new city.",
            "origin": "far_friends",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def visit_fares(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, VISIT)[-5:]):
        if at - datetime.fromisoformat(str(event.payload["simulated_at"])) > timedelta(days=2):
            break
        output.append(
            (
                f"visit-fare-{event.payload['person_id']}",
                FARE_PENCE,
                f"Train to {event.payload['city']}",
            )
        )
    return output


def _first(names: Mapping[str, str], person: str) -> str:
    return names.get(person, person.replace("-", " ").title()).split()[0]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
