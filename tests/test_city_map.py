from datetime import datetime, timezone
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.application.city_map import city_map
from eidos.application.world_packs import import_world_pack
from eidos.domain.events import DomainEvent
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import project_world_catalog


def test_city_pack_is_connected_without_fabricated_visits(tmp_path):
    store = SQLiteEventStore(tmp_path / "city.sqlite3")
    pack = Path(__file__).parents[1] / "world_packs/city-life-v1.json"
    import_world_pack(store, pack, simulated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    history = store.read("pathos")
    catalog = project_world_catalog(history)
    assert len(catalog.places) == 16
    atlas = city_map(history, catalog, "home")
    for place in catalog.places:
        assert route_duration("home", place, catalog.route_minutes).total_seconds() >= 0
        assert atlas["places"][place]["visits"] == 0
    assert atlas["places"]["library"]["experience"] == "known_not_visited"
    moved = DomainEvent(
        "pathos.moved",
        "pathos",
        {"location_id": "library", "simulated_at": "2026-01-02T12:00:00+00:00"},
    )
    atlas = city_map(history + [moved], catalog, "home")
    assert atlas["places"]["library"]["visits"] == 1
    assert atlas["places"]["library"]["experience"] == "visited"
