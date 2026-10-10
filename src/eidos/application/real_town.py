"""Alderwick laid on Frome's real streets.

Frome, in Somerset, is where his weather and news already come from, an hour from Bristol
where he studied. The town keeps its name, its people and its businesses (their names are
Alderwick's own, so nothing said lands on a real café), but its places sit where their real
counterparts are and the walking times between them are the real ones along the streets
(OpenStreetMap contributors, ODbL; built by tools/build_real_town.py into frome_v1.json).

It arrives once, as events (each place relocated, then the walking network among them set),
so his history keeps the geography it had: journeys already made keep their recorded times.
It applies to a world that has all of the town's places; smaller worlds keep their layout.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.world_catalog import WorldCatalog

PLAN_ID = "frome-v1"


@cache
def plan() -> dict[str, Any]:
    return dict(json.loads((Path(__file__).with_name("frome_v1.json")).read_text()))


def real_town_events(
    history: Sequence[DomainEvent], at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    if any(e.payload.get("plan_id") == PLAN_ID for e in events_of(history, "world.routes_set")):
        return []
    layout = plan()
    places: dict[str, dict[str, Any]] = layout["places"]
    if not set(places) <= set(catalog.places):
        return []
    output = [
        DomainEvent(
            "world.place_relocated",
            "pathos",
            {
                "entity_id": place_id,
                "x": spot["x"],
                "y": spot["y"],
                "lat": spot["lat"],
                "lon": spot["lon"],
                "description": f"{catalog.places[place_id].description.rstrip('.')}; "
                f"{spot['where']}.",
                "plan_id": PLAN_ID,
                "simulated_at": at.isoformat(),
            },
        )
        for place_id, spot in sorted(places.items())
    ]
    output.append(
        DomainEvent(
            "world.routes_set",
            "pathos",
            {
                "plan_id": PLAN_ID,
                "places": ",".join(sorted(places)),
                "routes": ";".join(f"{a}|{b}|{m}" for a, b, m in layout["routes"]),
                "source": layout["source"],
                "simulated_at": at.isoformat(),
            },
        )
    )
    return output
