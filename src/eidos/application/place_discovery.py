"""What Patrick actually knows of his town.

A place existing in the world is not the same as Patrick knowing it (the blueprint's
discovery policy: planned is not known). He knows his home ground from the start, every
place he has actually been, places he has discovered, and places friends have invited him
to. Discovery is ordinary: arriving somewhere, he sometimes notices a place he hadn't
clocked just along the way, or someone suggests meeting somewhere he'd never been. His
own plans and ideas only reach for places he knows.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.world_catalog import WorldCatalog

HOME_GROUND = frozenset({"home", "cafe", "workshop", "park"})
NOTICE_CHANCE = 0.3


def known_place_ids(history: Sequence[DomainEvent], catalog: WorldCatalog) -> frozenset[str]:
    known = set(HOME_GROUND)
    for event in events_of(history, "pathos.moved", "place.discovered", "invitation.made"):
        if event.kind == "invitation.made" and event.payload.get("invitee_id") != "pathos":
            continue
        place = event.payload.get("location_id") or event.payload.get("place_id")
        if isinstance(place, str):
            known.add(place)
    return frozenset(place for place in known if place in catalog.places)


def visited_place_ids(history: Sequence[DomainEvent]) -> frozenset[str]:
    """Places he has actually been: his home ground, and anywhere he has arrived."""
    return HOME_GROUND | {
        str(event.payload["location_id"])
        for event in events_of(history, "pathos.moved")
        if isinstance(event.payload.get("location_id"), str)
    }


def known_world(history: Sequence[DomainEvent], catalog: WorldCatalog) -> WorldCatalog:
    """The catalog as he knows it: only known places, with every street still walkable."""
    known = known_place_ids(history, catalog)
    if len(known) == len(catalog.places):
        return catalog
    return replace(
        catalog,
        places={place_id: place for place_id, place in catalog.places.items() if place_id in known},
    )


def place_discovery_events(
    history: Sequence[DomainEvent],
    catalog: WorldCatalog,
    location_id: str,
    awake: bool,
    simulated_at: datetime,
) -> list[DomainEvent]:
    """At most one new place a day, noticed from somewhere he actually is."""
    if not awake or location_id in {"home", "in_transit"} or location_id not in catalog.places:
        return []
    today = simulated_at.date().isoformat()
    discoveries = events_of(history, "place.discovered")
    if any(str(event.payload.get("simulated_at", ""))[:10] == today for event in discoveries):
        return []
    known = known_place_ids(history, catalog)
    nearby = sorted(
        other
        for route in catalog.route_minutes
        if location_id in route
        for other in route
        if other != location_id and other not in known
    )
    if not nearby:
        return []
    roll = int(sha256(f"notice:{location_id}:{today}".encode()).hexdigest()[:8], 16)
    if roll / 0xFFFFFFFF >= NOTICE_CHANCE:
        return []
    place_id = nearby[roll % len(nearby)]
    place = catalog.places[place_id]
    discovered = DomainEvent(
        "place.discovered",
        "pathos",
        {
            "place_id": place_id,
            "how": "noticed in passing",
            "from_location_id": location_id,
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=f"discover-{place_id}",
    )
    return [
        discovered,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"Noticed {place.name} for the first time, just along from "
                f"{catalog.location_name(location_id)}.",
                "simulated_at": simulated_at.isoformat(),
                "category": "experience",
                "source": "lived-discovery",
                "source_event_id": str(discovered.event_id),
                "location_id": location_id,
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 1.0,
            },
            causation_id=discovered.event_id,
            correlation_id=discovered.correlation_id,
        ),
    ]
