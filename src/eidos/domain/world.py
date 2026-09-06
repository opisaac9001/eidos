"""Authored world facts and deterministic schedules shared by every role."""

from datetime import datetime, time
from typing import Mapping

LOCATIONS = (
    {
        "id": "home",
        "name": "The apartment",
        "label": "Home",
        "x": 23,
        "y": 24,
        "description": "A small upstairs apartment. Books on the table, a kettle by the window.",
    },
    {
        "id": "cafe",
        "name": "Juniper Café",
        "label": "Café",
        "x": 70,
        "y": 22,
        "description": "The neighborhood's morning meeting place. Mara tends the counter.",
    },
    {
        "id": "workshop",
        "name": "The workshop",
        "label": "Workshop",
        "x": 73,
        "y": 73,
        "description": "A shared repair studio, full of unfinished objects and patient work.",
    },
    {
        "id": "park",
        "name": "Willow Square",
        "label": "Park",
        "x": 25,
        "y": 75,
        "description": "A quiet square between home and work. Rowan comes here to sketch.",
    },
)

PEOPLE = (
    {
        "id": "mara",
        "name": "Mara",
        "occupation": "Café owner",
        "color": "#e9b36f",
        "description": "Observant, dryly funny, and protective of her regulars.",
    },
    {
        "id": "ellis",
        "name": "Ellis",
        "occupation": "Repair artist",
        "color": "#96b9da",
        "description": "Patient with objects, restless with unfinished conversations.",
    },
    {
        "id": "rowan",
        "name": "Rowan",
        "occupation": "Illustrator",
        "color": "#b1c696",
        "description": "Curious about ordinary things most people walk past.",
    },
)

NPC_PLAN_PROFILES = {
    "mara": {
        "action": "host",
        "location_id": "cafe",
        "title": "Host a welcoming hour for neighborhood conversation",
    },
    "ellis": {
        "action": "repair",
        "location_id": "workshop",
        "title": "Repair an item for the next community gathering",
    },
    "rowan": {
        "action": "sketch",
        "location_id": "park",
        "title": "Sketch the next community gathering",
    },
}

ROLES = (
    {"id": "pathos", "name": "Pathos", "purpose": "Voice & conscious response"},
    {"id": "murmur", "name": "The Murmur", "purpose": "Associations & inner life"},
    {"id": "firmament", "name": "Firmament", "purpose": "Neighbors & encounters"},
    {"id": "moira", "name": "Moira", "purpose": "Weather & world rhythm"},
    {"id": "mnemosyne", "name": "Mnemosyne", "purpose": "Memory & provenance"},
    {"id": "reflection", "name": "Reflection", "purpose": "Evening perspective"},
    {"id": "oneiros", "name": "Oneiros", "purpose": "Dream composition"},
    {"id": "chronicler", "name": "The Chronicler", "purpose": "A factual daybook"},
    {"id": "critic", "name": "Continuity critic", "purpose": "Proposal validation"},
)

# Simulation-local opening windows. The end is exclusive for arrival and inclusive
# for an activity ending exactly at closing time.
OPEN_HOURS = {
    "home": (time(0), time(23, 59, 59, 999999)),
    "cafe": (time(7), time(18)),
    "workshop": (time(8), time(20)),
    "park": (time(6), time(22)),
}


def location_allows_interval(
    location_id: str,
    starts_at: datetime,
    ends_at: datetime,
    opening_hours: Mapping[str, tuple[time, time]] | None = None,
) -> bool:
    """Return whether one same-day activity fits within a known place's hours."""
    hours = (opening_hours or OPEN_HOURS).get(location_id)
    if hours is None or starts_at.tzinfo is None or ends_at.tzinfo is None:
        return False
    if ends_at <= starts_at:
        return False
    if location_id == "home":
        return True
    if starts_at.date() != ends_at.date():
        return False
    opens_at, closes_at = hours
    return starts_at.time() >= opens_at and ends_at.time() <= closes_at


def npc_location(person_id: str, hour: int, home_location_id: str = "home") -> str:
    if person_id == "mara":
        return "cafe" if 7 <= hour < 17 else "home"
    if person_id == "ellis":
        return "workshop" if 9 <= hour < 18 else "park" if 18 <= hour < 20 else "home"
    if person_id == "rowan":
        return "park" if 11 <= hour < 16 else "cafe" if 8 <= hour < 11 else "home"
    return home_location_id if 8 <= hour < 17 else "home"


def npc_activity(person_id: str, location_id: str) -> tuple[str, str]:
    """Return the structured action and private narration for an ordinary activity."""
    if location_id == "home":
        return "rest", "resting at home"
    known = {
        "mara": ("host", "running the cafe"),
        "ellis": (
            ("repair", "working on repairs")
            if location_id == "workshop"
            else ("walk", "taking a walk")
        ),
        "rowan": (
            ("sketch", "sketching") if location_id == "park" else ("visit", "visiting the cafe")
        ),
    }
    return known.get(person_id, ("attend", "spending time nearby"))


def npc_plan_profile(person_id: str, location_id: str = "park") -> dict[str, str]:
    profile = NPC_PLAN_PROFILES.get(person_id)
    if profile is not None:
        return profile
    return {
        "action": "attend",
        "location_id": location_id,
        "title": "Spend time among familiar people",
    }


def location_name(location_id: str) -> str:
    return str(next(place["name"] for place in LOCATIONS if place["id"] == location_id))
