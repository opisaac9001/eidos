"""Thousands of townsfolk exist without being stored; he meets them one at a time."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.bonds import bond_events
from eidos.application.epistemics import pathos_known_person_ids
from eidos.application.latent_town import (
    TOWN_POPULATION,
    latent_resident,
    present_at,
    regulars,
)
from eidos.application.townsfolk import (
    _valid_description,
    _valid_introduction,
    townsfolk_events,
    townsfolk_promotion_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.proposals import ProposalRejected
from eidos.domain.relationships import project_relationships
from eidos.domain.townsfolk import project_townsfolk
from eidos.domain.world_catalog import project_world_catalog, seed_world_catalog

START = datetime(2026, 1, 5, tzinfo=timezone.utc)
CATALOG = seed_world_catalog()


def test_the_town_is_thousands_strong_and_the_same_every_time() -> None:
    assert TOWN_POPULATION >= 5_000
    assert latent_resident(42) == latent_resident(42)
    cafe = regulars("cafe", "social")
    assert 80 < len(cafe) < 400
    counts = [len(present_at("cafe", "social", START + timedelta(hours=h))) for h in range(8, 20)]
    assert max(counts) > 0 and sum(counts) / len(counts) < 40
    assert present_at("cafe", "social", START.replace(hour=11)) == present_at(
        "cafe", "social", START.replace(hour=11)
    )


def live_at_the_cafe(days: int) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    gateway = StandInGateway()
    for day in range(days):
        for hour in range(9, 18):
            at = START + timedelta(days=day, hours=hour)
            history += asyncio.run(
                townsfolk_events(
                    history,
                    at,
                    gateway,
                    location_id="cafe",
                    awake=True,
                    busy=False,
                    catalog=project_world_catalog(history),
                    crowd=8,
                )
            )
        evening = START + timedelta(days=day, hours=20)
        names = project_townsfolk(history).names()
        history += bond_events(
            history,
            evening,
            project_relationships(history).relationships,
            pathos_known_person_ids(history),
            names,
        )
        history += townsfolk_promotion_events(
            history, evening.replace(hour=21), project_world_catalog(history)
        )
    return history


@pytest.fixture(scope="module")
def cafe_life() -> list[DomainEvent]:
    return live_at_the_cafe(200)


def test_faces_become_familiar_then_get_names(cafe_life) -> None:
    state = project_townsfolk(cafe_life)
    assert len(state.people) >= 10
    assert any(person.sightings >= 2 for person in state.people.values())
    named = state.acquaintances()
    assert named and all(person.name and person.occupation for person in named)
    assert len({person.name for person in named}) == len(named)
    per_day: dict[str, int] = {}
    for event in cafe_life:
        if event.kind.startswith("townsfolk."):
            day = event.payload["simulated_at"][:10]
            per_day[day] = per_day.get(day, 0) + 1
    assert max(per_day.values()) <= 2


def test_only_people_he_knows_by_name_count_as_known(cafe_life) -> None:
    state = project_townsfolk(cafe_life)
    known = pathos_known_person_ids(cafe_life)
    for person in state.faces():
        assert person.townsfolk_id not in known
    for person in state.acquaintances():
        assert person.townsfolk_id in known


def test_a_townsperson_who_becomes_a_friend_becomes_a_resident(cafe_life) -> None:
    promoted = [e for e in cafe_life if e.kind == "world.person_registered"]
    assert promoted, "someone met repeatedly over 200 days should become a friend"
    person_id = promoted[0].payload["entity_id"]
    catalog = project_world_catalog(cafe_life)
    assert catalog.people[person_id].name == promoted[0].payload["name"]
    assert person_id in project_npcs(cafe_life, START + timedelta(days=201)).people
    assert len(promoted) == len({e.payload["entity_id"] for e in promoted})
    # From then on they live their own simulated day; the latent routine no longer places them.
    promoted_at = promoted[0].payload["simulated_at"]
    later = [
        e
        for e in cafe_life
        if e.kind.startswith("townsfolk.")
        and e.payload.get("townsfolk_id") == person_id
        and e.payload["simulated_at"] > promoted_at
    ]
    assert later == []


def test_firmament_proposals_are_checked() -> None:
    assert _valid_description("A man in a flat cap reading.") == "a man in a flat cap reading"
    for bad in (
        "Mr Jones by the till",
        "a man",
        "a man called Patrick at the bar",
        "a 40 year old",
    ):
        with pytest.raises(ProposalRejected):
            _valid_description(bad)
    good = {"name": "June Hollis", "occupation": "Retired postmistress", "first_words": "Hello!"}
    assert _valid_introduction(good, set()) == ("June Hollis", "retired postmistress", "Hello!")
    with pytest.raises(ProposalRejected):
        _valid_introduction(good, {"June Hollis"})
    with pytest.raises(ProposalRejected):
        _valid_introduction({**good, "name": "june"}, set())
    with pytest.raises(ProposalRejected):
        _valid_introduction({**good, "first_words": "Hi Pathos!"}, set())


def test_nobody_is_noticed_at_home_asleep_or_mid_conversation() -> None:
    at = START.replace(hour=11)
    for kwargs in (
        {"location_id": "home", "awake": True, "busy": False},
        {"location_id": "cafe", "awake": False, "busy": False},
        {"location_id": "cafe", "awake": True, "busy": True},
    ):
        assert (
            asyncio.run(
                townsfolk_events([], at, StandInGateway(), catalog=CATALOG, crowd=30, **kwargs)
            )
            == []
        )
