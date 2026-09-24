"""Ordinary friction is rare, grounded in his situation, and can sometimes be repaired."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.selfhood import selfhood_context
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


def test_only_a_lighter_friendship_drifts_and_a_close_friend_never_does() -> None:
    def met(person: str, day: int) -> DomainEvent:
        return DomainEvent(
            "npc.encountered",
            "pathos",
            {
                "person_id": person,
                "simulated_at": (MONDAY + timedelta(days=day)).isoformat(),
                "text": "Hi.",
            },
        )

    def together(person: str, day: int, kind: str = "social.activity_completed") -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            {"person_id": person, "simulated_at": (MONDAY + timedelta(days=day)).isoformat()},
        )

    known = frozenset({"mara", "rowan", "ellis"})
    history = [identity_established_event(MONDAY.isoformat())]
    for day in range(0, 120, 2):
        history += [met("mara", day), together("mara", day)]  # a real friend, lightly kept
        history += [met("ellis", day), together("ellis", day)]  # and a deep one
    history += [together("ellis", day, "incident.shared_aftermath") for day in (10, 40, 90)]
    history.append(met("rowan", 5))  # someone he met once
    sunday = MONDAY + timedelta(days=118 + 7 * 3, hours=19)
    assert sunday.weekday() == 6
    assert run(history, sunday, known=known) == []  # a few weeks apart is nothing
    much_later = MONDAY + timedelta(days=118 + 7 * 8, hours=19)
    output = run(history, much_later, known=known)
    assert output[0].payload["kind"] == "friendship_drift"
    assert output[0].payload["person_id"] == "mara"
    assert value_evidence(output[0])[0][:2] == ("care", -1)
    history += output
    assert run(history, much_later + timedelta(days=7), known=known) == []


def unwell(at: datetime, severity: float) -> DomainEvent:
    return DomainEvent(
        "wellbeing.episode_started",
        "pathos",
        {
            "episode_id": f"wellbeing:{at.date()}",
            "condition_kind": "under_the_weather",
            "severity": severity,
            "expected_end_at": (at + timedelta(hours=48)).isoformat(),
            "reason": "An ordinary spell of physical discomfort surfaced.",
            "simulated_at": at.isoformat(),
            "clinical_diagnosis": False,
        },
    )


def test_on_a_bad_morning_he_rings_in_sick_but_works_through_a_mild_one() -> None:
    tuesday = MONDAY + timedelta(days=1, hours=8)
    base = [identity_established_event(MONDAY.isoformat())]
    base += work_rota_events(base, PlanningState(), MONDAY + timedelta(hours=6))
    shift = f"work-rota-{tuesday.date().isoformat()}"
    assert project_planning(base).calendar[shift].status == "scheduled"

    mild = [*base, unwell(tuesday, 0.35)]
    assert run(mild, tuesday) == []
    assert selfhood_context(mild, tuesday)["feeling_unwell"]

    bad = [*base, unwell(tuesday, 0.55)]
    output = run(bad, tuesday)
    assert [e.kind for e in output[:3]] == [
        "setback.occurred",
        "schedule.cancelled",
        "intention.abandoned",
    ]
    assert output[0].payload["kind"] == "sick_day"
    after = [*bad, *output]
    assert project_planning(after).calendar[shift].status == "cancelled"
    assert run(after, tuesday) == []
    assert selfhood_context(base, tuesday)["feeling_unwell"] is None


def test_he_turns_up_for_something_on_in_town_and_finds_it_called_off() -> None:
    from eidos.application.town_calendar import called_off

    outcomes = {}
    for week in range(40):
        tuesday = MONDAY + timedelta(weeks=week, days=1, hours=19)
        planned = event_at(
            "schedule.created",
            tuesday - timedelta(hours=6),
            schedule_id=f"quiz-{week}",
            title="Go along to the quiz",
            starts_at=tuesday.isoformat(),
            ends_at=(tuesday + timedelta(hours=3)).isoformat(),
            location_id="crown-anchor",
            actor_id="pathos",
            action="attend",
        )
        history = [identity_established_event(MONDAY.isoformat()), planned]
        output = run(history, tuesday, here="crown-anchor")
        off = called_off(f"quiz-{tuesday.date().isoformat()}")
        outcomes[off] = output
        if off:
            assert output[0].payload["kind"] == "called_off"
            assert output[1].kind == "schedule.cancelled"
            assert run([*history, *output], tuesday, here="crown-anchor") == []
            assert run(history, tuesday, here="home") == []
        else:
            assert output == []
        if len(outcomes) == 2:
            return
    raise AssertionError("never saw both an evening on and an evening off")


def event_at(kind: str, when: datetime, **payload: object) -> DomainEvent:
    return DomainEvent(kind, "pathos", {**payload, "simulated_at": when.isoformat()})
