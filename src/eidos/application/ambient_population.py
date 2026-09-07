"""Cheap anonymous town life that exists below persistent character detail."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Mapping

from eidos.domain.world_catalog import WorldCatalog, WorldPlace


@dataclass(frozen=True, slots=True)
class AmbientPresence:
    """An aggregate presence, deliberately without names or person identifiers."""

    place_id: str
    estimated_people: int
    pace: str
    activity: str


def ambient_population(
    catalog: WorldCatalog, simulated_at: datetime, weather: str
) -> Mapping[str, AmbientPresence]:
    """Derive replay-stable public footfall without creating fictional individuals."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Ambient population time must be timezone-aware")
    return {
        place.place_id: _presence(place, simulated_at, weather) for place in catalog.places.values()
    }


def _presence(place: WorldPlace, at: datetime, weather: str) -> AmbientPresence:
    if place.place_id == "home" or not _is_open(place, at.hour):
        return AmbientPresence(place.place_id, 0, "empty", "No public footfall")
    kind = _place_kind(place)
    base = _base_count(kind, at.hour)
    if at.weekday() >= 5:
        base += 2 if kind in {"park", "cafe"} else -1
    lowered_weather = weather.casefold()
    if any(word in lowered_weather for word in ("rain", "storm", "snow")):
        base += 2 if kind == "cafe" else -4 if kind == "park" else -1
    elif any(word in lowered_weather for word in ("clear", "sun")) and kind == "park":
        base += 2
    variation = _sample(f"{at.date().isoformat()}:{at.hour}:{place.place_id}") % 5 - 2
    count = max(0, base + variation)
    return AmbientPresence(
        place.place_id,
        count,
        _pace(count),
        _activity(kind, at.hour, _sample(f"activity:{at.date()}:{at.hour}:{place.place_id}")),
    )


def _is_open(place: WorldPlace, hour: int) -> bool:
    return place.opens_hour <= hour < place.closes_hour


def _place_kind(place: WorldPlace) -> str:
    text = f"{place.place_id} {place.name} {place.description}".casefold()
    for kind, markers in {
        "cafe": ("cafe", "café", "tea", "coffee"),
        "workshop": ("workshop", "repair", "studio", "craft"),
        "park": ("park", "square", "garden", "green"),
    }.items():
        if any(marker in text for marker in markers):
            return kind
    return "public"


def _base_count(kind: str, hour: int) -> int:
    if kind == "cafe":
        return 8 if 7 <= hour < 10 else 6 if 10 <= hour < 14 else 4
    if kind == "workshop":
        return 2 if hour < 10 else 5 if hour < 17 else 3
    if kind == "park":
        return 3 if hour < 9 else 7 if hour < 16 else 9 if hour < 20 else 3
    return 2 if hour < 9 else 5 if hour < 18 else 3


def _pace(count: int) -> str:
    if count == 0:
        return "empty"
    if count <= 2:
        return "quiet"
    if count <= 6:
        return "gently active"
    if count <= 10:
        return "busy"
    return "crowded"


def _activity(kind: str, hour: int, sample: int) -> str:
    palettes = {
        "cafe": (
            "People come and go with drinks and small conversations",
            "A few tables turn over while others linger",
            "Orders, chairs, and half-heard conversations overlap",
        ),
        "workshop": (
            "People move between benches and shared tools",
            "Small jobs start, pause, and change hands",
            "Tools sound intermittently around quiet concentration",
        ),
        "park": (
            "Walkers cross paths while others stay on benches",
            "People pass through in loose, changing groups",
            "Children, dogs, bicycles, and quiet sitters share the space",
        ),
        "public": (
            "People pass through on unrelated errands",
            "The mix of arrivals and departures keeps changing",
            "Several ordinary activities overlap without a single focus",
        ),
    }
    options = palettes[kind]
    return options[(sample + hour) % len(options)]


def _sample(key: str) -> int:
    return int(sha256(key.encode()).hexdigest()[:8], 16)
