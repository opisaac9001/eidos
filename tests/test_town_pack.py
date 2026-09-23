"""Alderwick arrives as an ordinary pack, and Patrick has to discover it."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.application.place_discovery import (
    HOME_GROUND,
    known_place_ids,
    known_world,
    place_discovery_events,
)
from eidos.application.town_pack import build_town_pack
from eidos.application.world_packs import import_world_pack
from eidos.domain.events import DomainEvent
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import project_world_catalog, seed_world_catalog

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "world_plans" / "alderwick-v1.json"
PACK = ROOT / "world_packs" / "alderwick-v1.json"
CITY = ROOT / "world_packs" / "city-life-v1.json"
NOW = datetime(2026, 1, 3, 11, tzinfo=timezone.utc)


def existing_positions() -> dict[str, tuple[int, int]]:
    places = {pid: (p.x, p.y) for pid, p in seed_world_catalog().places.items()}
    for entity in json.loads(CITY.read_text())["entities"]:
        if entity["entity_kind"] == "place":
            places[entity["entity_id"]] = (entity["x"], entity["y"])
    return places


def test_committed_pack_is_exactly_what_the_blueprint_builds() -> None:
    built = build_town_pack(json.loads(PLAN.read_text()), existing_positions())
    assert built == json.loads(PACK.read_text())
    ids = {entity["entity_id"] for entity in built["entities"]}
    assert "primary-school" not in ids and "southbank-housing" not in ids
    assert "reading-room" not in ids


def imported_world(tmp_path: Path) -> list[DomainEvent]:
    store = SQLiteEventStore(tmp_path / "town.sqlite3")
    for pack in (CITY, PACK):
        import_world_pack(store, pack, simulated_at=NOW)
    return store.read("pathos")


def test_the_whole_town_imports_and_is_walkable(tmp_path: Path) -> None:
    history = imported_world(tmp_path)
    catalog = project_world_catalog(history)
    assert len(catalog.places) == 39
    for place_id in catalog.places:
        minutes = (
            route_duration("home", place_id, catalog.route_minutes) if place_id != "home" else None
        )
        assert minutes is None or timedelta(minutes=1) <= minutes <= timedelta(minutes=90)


def test_importing_the_town_does_not_make_him_know_it(tmp_path: Path) -> None:
    history = imported_world(tmp_path)
    catalog = project_world_catalog(history)
    assert known_place_ids(history, catalog) == HOME_GROUND
    visited = DomainEvent(
        "pathos.moved",
        "pathos",
        {
            "location_id": "hardware",
            "from_location_id": "workshop",
            "simulated_at": NOW.isoformat(),
        },
    )
    assert "hardware" in known_place_ids([*history, visited], catalog)
    invited = DomainEvent(
        "invitation.made",
        "pathos",
        {"inviter_id": "mara", "invitee_id": "pathos", "location_id": "crown-anchor"},
    )
    assert "crown-anchor" in known_place_ids([*history, invited], catalog)


def test_he_notices_new_places_nearby_at_most_once_a_day(tmp_path: Path) -> None:
    history = imported_world(tmp_path)
    catalog = project_world_catalog(history)
    found = []
    for day in range(30):
        at = NOW + timedelta(days=day)
        output = place_discovery_events(history, catalog, "workshop", True, at)
        assert len([e for e in output if e.kind == "place.discovered"]) <= 1
        assert place_discovery_events([*history, *output], catalog, "workshop", True, at) == []
        history = [*history, *output]
        found += [e.payload["place_id"] for e in output if e.kind == "place.discovered"]
    assert found
    near_workshop = {
        other for route in catalog.route_minutes if "workshop" in route for other in route
    }
    assert set(found) <= near_workshop
    assert place_discovery_events(history, catalog, "home", True, NOW) == []


def test_his_known_world_hides_unknown_places_but_keeps_the_streets(tmp_path: Path) -> None:
    history = imported_world(tmp_path)
    catalog = project_world_catalog(history)
    known = known_world(history, catalog)
    assert set(known.places) == HOME_GROUND
    assert known.route_minutes == catalog.route_minutes
    assert set(known.opening_hours) == HOME_GROUND
    noticed = place_discovery_events(history, catalog, "workshop", True, NOW)
    for day in range(1, 30):
        if noticed:
            break
        noticed = place_discovery_events(
            history, catalog, "workshop", True, NOW + timedelta(days=day)
        )
    place_id = noticed[0].payload["place_id"]
    assert place_id in known_world([*history, *noticed], catalog).places
