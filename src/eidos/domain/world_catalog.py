"""Replayable catalog for an authored seed world that can grow through accepted events."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world import LOCATIONS, OPEN_HOURS, PEOPLE

ENTITY_ID = re.compile(r"[a-z][a-z0-9-]{2,39}")
EXPANSION_FIELDS = {
    "entity_kind",
    "entity_id",
    "name",
    "description",
    "location_id",
    "purpose",
    "color",
    "label",
    "x",
    "y",
    "opens_hour",
    "closes_hour",
    "travel_minutes",
}
SEED_ROUTE_MINUTES: Mapping[frozenset[str], int] = {
    frozenset(("home", "cafe")): 20,
    frozenset(("cafe", "workshop")): 15,
    frozenset(("workshop", "park")): 20,
    frozenset(("park", "home")): 15,
    frozenset(("home", "workshop")): 30,
    frozenset(("cafe", "park")): 25,
}


class WorldEntityKind(StrEnum):
    PERSON = "person"
    OBJECT = "object"
    PLACE = "place"


@dataclass(frozen=True, slots=True)
class WorldPlace:
    place_id: str
    name: str
    label: str
    description: str
    x: int
    y: int
    opens_hour: int
    closes_hour: int
    introduced: bool = False


@dataclass(frozen=True, slots=True)
class WorldPerson:
    person_id: str
    name: str
    occupation: str
    description: str
    color: str
    home_location_id: str = "home"
    introduced: bool = False


@dataclass(frozen=True, slots=True)
class WorldCatalog:
    places: Mapping[str, WorldPlace]
    people: Mapping[str, WorldPerson]
    route_minutes: Mapping[frozenset[str], int]
    object_ids: frozenset[str] = frozenset()
    object_names: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "places", MappingProxyType(dict(self.places)))
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))
        object.__setattr__(self, "route_minutes", MappingProxyType(dict(self.route_minutes)))

    def apply(self, event: DomainEvent) -> WorldCatalog:
        places, people, routes = dict(self.places), dict(self.people), dict(self.route_minutes)
        object_ids, object_names = set(self.object_ids), set(self.object_names)
        if event.kind == "world.place_registered":
            place_id = _required(event, "entity_id")
            connected_to = _required(event, "connected_to_id")
            if place_id in places or connected_to not in places:
                raise ValueError("A new place needs a unique ID and an existing connection")
            place = WorldPlace(
                place_id,
                _required(event, "name"),
                _required(event, "label"),
                _required(event, "description"),
                _integer(event, "x", 5, 95),
                _integer(event, "y", 5, 95),
                _integer(event, "opens_hour", 0, 23),
                _integer(event, "closes_hour", 1, 24),
                True,
            )
            if place.opens_hour >= place.closes_hour:
                raise ValueError("A place must close after it opens")
            places[place_id] = place
            routes[frozenset((place_id, connected_to))] = _integer(event, "travel_minutes", 1, 180)
        elif event.kind == "world.person_registered":
            person_id = _required(event, "entity_id")
            home = _required(event, "location_id")
            if person_id in people or home not in places:
                raise ValueError("A new person needs a unique ID and a known home location")
            people[person_id] = WorldPerson(
                person_id,
                _required(event, "name"),
                _required(event, "purpose"),
                _required(event, "description"),
                _required(event, "color"),
                home,
                True,
            )
        elif event.kind == "object.registered":
            object_id = _required(event, "object_id")
            name = _required(event, "name")
            if object_id in object_ids:
                raise ValueError("Registered world object already exists")
            object_ids.add(object_id)
            object_names.add(name.casefold())
        return WorldCatalog(places, people, routes, frozenset(object_ids), frozenset(object_names))

    def location_name(self, location_id: str) -> str:
        place = self.places.get(location_id)
        if place is None:
            raise ValueError("Unknown world location")
        return place.name


@dataclass(frozen=True, slots=True)
class WorldExpansionProposal:
    proposal_id: str
    entity_kind: WorldEntityKind
    entity_id: str
    name: str
    description: str
    location_id: str
    purpose: str
    color: str
    label: str
    x: int
    y: int
    opens_hour: int
    closes_hour: int
    travel_minutes: int
    expected_revision: int


@dataclass(frozen=True, slots=True)
class WorldExpansionResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def parse_world_expansion_candidate(
    content: str, *, proposal_id: str, expected_revision: int
) -> WorldExpansionProposal:
    try:
        raw = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "World expansion was not valid JSON") from None
    if not isinstance(raw, dict) or set(raw) != EXPANSION_FIELDS:
        raise ProposalRejected("invalid_shape", "World expansion fields did not match schema v1")
    try:
        kind = WorldEntityKind(raw["entity_kind"])
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_kind", "World expansion kind is unknown") from None
    for field, maximum in {
        "entity_id": 40,
        "name": 80,
        "description": 240,
        "location_id": 40,
        "purpose": 100,
        "color": 7,
        "label": 40,
    }.items():
        value = raw[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ProposalRejected("invalid_text", f"World expansion {field} is invalid")
    integers: dict[str, int] = {}
    for field in ("x", "y", "opens_hour", "closes_hour", "travel_minutes"):
        value = raw[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProposalRejected("invalid_number", f"World expansion {field} must be an integer")
        integers[field] = value
    return WorldExpansionProposal(
        proposal_id=proposal_id,
        entity_kind=kind,
        entity_id=raw["entity_id"].strip(),
        name=raw["name"].strip(),
        description=raw["description"].strip(),
        location_id=raw["location_id"].strip(),
        purpose=raw["purpose"].strip(),
        color=raw["color"].strip(),
        label=raw["label"].strip(),
        expected_revision=expected_revision,
        **integers,
    )


def world_expansion_output_schema(known_location_ids: Sequence[str]) -> Mapping[str, object]:
    return {
        "type": "object",
        "properties": {
            "entity_kind": {"type": "string", "enum": [item.value for item in WorldEntityKind]},
            "entity_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{2,39}$"},
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
            "description": {"type": "string", "minLength": 1, "maxLength": 240},
            "location_id": {"type": "string", "enum": list(known_location_ids)},
            "purpose": {"type": "string", "minLength": 1, "maxLength": 100},
            "color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
            "label": {"type": "string", "minLength": 1, "maxLength": 40},
            "x": {"type": "integer", "minimum": 5, "maximum": 95},
            "y": {"type": "integer", "minimum": 5, "maximum": 95},
            "opens_hour": {"type": "integer", "minimum": 0, "maximum": 23},
            "closes_hour": {"type": "integer", "minimum": 1, "maximum": 24},
            "travel_minutes": {"type": "integer", "minimum": 1, "maximum": 180},
        },
        "required": sorted(EXPANSION_FIELDS),
        "additionalProperties": False,
    }


def seed_world_catalog() -> WorldCatalog:
    places = {
        str(place["id"]): WorldPlace(
            str(place["id"]),
            str(place["name"]),
            str(place["label"]),
            str(place["description"]),
            _seed_integer(place["x"]),
            _seed_integer(place["y"]),
            OPEN_HOURS[str(place["id"])][0].hour,
            24 if str(place["id"]) == "home" else OPEN_HOURS[str(place["id"])][1].hour,
        )
        for place in LOCATIONS
    }
    people = {
        str(person["id"]): WorldPerson(
            str(person["id"]),
            str(person["name"]),
            str(person["occupation"]),
            str(person["description"]),
            str(person["color"]),
        )
        for person in PEOPLE
    }
    return WorldCatalog(places, people, SEED_ROUTE_MINUTES)


def project_world_catalog(events: Sequence[DomainEvent]) -> WorldCatalog:
    state = seed_world_catalog()
    for event in events:
        state = state.apply(event)
    return state


def resolve_world_expansion(
    proposal: WorldExpansionProposal,
    *,
    catalog: WorldCatalog,
    actual_revision: int,
    simulated_at: str,
) -> WorldExpansionResolution:
    common: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "entity_kind": proposal.entity_kind.value,
        "entity_id": proposal.entity_id,
        "name": proposal.name,
        "description": proposal.description,
        "location_id": proposal.location_id,
        "purpose": proposal.purpose,
        "simulated_at": simulated_at,
    }
    proposed = DomainEvent(
        "world.expansion_proposed", "pathos", common, correlation_id=proposal.proposal_id
    )

    def reject(code: str, reason: str) -> WorldExpansionResolution:
        return WorldExpansionResolution(
            False,
            code,
            (
                proposed,
                DomainEvent(
                    "world.expansion_rejected",
                    "pathos",
                    {**common, "code": code, "reason": reason},
                    causation_id=proposed.event_id,
                    correlation_id=proposal.proposal_id,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed before registration")
    if not ENTITY_ID.fullmatch(proposal.entity_id):
        return reject("invalid_id", "Entity IDs must be stable lowercase slugs")
    if not all(value.strip() for value in (proposal.name, proposal.description, proposal.purpose)):
        return reject("invalid_text", "Name, description, and purpose are required")
    if (
        proposal.entity_id in catalog.people
        or proposal.entity_id in catalog.places
        or proposal.entity_id in catalog.object_ids
    ):
        return reject("duplicate_id", "That entity ID already exists")
    names = (
        {item.name.casefold() for item in catalog.people.values()}
        | {item.name.casefold() for item in catalog.places.values()}
        | set(catalog.object_names)
    )
    if proposal.name.casefold() in names:
        return reject("duplicate_name", "That entity name already exists")
    if proposal.location_id not in catalog.places:
        return reject("unknown_location", "The entity must connect to a known place")
    payload = dict(common)
    if proposal.entity_kind is WorldEntityKind.PERSON:
        if not proposal.color.startswith("#") or len(proposal.color) != 7:
            return reject("invalid_color", "A person needs a six-digit display color")
        kind = "world.person_registered"
        payload["color"] = proposal.color
    elif proposal.entity_kind is WorldEntityKind.OBJECT:
        kind = "object.registered"
        payload.update(
            owner_id="community",
            custodian_id="community",
            condition="good",
            object_id=proposal.entity_id,
        )
    else:
        if (
            not proposal.label.strip()
            or not 5 <= proposal.x <= 95
            or not 5 <= proposal.y <= 95
            or not 0 <= proposal.opens_hour < proposal.closes_hour <= 24
            or not 1 <= proposal.travel_minutes <= 180
        ):
            return reject("invalid_place", "Place layout, hours, and route must be feasible")
        if any(
            abs(place.x - proposal.x) <= 8 and abs(place.y - proposal.y) <= 8
            for place in catalog.places.values()
        ):
            return reject("crowded_layout", "The new place would overlap an existing map place")
        kind = "world.place_registered"
        payload.update(
            label=proposal.label,
            connected_to_id=proposal.location_id,
            x=proposal.x,
            y=proposal.y,
            opens_hour=proposal.opens_hour,
            closes_hour=proposal.closes_hour,
            travel_minutes=proposal.travel_minutes,
        )
    registered = DomainEvent(
        kind,
        "pathos",
        payload,
        causation_id=proposed.event_id,
        correlation_id=proposal.proposal_id,
    )
    accepted = DomainEvent(
        "world.expansion_accepted",
        "pathos",
        {**common, "registration_event_id": str(registered.event_id)},
        causation_id=registered.event_id,
        correlation_id=proposal.proposal_id,
    )
    return WorldExpansionResolution(True, "accepted", (proposed, registered, accepted))


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _integer(event: DomainEvent, key: str, minimum: int, maximum: int) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def _seed_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Seed world coordinates must be integers")
    return value
