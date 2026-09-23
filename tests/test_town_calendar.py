"""The town's weekly rhythm is real but optional, and he only hears of it where he knows."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_town_pack import imported_world

from eidos.application.ambient_population import ambient_population
from eidos.application.place_discovery import HOME_GROUND
from eidos.application.town_calendar import (
    CALLED_OFF_CHANCE,
    called_off,
    happening_opportunities,
    whats_on,
)
from eidos.domain.world_catalog import project_world_catalog, seed_world_catalog

TUESDAY = datetime(2026, 1, 6, 9, tzinfo=timezone.utc)


def test_nothing_is_on_in_a_world_without_the_venues() -> None:
    assert whats_on(seed_world_catalog(), None, TUESDAY, days=6) == []


def test_he_only_hears_of_happenings_at_places_he_knows(tmp_path: Path) -> None:
    catalog = project_world_catalog(imported_world(tmp_path))
    everything = whats_on(catalog, None, TUESDAY, days=6)
    assert {item["place_id"] for item in everything} >= {"crown-anchor", "market-hall", "cinema"}
    assert whats_on(catalog, HOME_GROUND, TUESDAY, days=6) == []
    known = whats_on(catalog, {*HOME_GROUND, "crown-anchor"}, TUESDAY, days=6)
    assert [item["title"] for item in known] == ["Quiz night at the Crown"]
    hall = [item["title"] for item in everything if item["place_id"] == "community-hall"]
    assert len(hall) == 1  # Repair café and drawing class alternate weeks.


def test_happenings_are_offered_with_time_to_get_there_and_some_are_called_off(
    tmp_path: Path,
) -> None:
    catalog = project_world_catalog(imported_world(tmp_path))
    offers = happening_opportunities(catalog, {"crown-anchor"}, TUESDAY)
    assert offers[0]["kind"] == "public_happening"
    assert offers[0]["action_authority"] is False
    assert "today from 19:00" in str(offers[0]["text"])
    late = TUESDAY.replace(hour=18)
    assert happening_opportunities(catalog, {"crown-anchor"}, late) == []
    rate = sum(called_off(f"quiz-{n}") for n in range(2000)) / 2000
    assert abs(rate - CALLED_OFF_CHANCE) < 0.03


def test_a_happening_draws_a_crowd(tmp_path: Path) -> None:
    catalog = project_world_catalog(imported_world(tmp_path))
    for week in range(8):
        tuesday = TUESDAY + timedelta(weeks=week)
        quiz = next(
            item
            for item in whats_on(catalog, None, tuesday, days=1)
            if item["place_id"] == "crown-anchor"
        )
        if quiz["called_off"]:
            continue
        before = ambient_population(catalog, tuesday.replace(hour=16), "clear")["crown-anchor"]
        during = ambient_population(catalog, tuesday.replace(hour=20), "clear")["crown-anchor"]
        assert during.activity == "Quiz night at the Crown"
        assert during.estimated_people >= before.estimated_people + 5
        return
    raise AssertionError("every quiz was called off")
