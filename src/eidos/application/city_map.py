"""An event-sourced travel atlas; registration is not a fabricated visit."""

from collections import Counter
from typing import Sequence

from eidos.application.place_discovery import known_place_ids
from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import WorldCatalog


def city_map(
    history: Sequence[DomainEvent], catalog: WorldCatalog, current_location_id: str | None
) -> dict[str, object]:
    visits: Counter[str] = Counter()
    last_visit: dict[str, object] = {}
    for event in history:
        if event.kind == "pathos.moved":
            place = event.payload.get("location_id")
            if isinstance(place, str) and place in catalog.places:
                visits[place] += 1
                last_visit[place] = event.payload.get("simulated_at")
    known = known_place_ids(history, catalog)
    return {
        "places": {
            place_id: {
                "experience": "here"
                if place_id == current_location_id
                else "visited"
                if visits[place_id]
                else "known_not_visited"
                if place_id in known
                else "undiscovered",
                "visits": visits[place_id],
                "last_visit": last_visit.get(place_id),
            }
            for place_id in catalog.places
        },
        "routes": [
            {"from": sorted(edge)[0], "to": sorted(edge)[1], "minutes": minutes}
            for edge, minutes in sorted(
                catalog.route_minutes.items(), key=lambda item: sorted(item[0])
            )
        ],
    }
