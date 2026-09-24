"""Tastes are earned from how things actually felt, and he can change his mind."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.adapters.standin_gateway import _standin_tastes_reply
from eidos.application.experience import _gerund, experience_events, place_category
from eidos.application.selfhood import selfhood_context
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import value_evidence
from eidos.domain.state import PathosState
from eidos.domain.tastes import project_tastes
from eidos.domain.world_catalog import seed_world_catalog

START = datetime(2026, 3, 2, 15, tzinfo=timezone.utc)
CATALOG = seed_world_catalog()
VALUES = {"care": 0.78, "curiosity": 0.84, "reliability": 0.74, "autonomy": 0.68, "craft": 0.72}
TRAITS = {"openness": 0.68, "sociability": 0.52, "follow_through": 0.64}


def realized(n: int, *, place: str = "cafe", kind: str = "window_notes") -> DomainEvent:
    return DomainEvent(
        "agency.activity_realized",
        "pathos",
        {
            "schedule_id": f"plan-{n}",
            "activity_type": kind,
            "action": "attend",
            "title": "Sit in the window and watch the street",
            "companion_id": None,
            "location_id": place,
            "simulated_at": (START + timedelta(days=n)).isoformat(),
        },
        event_id=UUID(int=n + 1),
    )


def feel(history, source, state=None, weather="Clear"):
    return experience_events(
        history,
        source,
        state or PathosState(),
        values=VALUES,
        traits=TRAITS,
        weather=weather,
        catalog=CATALOG,
    )


def live(count: int, state=None, **kwargs):
    history: list[DomainEvent] = []
    for n in range(count):
        source = realized(n, **kwargs)
        history += [source, *feel([*history, source], source, state)]
    return history


def test_each_chosen_activity_is_felt_once_with_reasons() -> None:
    source = realized(0)
    output = feel([source], source)
    felt = output[0]
    assert felt.kind == "experience.felt"
    assert -1 <= felt.payload["enjoyment"] <= 1
    assert feel([source, *output], source) == []
    assert place_category("cafe") == "social" and place_category("hardware") == "making"
    assert _gerund("Go along to the quiz") == "Going along to the quiz"
    assert _gerund("Sit by the river") == "Sitting by the river"


def test_a_tired_lonely_evening_and_a_rested_one_feel_different() -> None:
    source = realized(0)
    rested = PathosState(energy=0.9, connection=0.2, valence=0.3)
    drained = PathosState(energy=0.2, connection=0.9, valence=-0.4)
    good = feel([source], source, rested)[0].payload["enjoyment"]
    bad = feel([source], source, drained)[0].payload["enjoyment"]
    assert good - bad >= 0.5
    assert "among people" not in feel([source], source, drained)[0].payload["reasons"]


def test_repeated_good_experiences_become_a_taste_that_counts_as_lived_evidence() -> None:
    rested = PathosState(energy=0.9, connection=0.2, valence=0.4)
    history = live(8, state=rested)
    tastes = project_tastes(history)
    cafe = tastes.tastes.get("place:cafe")
    assert cafe is not None and cafe.stance == "likes"
    formed = next(
        e for e in history if e.kind == "taste.formed" and e.payload["subject"] == "place:cafe"
    )
    assert value_evidence(formed)[0][:2] == ("care", 1)
    context = selfhood_context(history, START + timedelta(days=9))
    assert CATALOG.places["cafe"].name in context["has_found_he_loves"]
    reply = _standin_tastes_reply(
        "what's your favourite place?", {"identity": {"selfhood": context}}
    )
    assert reply is not None and CATALOG.places["cafe"].name in reply


def test_a_run_of_bad_experiences_changes_his_mind() -> None:
    rested = PathosState(energy=0.9, connection=0.2, valence=0.4)
    history = live(8, state=rested)
    assert project_tastes(history).tastes["place:cafe"].stance == "likes"
    drained = replace(PathosState(), energy=0.15, connection=1.0, valence=-0.8)
    for n in range(8, 14):
        source = realized(n)
        history += [source, *feel([*history, source], source, drained)]
    cafe = project_tastes(history).tastes["place:cafe"]
    assert cafe.stance == "dislikes" and cafe.changed_mind
    assert any("Changed my mind" in str(e.payload.get("text")) for e in history)
    assert (
        CATALOG.places["cafe"].name
        in selfhood_context(history, START + timedelta(days=15))["changed_his_mind_about"]
    )
