"""Turn the Alderwick blueprint into an ordinary, additive world pack.

The blueprint is a design document, not world facts. This builds the next world-pack
release from it so the town can grow through the same validated, versioned, replayable
import every other pack uses. Each new public place is connected to its nearest place
already in the world along the street graph, with walking time at the blueprint's
75 metres a minute (plus a minute for doors and crossings). Private interiors and
residential frontage are left out: the discovery policy says they need a reason and
permission, not a map pin. Importing a place registers a possibility, never a visit,
a memory, or knowledge Patrick does not have.
"""

from __future__ import annotations

import heapq
import json
from math import ceil
from pathlib import Path
from typing import Any, Mapping, Sequence

PRIVATE = frozenset({"primary-school", "southbank-housing"})
# Places another pack already provides; registering them twice would reject one pack.
PROVIDED_ELSEWHERE = frozenset({"reading-room"})

# Opening windows from the blueprint's candidate hours; outdoor places stay open.
HOURS: Mapping[str, tuple[int, int]] = {
    "reading-room": (10, 18),
    "crown-anchor": (12, 23),
    "post-office": (9, 17),
    "pharmacy": (9, 18),
    "launderette": (7, 21),
    "charity-shop": (9, 17),
    "barber": (9, 17),
    "bus-interchange": (6, 23),
    "supermarket": (7, 22),
    "guesthouse": (8, 22),
    "parcel-depot": (8, 18),
    "clinic": (8, 18),
    "churchyard": (0, 24),
    "council-office": (9, 17),
    "mill-museum": (10, 16),
    "hardware": (8, 17),
    "print-studio": (10, 18),
    "bike-repair": (9, 18),
    "riverside-kiosk": (9, 17),
    "football-pavilion": (9, 21),
    "dog-walk": (0, 24),
    "nature-path": (6, 21),
    "hill-path": (0, 24),
    "cemetery": (8, 20),
}

DESCRIPTIONS: Mapping[str, tuple[str, str]] = {
    # id: (label, description)
    "reading-room": (
        "Reading Room",
        "A quiet upstairs room of donated books and oral-history tapes.",
    ),
    "crown-anchor": (
        "Crown",
        "An old pub with a fire in winter, a quiz on Tuesdays and slow lunches.",
    ),
    "post-office": (
        "Post Office",
        "Parcels, stamps, a queue that moves in its own time, and a noticeboard.",
    ),
    "pharmacy": ("Pharmacy", "An ordinary high-street pharmacy for everyday errands."),
    "launderette": (
        "Laundry",
        "Warm machines, folding tables and the same faces on the same evenings.",
    ),
    "charity-shop": (
        "Second Chances",
        "Donated books, mismatched crockery and the odd surprising find.",
    ),
    "barber": ("Barbers", "Two chairs, a radio, and conversation about nothing much."),
    "bus-interchange": (
        "Buses",
        "The forecourt where local buses turn, wait and sometimes don't come.",
    ),
    "supermarket": (
        "Food Store",
        "A bigger shop by the station for weekly food and household supplies.",
    ),
    "guesthouse": ("Guest Rooms", "A few rooms above the station for people passing through."),
    "parcel-depot": ("Depot", "Where missed parcels end up, behind a counter with a buzzer."),
    "clinic": (
        "Practice",
        "The town's GP surgery; appointments, waiting rooms and repeat prescriptions.",
    ),
    "churchyard": ("Churchyard", "Old stones, yew trees and a bench out of the wind."),
    "council-office": (
        "Council",
        "Public meetings, planning notices and the occasional heated evening.",
    ),
    "mill-museum": (
        "Mill Rooms",
        "Small exhibitions about the mill years, kept open by volunteers.",
    ),
    "hardware": ("Hardware", "Screws by weight, timber offcuts and advice you didn't ask for."),
    "print-studio": (
        "Print Studio",
        "A shared studio of presses, inky aprons and posters drying on lines.",
    ),
    "bike-repair": ("Bridge Cycles", "A cramped repair shop where bikes queue on hooks for parts."),
    "riverside-kiosk": ("Kiosk", "Tea and ice creams for walkers, open when the weather allows."),
    "football-pavilion": (
        "Pavilion",
        "A small clubhouse for Sunday league, tea urns and volunteers.",
    ),
    "dog-walk": ("Common", "Open meadow where dogs run and people drift into conversation."),
    "nature-path": ("Reedbeds", "A longer path through the reedbeds; birds, mud and weather."),
    "hill-path": ("Hill Path", "A climb to the edge of town and a view back over the roofs."),
    "cemetery": ("Cemetery", "Quiet paths among old and new graves at the edge of town."),
}

DISTRICT_COLOURS: Mapping[str, str] = {
    "old-town": "#b88859",
    "station-quarter": "#7f8fa8",
    "westfield": "#8fa97a",
    "mill-quarter": "#c49a6c",
    "foundry": "#a67b62",
    "southbank": "#7fa39a",
}


def build_town_pack(
    plan: Mapping[str, Any],
    existing_places: Mapping[str, tuple[int, int]],
    *,
    version: int = 1,
) -> dict[str, Any]:
    """The Alderwick places not yet in the world, as a strict schema-1 world pack."""
    town = plan["town"]
    speed = float(town["walking_speed_m_per_minute"])
    extent_x, extent_y = (float(value) for value in town["extent_m"])
    junctions = {item["id"]: item for item in plan["junctions"]}
    graph: dict[str, list[tuple[str, float]]] = {key: [] for key in junctions}
    for street in plan["streets"]:
        graph[street["from"]].append((street["to"], float(street["distance_m"])))
        graph[street["to"]].append((street["from"], float(street["distance_m"])))
    places = {item["id"]: item for item in plan["places"]}
    existing_place_ids = list(existing_places)
    known = [place_id for place_id in existing_place_ids if place_id in places]
    occupied = list(existing_places.values())
    entities: list[dict[str, Any]] = []
    for place in plan["places"]:
        place_id = place["id"]
        if (
            place_id in existing_place_ids
            or place_id in PRIVATE
            or place_id in PROVIDED_ELSEWHERE
            or place_id not in HOURS
        ):
            continue
        distances = _distances(graph, place["junction"])
        nearest = min(known, key=lambda other: (distances[places[other]["junction"]], other))
        metres = distances[places[nearest]["junction"]]
        junction = junctions[place["junction"]]
        x, y = _free_spot(
            _scale(float(junction["x"]), extent_x), _scale(float(junction["y"]), extent_y), occupied
        )
        occupied.append((x, y))
        label, description = DESCRIPTIONS[place_id]
        opens, closes = HOURS[place_id]
        entities.append(
            {
                "entity_kind": "place",
                "entity_id": place_id,
                "name": place["name"],
                "label": label,
                "description": description,
                "location_id": nearest,
                "purpose": "Support everyday life, errands and chance encounters in Alderwick.",
                "color": DISTRICT_COLOURS[place["district"]],
                "x": x,
                "y": y,
                "opens_hour": opens,
                "closes_hour": closes,
                "travel_minutes": max(2, ceil(metres / speed) + 1),
            }
        )
        known.append(place_id)
    return {
        "schema_version": 1,
        "pack_id": "alderwick",
        "version": version,
        "name": "Alderwick",
        "description": (
            "The rest of the market town around the river: shops, services, quiet paths and "
            "public places, connected along its streets. Registration provides possibilities, "
            "not invented visits, memories or relationships."
        ),
        "entities": entities,
    }


def _distances(graph: Mapping[str, list[tuple[str, float]]], start: str) -> dict[str, float]:
    best = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance > best.get(node, float("inf")):
            continue
        for neighbour, length in graph[node]:
            candidate = distance + length
            if candidate < best.get(neighbour, float("inf")):
                best[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    return best


def _free_spot(x: int, y: int, occupied: Sequence[tuple[int, int]]) -> tuple[int, int]:
    """The map point nearest the street position that keeps places visually apart."""
    candidates = sorted(
        ((cx, cy) for cx in range(5, 96) for cy in range(5, 96)),
        key=lambda point: ((point[0] - x) ** 2 + (point[1] - y) ** 2, point),
    )
    for cx, cy in candidates:
        if all(abs(cx - ox) > 8 or abs(cy - oy) > 8 for ox, oy in occupied):
            return cx, cy
    raise ValueError("The town map has no room left for another place")


def _scale(value: float, extent: float) -> int:
    return max(5, min(95, round(5 + 90 * value / extent)))


def write_town_pack(
    plan_path: Path, output: Path, existing_places: Mapping[str, tuple[int, int]]
) -> None:
    pack = build_town_pack(json.loads(plan_path.read_text()), existing_places)
    output.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")
