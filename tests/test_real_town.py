"""Alderwick on Frome's real streets: real positions and walking times, from now on."""

from datetime import datetime, timezone

from eidos.application.real_town import PLAN_ID, plan, real_town_events
from eidos.domain.events import DomainEvent
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import project_world_catalog

AT = datetime(2026, 8, 30, 9, tzinfo=timezone.utc)


def _whole_town() -> list[DomainEvent]:
    """The four seed places plus the rest of the town and his parents' house in Wye."""
    events = []
    extra = [p for p in plan()["places"] if p not in {"home", "cafe", "workshop", "park"}]
    for n, place in enumerate([*extra, "wye-home"]):
        events.append(
            DomainEvent(
                "world.place_registered",
                "pathos",
                {
                    "entity_id": place, "name": place.title(), "label": place, "description": "A place.",
                    "connected_to_id": "station" if place == "wye-home" else "cafe",
                    "x": 10 + (n * 5) % 80, "y": 10 + (n * 7) % 80, "opens_hour": 0, "closes_hour": 24,
                    "travel_minutes": 150 if place == "wye-home" else 20,
                    "simulated_at": AT.isoformat(),
                },
            )
        )  # fmt: skip
    return events


def test_the_whole_town_is_laid_on_real_streets_once() -> None:
    history = _whole_town()
    before = project_world_catalog(history)
    laid = real_town_events(history, AT, before)
    assert [e.kind for e in laid].count("world.place_relocated") == len(plan()["places"])
    assert laid[-1].kind == "world.routes_set" and laid[-1].payload["plan_id"] == PLAN_ID
    after = project_world_catalog([*history, *laid])
    minutes = plan()["all_pairs"]
    # Real walking times between neighbours, and the rest along the real streets via them.
    assert (
        route_duration("cafe", "home", after.route_minutes).total_seconds() / 60
        == minutes["cafe|home"]
    )
    station = route_duration("cafe", "station", after.route_minutes).total_seconds() / 60
    assert 12 <= station <= 20
    # The train to Wye is untouched.
    assert after.route_minutes[frozenset(("station", "wye-home"))] == 150
    assert "; " in after.places["cafe"].description
    # Once only.
    assert real_town_events([*history, *laid], AT, after) == []


def test_a_smaller_world_keeps_its_layout() -> None:
    assert real_town_events([], AT, project_world_catalog([])) == []
