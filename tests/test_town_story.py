"""The town has quiet weeks and then something that matters, and it changes people's days."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone

import pytest

from eidos.application import town_story
from eidos.application.npc_movement import their_place_now
from eidos.application.town_story import (
    KIND,
    QUIET_DAYS,
    STORIES,
    as_today,
    both_know,
    closed_places,
    heard_lately,
    mentioned,
    power_out,
    town_story_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import WorldPlace, project_world_catalog

START = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
RESIDENTS = frozenset({"mara", "ellis", "rowan"})
BY_KIND = {story.kind: story for story in STORIES}


def _catalog():
    catalog = project_world_catalog([])
    extra = {
        "riverside": WorldPlace("riverside", "Riverside Walk", "", "", 1, 1, 0, 24),
        "bakery": WorldPlace("bakery", "Mill Street Bakery", "", "", 2, 2, 6, 16),
        "market-hall": WorldPlace("market-hall", "Market Hall", "", "", 3, 3, 7, 18),
    }
    return replace(catalog, places={**catalog.places, **extra})


def _begun() -> list[DomainEvent]:
    return [DomainEvent("time.advanced", "pathos", {"simulated_at": START.isoformat()})]


def _weather(at: datetime, text: str) -> DomainEvent:
    return DomainEvent("world.weather", "pathos", {"text": text, "simulated_at": at.isoformat()})


def _live(days: int, *, on_phone_at: int = 20) -> list[DomainEvent]:
    """Months of a town, an hour at a time, with him at home and on his phone of an evening."""
    catalog = _catalog()
    history = _begun()
    at = START
    for _ in range(days * 24):
        if at.hour % 6 == 0:
            text = ("Clear", "Cloudy", "Light rain", "Breezy")[(at.day * 7 + at.hour) % 4]
            history.append(_weather(at, text))
        history += town_story_events(
            history,
            at,
            catalog=catalog,
            residents=RESIDENTS,
            locations={person: "home" for person in RESIDENTS},
            location_id="home",
            awake=8 <= at.hour <= 22,
            on_phone=at.hour == on_phone_at,
        )
        at += timedelta(hours=1)
    return history


@pytest.fixture(scope="module")
def half_a_year() -> list[DomainEvent]:
    return _live(180)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def test_the_town_has_quiet_weeks_between_its_stories(half_a_year) -> None:
    happened = [e for e in half_a_year if e.kind == KIND and e.payload["stage"] == "happened"]
    # Something every week or two, not every day, and not never.
    assert 8 <= len(happened) <= 26
    for before, after in zip(happened, happened[1:]):
        quiet = QUIET_DAYS[BY_KIND[str(before.payload["story_kind"])].weight]
        assert _when(after) - _when(before) >= timedelta(days=quiet)
        assert before.payload["story_kind"] != after.payload["story_kind"]
    big = [_when(e) for e in happened if int(e.payload["weight"]) == 3]
    for one, two in zip(big, big[1:]):
        assert two - one >= timedelta(days=town_story.BIG_GAP_DAYS)
    # A varied town, not the same burst main again and again.
    assert len({e.payload["story_kind"] for e in happened}) >= 5


def test_word_goes_round_and_he_hears_some_of_it_his_own_way(half_a_year) -> None:
    heard = [e for e in half_a_year if e.kind == "gossip.heard"]
    stories = {e.payload["story_id"] for e in half_a_year if e.kind == KIND}
    by_resident = {e.payload["claim_id"] for e in heard if e.payload["holder_id"] != "pathos"}
    assert len(by_resident) >= len(stories) // 2
    his = [e for e in heard if e.payload["holder_id"] == "pathos"]
    assert his and all(e.payload["heard_from"] for e in his)
    # Once each, and remembered in his words with how he heard it.
    assert len({e.payload["claim_id"] for e in his}) == len(his)
    memories = [
        e for e in half_a_year if e.kind == "memory.recorded" and e.payload["source"] ==
        "lived-town-story"
    ]  # fmt: skip
    assert len(memories) == len(his)
    assert any(m.payload["text"].startswith("On the Alderwick Facebook group:") for m in memories)
    # A coda only reaches him if he knew the first part.
    knew = {e.payload["claim_id"] for e in his}
    for event in his:
        if str(event.payload["claim_id"]).endswith(":after"):
            assert str(event.payload["claim_id"]).removesuffix(":after") in knew


def _happened(kind: str, at: datetime, **extra: object) -> DomainEvent:
    story = BY_KIND[kind]
    payload: dict[str, object] = {
        "story_id": f"{kind}-{at.date().isoformat()}",
        "story_kind": kind,
        "stage": "happened",
        "weight": story.weight,
        "text": story.told[0].replace("{place}", "Juniper Café"),
        "simulated_at": at.isoformat(),
        "owner": "world",
        **extra,
    }
    return DomainEvent(KIND, "pathos", payload)


def test_a_burst_main_shuts_the_cafe_and_mara_stays_home() -> None:
    at = datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)
    history = [
        _happened(
            "burst_main",
            at,
            location_id="cafe",
            place_name="Juniper Café",
            closed_until=(at + timedelta(days=2)).isoformat(),
        )
    ]
    noon = at + timedelta(hours=5)
    assert set(closed_places(history, noon)) == {"cafe"}
    today = as_today(_catalog(), closed_places(history, noon))
    assert today.opening_hours["cafe"] == (time(0), time(0))
    assert today.opening_hours["park"] != (time(0), time(0))
    # Mara would be opening up; today she's at home.
    assert their_place_now("mara", "cafe", noon, _catalog().opening_hours) == "cafe"
    assert their_place_now("mara", "cafe", noon, today.opening_hours) == "home"
    assert closed_places(history, at + timedelta(days=2, hours=1)) == {}


def test_walking_past_the_shut_cafe_is_how_he_finds_out() -> None:
    at = datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)
    history = [
        *_begun(),
        _happened(
            "burst_main",
            at,
            location_id="cafe",
            place_name="Juniper Café",
            closed_until=(at + timedelta(days=2)).isoformat(),
        ),
    ]
    found = town_story_events(
        history,
        at + timedelta(hours=3),
        catalog=_catalog(),
        residents=RESIDENTS,
        locations={},
        location_id="cafe",
        awake=True,
        on_phone=False,
    )
    mine = [e for e in found if e.kind == "gossip.heard" and e.payload["holder_id"] == "pathos"]
    assert mine and mine[0].payload["heard_from"] == "there"
    memory = next(e for e in found if e.kind == "memory.recorded")
    assert "Juniper Café shut" in memory.payload["text"]
    assert heard_lately([*history, *found], at + timedelta(hours=4))


def test_a_power_cut_means_no_kettle_and_no_records() -> None:
    at = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
    history = [_happened("power_cut", at, power_until=(at + timedelta(hours=3)).isoformat())]
    assert power_out(history, at + timedelta(hours=1))
    assert not power_out(history, at + timedelta(hours=4))
    assert {"kettle_tea", "record_side", "laptop_game"} <= town_story.NEEDS_POWER
    assert "read_book" not in town_story.NEEDS_POWER


def test_they_talk_about_it_when_both_have_heard() -> None:
    at = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
    happened = _happened("chip_shop_fire", at)
    story = BY_KIND["chip_shop_fire"]
    claim = f"town:{happened.payload['story_id']}"

    def heard(holder: str) -> DomainEvent:
        return DomainEvent(
            "gossip.heard",
            "pathos",
            {
                "claim_id": claim,
                "story": "town:chip_shop_fire",
                "subject_id": "town",
                "holder_id": holder,
                "teller_id": "",
                "text": story.told[0],
                "version": 0,
                "strength": 1.0,
                "simulated_at": at.isoformat(),
            },
        )

    later = at + timedelta(days=1)
    assert both_know([happened, heard("mara")], later, "mara") == []
    assert both_know([happened, heard("mara"), heard("pathos")], later, "mara")[0][0] == claim
    # Two weeks on, nobody's talking about it any more.
    assert (
        both_know([happened, heard("mara"), heard("pathos")], at + timedelta(days=15), "mara") == []
    )
    assert mentioned("town:chip_shop_fire", "Did you hear about the chippy? Awful.")
    assert not mentioned("town:chip_shop_fire", "Lovely morning, isn't it.")


def test_the_river_only_floods_after_a_wet_spell() -> None:
    at = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)
    river = BY_KIND["river_up"]
    dry = [_weather(at - timedelta(hours=6 * i), "Clear") for i in range(12)]
    wet = [_weather(at - timedelta(hours=6 * i), "Light rain") for i in range(12)]
    assert not town_story._conditions_met(river, dry, at)
    assert town_story._conditions_met(river, wet, at)


def _he_holds(claim: str, kind: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "gossip.heard",
        "pathos",
        {
            "claim_id": claim,
            "story": f"town:{kind}",
            "subject_id": "town",
            "holder_id": "pathos",
            "teller_id": "",
            "text": "…",
            "version": 0,
            "strength": 1.0,
            "simulated_at": at.isoformat(),
        },
    )


def _hour(history, at, location_id="home", **extra):
    return town_story_events(
        history,
        at,
        catalog=project_world_catalog(history),
        residents=RESIDENTS,
        locations={},
        location_id=location_id,
        awake=True,
        on_phone=False,
        **extra,
    )


def test_the_record_shop_opens_and_hearing_so_is_how_he_finds_it() -> None:
    at = datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc)
    opened = at + timedelta(days=5)
    history = [*_begun(), _happened("record_shop", at)]
    coda = _hour(history, opened)
    history += coda
    assert any(e.kind == "world.place_registered" for e in coda)
    assert "record-shop" in project_world_catalog(history).places
    assert not any(e.kind == "place.discovered" for e in coda)
    history += [
        _he_holds("town:record_shop-2026-09-08", "record_shop", at),
        _he_holds("town:record_shop-2026-09-08:after", "record_shop", opened),
    ]
    later = _hour(history, opened + timedelta(hours=1))
    found = [e for e in later if e.kind == "place.discovered"]
    assert found and found[0].payload["place_id"] == "record-shop"
    from eidos.application.everyday import REPERTOIRE

    assert any(doing.places == ("record-shop",) for doing in REPERTOIRE)


def test_he_decides_about_dennis_s_funeral_and_the_decision_books_it() -> None:
    from eidos.domain.planning import project_planning

    at = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    history = [
        *_begun(),
        _happened("fixture_died", at),
        _he_holds("town:fixture_died-2026-09-11", "fixture_died", at),
    ]
    out = _hour(
        history,
        at + timedelta(hours=1),
        values={"care": 0.95},
        planning=project_planning(history),
        knew_dennis=True,
    )
    decision = next(e for e in out if e.kind == "town.story_decided")
    memory = next(e for e in out if e.kind == "memory.recorded")
    assert "Dennis's funeral" in memory.payload["text"]
    assert decision.payload["decision"] == "go"
    if True:
        booked = next(e for e in out if e.kind == "schedule.created")
        assert booked.causation_id == decision.event_id
        assert booked.payload["location_id"] == "st-johns"
        assert (
            datetime.fromisoformat(booked.payload["starts_at"]).date()
            == (at + timedelta(days=9)).date()
        )
        assert "st-johns" in project_world_catalog([*history, *out]).places
    # He only decides once; and not at all about someone he never knew.
    assert not any(
        e.kind == "town.story_decided"
        for e in _hour([*history, *out], at + timedelta(hours=2), knew_dennis=True,
                       planning=project_planning([*history, *out]))
    )  # fmt: skip
    assert not any(
        e.kind == "town.story_decided"
        for e in _hour(history, at + timedelta(hours=1), planning=project_planning(history))
    )


def test_a_fiver_in_the_jar_next_time_hes_in_town() -> None:
    at = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    coda_at = at + timedelta(days=10)
    coda = DomainEvent(
        KIND,
        "pathos",
        {
            "story_id": "chip_shop_fire-2026-09-10",
            "story_kind": "chip_shop_fire",
            "stage": "after",
            "weight": 1,
            "text": "There's a collection going round.",
            "simulated_at": coda_at.isoformat(),
        },
    )
    history = [
        *_begun(),
        _happened("chip_shop_fire", at),
        coda,
        _he_holds("town:chip_shop_fire-2026-09-10:after", "chip_shop_fire", coda_at),
    ]
    assert not any(e.kind == "spending.made" for e in _hour(history, coda_at + timedelta(hours=2)))
    out = _hour(history, coda_at + timedelta(hours=3), location_id="cafe")
    spent = [e for e in out if e.kind == "spending.made"]
    assert spent and spent[0].payload["cost_pence"] == 500
    assert not any(
        e.kind == "spending.made"
        for e in _hour([*history, *out], coda_at + timedelta(hours=4), location_id="cafe")
    )
