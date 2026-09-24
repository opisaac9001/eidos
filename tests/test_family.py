"""His family keeps in touch from a distance; their lives go on and he hears about them."""

from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.standin_gateway import _standin_family_reply
from eidos.application.family import FAMILY, NEWS, _easter, family_context, family_events
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import value_evidence

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def live(days: int, *, at_home_after: int = 0) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    for hour in range(days * 24):
        at = START + timedelta(hours=hour)
        awake = 8 <= at.hour <= 22
        history += family_events(
            history,
            at,
            awake=awake,
            at_home=at.hour >= at_home_after,
            in_conversation=False,
            connection=0.5,
        )
    return history


@pytest.fixture(scope="module")
def year() -> list[DomainEvent]:
    return live(366)


def test_mum_rings_most_sundays_and_tom_keeps_the_chat_going(year) -> None:
    contacts = [e for e in year if e.kind == "family.contact"]
    sunday_calls = [e for e in contacts if str(e.payload["contact_id"]).startswith("mum-sunday")]
    assert 30 <= len(sunday_calls) <= 45
    assert all(
        datetime.fromisoformat(e.payload["simulated_at"]).weekday() == 6 for e in sunday_calls
    )
    tom = [e for e in contacts if e.payload["person_id"] == "tom"]
    assert len(tom) >= 60
    assert any(e.payload["channel"] == "call" for e in tom)


def test_their_lives_unfold_a_step_at_a_time(year) -> None:
    news = [e for e in year if e.kind == "family.news"]
    assert {e.payload["person_id"] for e in news} == set(FAMILY)
    by_story: dict[str, list[DomainEvent]] = {}
    for event in news:
        by_story.setdefault(event.payload["story"], []).append(event)
    for story, steps in by_story.items():
        assert [e.payload["step"] for e in steps] == list(range(len(steps)))
        for earlier, later in zip(steps, steps[1:]):
            gap = datetime.fromisoformat(later.payload["simulated_at"]) - datetime.fromisoformat(
                earlier.payload["simulated_at"]
            )
            assert gap >= timedelta(days=14)
    knee = by_story.get("dad-0", [])
    if len(knee) == len(NEWS["dad"][0]):
        assert "walking" in knee[-1].payload["text"]


def test_birthdays_are_remembered_or_forgotten_and_felt(year) -> None:
    occasions = [e for e in year if e.kind == "family.occasion"]
    ids = {str(e.payload["occasion_id"]).removesuffix("-late") for e in occasions}
    assert {"mum-birthday-2026", "dad-birthday-2026", "tom-birthday-2026"} <= ids
    easter = _easter(2026)
    assert easter.isoformat() == "2026-04-05"
    for event in occasions:
        if event.payload["outcome"] == "forgot":
            assert value_evidence(event)[0][:2] == ("care", -1)
    his_birthday = [e for e in year if e.payload.get("contact_id") == "his-birthday-2026"]
    assert his_birthday and "sing" in his_birthday[0].payload["text"]


def test_a_missed_call_is_owed_until_he_rings_back() -> None:
    history = live(120, at_home_after=23)  # rarely home in the evening: calls get missed
    missed = [e for e in history if e.kind == "family.contact" and e.payload["missed"]]
    assert missed
    rang_back = [e for e in history if str(e.payload.get("contact_id", "")).startswith("ringback")]
    assert rang_back
    assert all(
        value_evidence(e)[0][:2] == ("care", -1) for e in history if e.kind == "family.call_owed"
    )
    context = family_context(history, START + timedelta(days=120))
    assert {item["relation"] for item in context} == {"mother", "father", "older brother"}


def test_he_can_talk_about_his_family(year) -> None:
    context = {
        "identity": {"selfhood": {"family": family_context(year, START + timedelta(days=366))}}
    }
    assert "Dad" in str(_standin_family_reply("how's your dad doing?", context))
    assert "Tom" in str(_standin_family_reply("how is tom?", context))
    assert _standin_family_reply("what are you doing tomorrow?", context) is None


def test_he_goes_home_for_christmas_and_is_fed_there() -> None:
    from dataclasses import replace as _replace

    from eidos.application.activity_execution import activity_effort
    from eidos.application.family import FAMILY_HOME, christmas_events
    from eidos.application.nourishment import nourishment_events
    from eidos.domain.planning import project_planning
    from eidos.domain.state import PathosState
    from eidos.domain.world_catalog import project_world_catalog, seed_world_catalog

    catalog = seed_world_catalog()
    sixth = datetime(2026, 12, 6, 19, tzinfo=timezone.utc)
    agreed = christmas_events([], sixth, catalog, awake=True, location_id="home")
    kinds = [e.kind for e in agreed]
    assert kinds[:2] == ["family.plan_agreed", "world.place_registered"]
    assert "schedule.created" in kinds
    assert christmas_events(agreed, sixth, catalog, awake=True, location_id="home") == []
    catalog = project_world_catalog(agreed)
    assert FAMILY_HOME in catalog.places
    entry = project_planning(agreed).calendar["christmas-2026"]
    assert entry.location_id == FAMILY_HOME and entry.starts_at.startswith("2026-12-23")

    christmas_day = datetime(2026, 12, 25, 14, tzinfo=timezone.utc)
    moment = christmas_events(agreed, christmas_day, catalog, awake=True, location_id=FAMILY_HOME)
    assert moment and moment[0].payload["channel"] == "in_person"
    assert value_evidence(moment[0])[0][:2] == ("care", 1)

    state = _replace(
        PathosState(), location_id=FAMILY_HOME, awake=True, hunger=0.6, simulated_at=christmas_day
    )
    meal = nourishment_events(
        agreed,
        state,
        christmas_day.replace(hour=13),
        project_planning(agreed),
        0,
        pathos_busy=False,
    )
    assert meal and meal[0].payload["provision_source"] == "family_table"
    assert all(e.kind != "object.stock_changed" for e in meal)

    # Sleeping at his parents' still counts as being there.
    arrived = DomainEvent(
        "pathos.moved",
        "pathos",
        {"location_id": FAMILY_HOME, "simulated_at": "2026-12-23T19:00:00+00:00"},
    )
    started = DomainEvent(
        "activity.execution_started",
        "pathos",
        {
            "schedule_id": "christmas-2026",
            "required_seconds": 320400.0,
            "simulated_at": "2026-12-23T19:00:00+00:00",
        },
    )
    asleep = DomainEvent("sleep.started", "pathos", {"simulated_at": "2026-12-23T23:00:00+00:00"})
    effort = activity_effort(
        [*agreed, arrived, started, asleep], entry, datetime(2026, 12, 24, 6, tzinfo=timezone.utc)
    )
    assert effort["blocked_by"] is None


def test_when_their_stories_run_out_firmament_writes_new_ones() -> None:
    import asyncio

    import pytest as _pytest

    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.family_stories import _valid_steps, family_storyline_events
    from eidos.domain.proposals import ProposalRejected

    history: list[DomainEvent] = []
    gateway = StandInGateway()
    for hour in range(730 * 24):
        at = START + timedelta(hours=hour)
        history += family_events(
            history,
            at,
            awake=8 <= at.hour <= 22,
            at_home=True,
            in_conversation=False,
            connection=0.5,
        )
        if at.weekday() == 6 and at.hour == 11:
            history += asyncio.run(family_storyline_events(history, at, gateway))
    written = [e for e in history if e.kind == "family.storyline_written"]
    assert written
    year_two = [
        e for e in history if e.kind == "family.news" and e.payload["simulated_at"] >= "2027"
    ]
    assert any("-w" in str(e.payload["story"]) for e in year_two)
    for bad in (
        ["Dad died peacefully."],
        ["I went to see them and it was lovely."],
        ["The weather in Wye has been grey all week."],
    ):
        with _pytest.raises(ProposalRejected):
            _valid_steps(bad, "Dad")
    assert _valid_steps(["Dad's joined a clock club."], "Dad")
