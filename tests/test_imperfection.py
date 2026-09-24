"""He falls short in ordinary ways, from how he is, and notices the patterns."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.friendship import friendships
from eidos.application.imperfection import imperfection_context, imperfection_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.relationships import project_relationships
from eidos.domain.selfhood import value_evidence
from eidos.domain.state import PathosState

EVENING = datetime(2026, 2, 3, 18, tzinfo=timezone.utc)
TRAITS = {"follow_through": 0.64}
VALUES = {"care": 0.78}


def plan(n: int, starts: datetime) -> CalendarEntry:
    return CalendarEntry(
        f"pathos-agency-cause-{n}-schedule",
        "Sketch the joints on repaired furniture",
        starts.isoformat(),
        "home",
        ends_at=(starts + timedelta(hours=1)).isoformat(),
        actor_id="pathos",
        action="learn",
    )


def run(history, at, state, planning=PlanningState(), talking_with=None):
    return imperfection_events(
        history,
        at,
        state,
        planning,
        traits=TRAITS,
        values=VALUES,
        talking_with=talking_with,
        names={"ellis": "Ellis"},
    )


def put_offs(state: PathosState) -> int:
    count = 0
    for n in range(300):
        at = EVENING + timedelta(days=n)
        entry = plan(n, at + timedelta(minutes=30))
        output = run([], at, state, PlanningState(calendar={entry.schedule_id: entry}))
        count += any(e.payload.get("pattern") == "put_off" for e in output)
    return count


def test_he_puts_things_off_more_on_flat_days() -> None:
    bright = replace(PathosState(), awake=True, energy=0.9, valence=0.4)
    flat = replace(PathosState(), awake=True, energy=0.2, valence=-0.5)
    assert put_offs(flat) > 2 * max(1, put_offs(bright))


def test_a_put_off_plan_is_cancelled_and_felt_as_a_lapse() -> None:
    flat = replace(PathosState(), awake=True, energy=0.1, valence=-0.8)
    for n in range(200):
        at = EVENING + timedelta(days=n)
        entry = plan(n, at + timedelta(minutes=30))
        output = run([], at, flat, PlanningState(calendar={entry.schedule_id: entry}))
        if output:
            assert [e.kind for e in output[:2]] == ["imperfection.noticed", "schedule.cancelled"]
            assert value_evidence(output[0])[0][:2] == ("reliability", -1)
            return
    raise AssertionError("never put anything off, even on the flattest days")


def test_late_nights_cost_sleep_and_are_capped() -> None:
    restless = replace(
        PathosState(), awake=True, arousal=0.9, connection=0.1, valence=-0.4, rest=0.6
    )
    history: list[DomainEvent] = []
    for n in range(28):
        output = run(history, EVENING.replace(hour=23) + timedelta(days=n), restless)
        history += output
    nights = [e for e in history if e.payload.get("pattern") == "late_night"]
    assert 1 <= len(nights) <= 8
    tired = next(e for e in history if e.kind == "needs.changed")
    assert tired.payload["rest"] < 0.6


def test_snapping_when_exhausted_then_saying_sorry() -> None:
    wrecked = replace(PathosState(), awake=True, energy=0.1, rest=0.2)
    history: list[DomainEvent] = []
    for hour in range(200):
        at = EVENING + timedelta(hours=hour)
        history += run(history, at, wrecked, talking_with="ellis")
        if any(e.kind == "imperfection.apologised" for e in history):
            break
    snap = next(e for e in history if e.payload.get("pattern") == "snapped")
    assert value_evidence(snap)[0][:2] == ("care", -1)
    apology = next(e for e in history if e.kind == "imperfection.apologised")
    assert apology.payload["person_id"] == "ellis"
    assert value_evidence(apology)[0][:2] == ("care", 1)
    ellis = project_relationships(history).relationships["ellis"]
    assert ellis.tension < 0.08 * len([e for e in history if e.payload.get("pattern") == "snapped"])
    assert friendships(history, EVENING + timedelta(days=10))["ellis"].deepening_moments >= 1


def test_he_knows_the_patterns_he_would_like_to_change() -> None:
    noticed = [
        DomainEvent(
            "imperfection.noticed",
            "pathos",
            {"pattern": "put_off", "simulated_at": (EVENING - timedelta(days=d)).isoformat()},
        )
        for d in (2, 9)
    ]
    assert imperfection_context(noticed, EVENING) == ["putting things off"]
    assert imperfection_context(noticed[:1], EVENING) == []
