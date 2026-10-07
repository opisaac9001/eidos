"""Meals fit the day: later and slower on a day off, sometimes skipped on a rushed work
morning, cooked properly when there's time, a takeaway when he's shattered or it's Friday."""

from datetime import datetime, timedelta, timezone

import eidos.application.nourishment as nourishment
from eidos.application import economy
from eidos.application.nourishment import nourishment_events, provision_foundation_events
from eidos.domain.planning import project_planning
from eidos.domain.state import PathosState

MONDAY = datetime(2026, 8, 3, tzinfo=timezone.utc)
SHIFTS = {0, 1, 3, 4}


def _day(monkeypatch, date, energy=0.6, balance=20_000):
    monkeypatch.setattr(nourishment, "working_day", lambda planning, at: at.weekday() in SHIFTS)
    seed = provision_foundation_events([], date)
    history = list(seed)
    planning = project_planning(history)
    eaten = []
    for hour in range(6, 23):
        at = date.replace(hour=hour)
        state = PathosState(simulated_at=at, awake=True, hunger=0.6, energy=energy)
        out = nourishment_events(history, state, at, planning, balance, pathos_busy=False)
        history += out
        eaten += [e for e in out if e.kind in {"meal.eaten", "meal.skipped"}]
    return eaten


def test_breakfast_is_later_on_a_day_off_and_drifts(monkeypatch) -> None:
    work, off = set(), set()
    for day in range(28):
        date = MONDAY + timedelta(days=day)
        for meal in _day(monkeypatch, date):
            if meal.payload["meal_kind"] == "breakfast":
                hour = datetime.fromisoformat(meal.payload["simulated_at"]).hour
                (work if date.weekday() in SHIFTS else off).add(hour)
    assert work <= {7, 8} and off <= {8, 9, 10}
    assert len(off) >= 2 and max(off) > max(work)


def test_some_rushed_work_mornings_have_no_breakfast(monkeypatch) -> None:
    skipped = []
    for day in range(56):
        date = MONDAY + timedelta(days=day)
        meals = _day(monkeypatch, date)
        kinds = [m.kind for m in meals if m.payload["meal_kind"] == "breakfast"]
        assert len(kinds) == 1  # skipped or eaten, once
        if kinds == ["meal.skipped"]:
            skipped.append(date)
    assert skipped and all(d.weekday() in SHIFTS for d in skipped)
    assert len(skipped) < 0.35 * 32


def test_what_tea_comes_to(monkeypatch) -> None:
    saturday = MONDAY + timedelta(days=5)
    meals = _day(monkeypatch, saturday)
    tea = next(m for m in meals if m.payload["meal_kind"] == "evening_meal")
    assert tea.payload["text"] in nourishment._COOKED + nourishment._TAKEAWAY
    tired = [
        next(m for m in _day(monkeypatch, MONDAY + timedelta(days=d), energy=0.4)
             if m.payload["meal_kind"] == "evening_meal").payload
        for d in range(0, 28) if d % 7 in {0, 1, 3}
    ]  # fmt: skip
    texts = {p["text"] for p in tired}
    assert texts & set(nourishment._TIRED)
    assert not texts & set(nourishment._COOKED)


def test_a_takeaway_now_and_then_and_it_costs(monkeypatch) -> None:
    sources = []
    for day in range(56):
        date = MONDAY + timedelta(days=day)
        for meal in _day(monkeypatch, date, energy=0.3):
            if meal.kind == "meal.eaten" and meal.payload["meal_kind"] == "evening_meal":
                sources.append(meal)
    takeaways = [m for m in sources if m.payload["provision_source"] == "takeaway"]
    assert 0 < len(takeaways) < len(sources)
    assert all(m.payload["provision_object_id"] is None for m in takeaways)
    assert economy._source_consequence(takeaways[0])[0] == -economy.TAKEAWAY_PENCE
    # Not when there's no money for it.
    broke = [
        m for d in range(56) for m in _day(monkeypatch, MONDAY + timedelta(days=d), 0.3, 1_000)
        if m.kind == "meal.eaten"
    ]  # fmt: skip
    assert not any(m.payload["provision_source"] == "takeaway" for m in broke)
