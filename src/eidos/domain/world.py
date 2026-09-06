"""Authored world facts and deterministic schedules shared by every role."""

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


def npc_location(person_id: str, hour: int) -> str:
    if person_id == "mara":
        return "cafe" if 7 <= hour < 17 else "home"
    if person_id == "ellis":
        return "workshop" if 9 <= hour < 18 else "park" if 18 <= hour < 20 else "home"
    return "park" if 11 <= hour < 16 else "cafe" if 8 <= hour < 11 else "home"


def location_name(location_id: str) -> str:
    return next(place["name"] for place in LOCATIONS if place["id"] == location_id)
