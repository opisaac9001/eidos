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
