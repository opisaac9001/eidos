"""Ordinary friction is rare, grounded in his situation, and can sometimes be repaired."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.setbacks import setback_events
from eidos.application.work_rota import work_rota_events
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances
from eidos.domain.identity import identity_established_event
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.relationships import project_relationships
from eidos.domain.selfhood import value_evidence

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def run(history, at, planning=None, *, care=0.8, known=frozenset(), here="home", ellis=None):
    return setback_events(
        history,
        at,
        planning if planning is not None else project_planning(history),
        values={"care": care},
        known_person_ids=known,
        pathos_location_id=here,
        ellis_location_id=ellis,
    )


def first_week_with(kind: str, hour: int, weekday: int, weeks: int = 80):
    base = [identity_established_event(MONDAY.isoformat())]
    for week in range(weeks):
        at = MONDAY + timedelta(weeks=week, days=weekday, hours=hour)
        output = run(base, at)
        if any(e.payload.get("kind") == kind for e in output):
            return base, at, output
    raise AssertionError(f"no {kind} in {weeks} weeks")


def test_something_breaks_now_and_then_and_the_ledger_feels_it() -> None:
    history, at, output = first_week_with("expense", 18, 2)
    occurred = output[0]
    assert occurred.kind == "setback.occurred"
    assert any(e.kind == "memory.recorded" for e in output)
    assert run([*history, *output], at) == []
    account = financial_foundation_events([], at - timedelta(days=1))
    rich = [*account, *output]
    charged = financial_consequence_events(rich, project_finances(rich), at)
    assert charged[0].payload["category"] == "unexpected_expense"
    assert charged[0].payload["amount_pence"] == -occurred.payload["cost_pence"]
    poor_account = DomainEvent(
        "finance.account_opened",
        "pathos",
        {"currency": "GBP", "opening_balance_pence": 100, "simulated_at": at.isoformat()},
    )
    poor = [poor_account, *output]
    missed = financial_consequence_events(poor, project_finances(poor), at)
    assert missed[0].kind == "finance.payment_missed"


def test_a_quiet_week_calls_off_tomorrows_shift_and_its_intention() -> None:
    base = [identity_established_event(MONDAY.isoformat())]
    base += work_rota_events(base, PlanningState(), MONDAY + timedelta(hours=6))
    for day in range(0, 200):
        at = MONDAY + timedelta(days=day, hours=18)
        tomorrow = (at + timedelta(days=1)).date().isoformat()
        planning = project_planning(base)
        if f"work-rota-{tomorrow}" not in planning.calendar:
            base += work_rota_events(base, planning, at - timedelta(hours=12))
            planning = project_planning(base)
        output = run(base, at, planning)
        if any(e.payload.get("kind") == "quiet_week" for e in output):
            kinds = [e.kind for e in output]
            assert kinds[:3] == ["setback.occurred", "schedule.cancelled", "intention.abandoned"]
            after = project_planning([*base, *output])
            assert after.calendar[f"work-rota-{tomorrow}"].status == "cancelled"
            return
    raise AssertionError("no quiet week found")


def shift_history(day: int, status: str):
    base = [identity_established_event(MONDAY.isoformat())]
    planning = project_planning(base)
    rota = work_rota_events(base, planning, MONDAY + timedelta(days=day, hours=6))
    base += rota
    planning = project_planning(base)
    schedule_id = f"work-rota-{(MONDAY + timedelta(days=day)).date().isoformat()}"
    entry = planning.calendar[schedule_id]
    planning = replace(
        planning, calendar={**planning.calendar, schedule_id: replace(entry, status=status)}
    )
    return base, planning


def test_a_shift_cut_short_can_leave_ellis_short_with_him_and_it_can_be_cleared() -> None:
    for week in range(60):
        day = week * 7
        base, planning = shift_history(day, "interrupted")
        at = MONDAY + timedelta(days=day, hours=17)
        output = run(base, at, planning)
        if not output:
            continue
        assert output[0].payload["kind"] == "work_friction"
        assert value_evidence(output[0])[0][:2] == ("craft", -1)
        history = [*base, *output]
        strained = project_relationships(history).relationships["ellis"]
        assert strained.tension > 0
        for later in range(1, 14):
            lunch = at.replace(hour=12) + timedelta(days=later)
            cleared = run(history, lunch, care=1.0, here="workshop", ellis="workshop")
            if cleared:
                assert cleared[0].payload["outcome"] == "cleared"
                assert value_evidence(cleared[0])[0][:2] == ("care", 1)
                eased = project_relationships([*history, *cleared]).relationships["ellis"]
                assert eased.tension < strained.tension
                return
        raise AssertionError("never cleared despite high care")
    raise AssertionError("no friction found")


def test_friction_left_alone_sets_in_after_two_weeks() -> None:
    for week in range(60):
        day = week * 7
        base, planning = shift_history(day, "interrupted")
        at = MONDAY + timedelta(days=day, hours=17)
        output = run(base, at, planning)
        if output:
            later = run([*base, *output], at + timedelta(days=15), care=0.0)
            assert later[0].payload["outcome"] == "left_unspoken"
            return
    raise AssertionError("no friction found")


def test_he_notices_a_friend_he_has_not_seen_in_weeks() -> None:
    met = DomainEvent(
        "npc.encountered",
        "pathos",
        {"person_id": "mara", "simulated_at": MONDAY.isoformat(), "text": "Hi."},
    )
    history = [identity_established_event(MONDAY.isoformat()), met]
    sunday = MONDAY + timedelta(days=13, hours=19)
    assert run(history, sunday, known=frozenset({"mara"})) == []
    later = MONDAY + timedelta(days=27, hours=19)
    output = run(history, later, known=frozenset({"mara"}))
    assert output[0].payload["kind"] == "friendship_drift"
    assert value_evidence(output[0])[0][:2] == ("care", -1)
    assert run([*history, *output], later + timedelta(days=7), known=frozenset({"mara"})) == []


def test_he_sometimes_wakes_up_ill_rings_in_sick_and_gets_better() -> None:
    base = [identity_established_event(MONDAY.isoformat())]
    for day in range(400):
        at = MONDAY + timedelta(days=day, hours=7)
        planning = project_planning(base)
        if f"work-rota-{at.date().isoformat()}" not in planning.calendar:
            base += work_rota_events(base, planning, at - timedelta(hours=1))
            planning = project_planning(base)
        output = run(base, at, planning)
        if not output:
            continue
        occurred = output[0]
        assert occurred.payload["kind"] == "illness"
        history = [*base, *output]
        cancelled = [e for e in history if e.kind == "schedule.cancelled"]
        today = f"work-rota-{at.date().isoformat()}"
        assert (today in {e.payload["schedule_id"] for e in cancelled}) == (
            today in planning.calendar
        )
        recovered = None
        for later in range(1, 10):
            morning = at + timedelta(days=later)
            planning = project_planning(history)
            if f"work-rota-{morning.date().isoformat()}" not in planning.calendar:
                history += work_rota_events(history, planning, morning - timedelta(hours=1))
                planning = project_planning(history)
            step = run(history, morning, planning)
            history += step
            if any(e.kind == "setback.resolved" for e in step):
                recovered = later
                break
        assert recovered == occurred.payload["days"]
        after = project_planning(history)
        for gap_day in range(1, recovered):
            sick_day = (at + timedelta(days=gap_day)).date().isoformat()
            entry = after.calendar.get(f"work-rota-{sick_day}")
            assert entry is None or entry.status == "cancelled"
        soon = at + timedelta(days=recovered + 1)
        assert all(
            e.payload.get("kind") != "illness"
            for day in range(20)
            for e in run(history, soon + timedelta(days=day))
        )
        return
    raise AssertionError("never ill in 400 days")
