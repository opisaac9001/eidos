"""The job goes somewhere: a raise, a fifth day or not, and a question about the future."""

from datetime import datetime, timedelta, timezone

from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.work_arc import work_arc_events
from eidos.application.work_rota import current_terms, work_rota_events
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances
from eidos.domain.identity import identity_established_event
from eidos.domain.planning import project_planning
from eidos.domain.selfhood import value_evidence

START = datetime(2026, 1, 5, 6, tzinfo=timezone.utc)
VALUES = {"craft": 0.72, "autonomy": 0.68, "care": 0.78, "reliability": 0.74, "curiosity": 0.84}


def worked(days: int) -> list[DomainEvent]:
    history = [identity_established_event(START.isoformat())]
    for day in range(days):
        at = START + timedelta(days=day)
        if day % 7 == 0:
            history += work_rota_events(history, project_planning(history), at)
        schedule_id = f"work-rota-{at.date().isoformat()}"
        if schedule_id in project_planning(history).calendar:
            history.append(
                DomainEvent(
                    "schedule.completed",
                    "pathos",
                    {"schedule_id": schedule_id, "simulated_at": at.replace(hour=16).isoformat()},
                )
            )
    return history


def end_of_shift(day: int) -> datetime:
    return (START + timedelta(days=day)).replace(hour=16)


def run(history, day, **kwargs):
    options = {"values": VALUES, "balance_pence": 100_000, "ellis_bond": "friend", **kwargs}
    return work_arc_events(history, end_of_shift(day), **options)


def next_shift_day(after: int) -> int:
    day = after
    while (START + timedelta(days=day)).weekday() not in (0, 1, 3, 4):
        day += 1
    return day


def test_months_of_good_work_earn_a_raise_that_shows_up_in_his_pay() -> None:
    day = next_shift_day(95)
    history = worked(day + 1)
    assert run(worked(40), next_shift_day(30)) == []  # too soon
    raised = run(history, day)
    assert raised[0].payload["step"] == "raise"
    assert value_evidence(raised[0])[0][:2] == ("craft", 1)
    history += raised
    assert current_terms(history)[1] == 1_200
    at = end_of_shift(day) + timedelta(hours=14)
    history += work_rota_events(history, project_planning(history), at)
    booked = [
        e
        for e in history
        if e.kind == "schedule.created" and e.payload.get("hourly_wage_pence") == 1_200
    ]
    assert booked
    completed = DomainEvent(
        "activity.completed",
        "pathos",
        {
            "activity": "work",
            "schedule_id": booked[0].payload["schedule_id"],
            "simulated_at": booked[0].payload["ends_at"],
        },
    )
    rich = [*financial_foundation_events([], START), *history, completed]
    pay = financial_consequence_events(rich, project_finances(rich), at)
    assert any(e.payload.get("amount_pence") == 1_200 * 6 for e in pay)


def test_whether_he_takes_a_fifth_day_depends_on_who_he_has_become() -> None:
    day = next_shift_day(160)
    history = worked(day + 1)
    history += run(history, next_shift_day(95))
    maker = run(history, day, values={**VALUES, "craft": 0.95, "autonomy": 0.5})
    free_spirit = run(history, day, values={**VALUES, "craft": 0.6, "autonomy": 0.92})
    assert maker[0].payload["accepted"] is True
    assert 2 in current_terms([*history, *maker])[0]
    assert free_spirit[0].payload["accepted"] is False
    assert value_evidence(free_spirit[0])[0][:2] == ("autonomy", 1)


def test_after_a_year_and_a_real_friendship_ellis_asks_about_the_future() -> None:
    day = next_shift_day(370)
    history = worked(day + 1)
    history += run(history, next_shift_day(95))
    history += run(history, next_shift_day(160))
    assert run(history, day, ellis_bond="friend") == []
    future = run(history, day, ellis_bond="close")
    assert future[0].payload["step"] == "future"
    assert "taking the workshop on" in future[0].payload["text"]


def career(values, balance=100_000, days=1000) -> list[DomainEvent]:
    history = worked(days)
    for day in range(90, days):
        if (START + timedelta(days=day)).weekday() in (0, 1, 3, 4):
            history += run(
                history, day, values=values, balance_pence=balance, ellis_bond="closest"
            )
    return history


def steps(history) -> list[str]:
    return [e.payload["step"] for e in history if e.kind == "work.arc_step"]


def test_saying_yes_means_ellis_hands_the_workshop_over() -> None:
    history = career({**VALUES, "craft": 0.9, "autonomy": 0.8})
    assert steps(history)[:4] == ["raise", "extra_day", "future", "answer"]
    assert steps(history)[4:] == ["handover_plan", "running", "keys"]
    weekdays, wage = current_terms(history)
    assert weekdays == frozenset({0, 1, 2, 3, 4}) and wage == 1_500
    keys = next(e for e in history if e.payload.get("step") == "keys")
    answer = next(e for e in history if e.payload.get("step") == "answer")
    gap = datetime.fromisoformat(keys.payload["simulated_at"]) - datetime.fromisoformat(
        answer.payload["simulated_at"]
    )
    assert timedelta(days=400) <= gap <= timedelta(days=500)


def test_saying_no_means_someone_else_learns_from_him() -> None:
    history = career({**VALUES, "craft": 0.5, "autonomy": 0.4}, balance=20_000)
    assert "answer" in steps(history)
    assert steps(history)[-1] == "apprentice"
    assert "keys" not in steps(history)
