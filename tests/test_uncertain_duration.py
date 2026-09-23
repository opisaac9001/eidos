from dataclasses import replace
from datetime import timedelta

from test_activity_execution import NOW, event, plan

from eidos.application.activity_execution import (
    duration_requirement,
    execution_context,
    execution_events,
)
from eidos.application.lived_activity_window import lived_activity_window
from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import project_world_catalog


def uncertain_plan(schedule_id, confidence):
    planning, old = plan(30)
    entry = replace(old, schedule_id=schedule_id, source_proposal_id="choice")
    planning = replace(planning, calendar={schedule_id: entry})
    created = DomainEvent(
        "schedule.created",
        "pathos",
        {
            "schedule_id": schedule_id,
            "title": entry.title,
            "starts_at": entry.starts_at,
            "ends_at": entry.ends_at,
            "location_id": entry.location_id,
            "actor_id": "pathos",
            "action": entry.action,
            "target_id": entry.target_id,
            "activity_type": entry.activity_type,
            "source_proposal_id": "choice",
            "estimated_duration_seconds": 1800,
            "estimate_confidence": confidence,
            "simulated_at": NOW.isoformat(),
        },
    )
    intention = DomainEvent(
        "intention.adopted",
        "pathos",
        {
            "intention_id": entry.intention_id,
            "actor_id": "pathos",
            "action": entry.action,
            "motivation": "Spend the estimated time on it.",
            "priority": 0.6,
            "target_id": entry.target_id,
            "simulated_at": NOW.isoformat(),
        },
    )
    return planning, entry, created, intention


def ids_for(direction):
    for index in range(100):
        planning, entry, created, intention = uncertain_plan(f"estimate-{index}", 0.0)
        _, actual, _ = duration_requirement([created], entry)
        if (actual < 1800) == (direction == "shorter"):
            return planning, entry, created, intention, actual
    raise AssertionError("No stable duration sample in expected direction")


def test_confidence_does_not_control_reality_but_historical_duration_remains_exact():
    planning, entry, created, _ = uncertain_plan("exact", 1.0)
    estimated, actual, confidence = duration_requirement([created], entry)
    assert (estimated, confidence) == (1800, 1.0)
    assert 1800 * 0.92 <= actual <= 1800 * 1.08
    assert actual != 1800
    assert duration_requirement([], entry) == (1800, 1800, 1.0)
    started = execution_events([event("sleep.ended"), created], planning, NOW)[-1]
    assert started.payload["required_seconds"] == actual
    assert started.payload["duration_outcome_hidden_from_pathos"] is True


def test_uncertain_requirement_is_replay_stable_and_bounded():
    _, entry, created, _, actual = ids_for("longer")
    assert duration_requirement([created], entry)[1] == actual
    assert 1080 <= actual <= 2520
    assert actual != 1800


def test_personal_context_knows_uncertainty_but_not_hidden_actual_seconds():
    planning, entry, created, intention, actual = ids_for("longer")
    history = [event("sleep.ended"), created, intention]
    history += execution_events(history, planning, NOW)
    observer = execution_context(history, planning, NOW, observer=True)[0]
    personal = execution_context(history, planning, NOW)[0]
    assert observer["required_seconds"] == actual
    assert observer["estimated_seconds"] == 1800
    assert personal["duration_expectation"] == "I am not very sure how long this will take."
    assert "required_seconds" not in personal


def test_shorter_task_can_finish_before_the_reserved_window_ends():
    planning, entry, created, intention, actual = ids_for("shorter")
    history = [event("sleep.ended"), created, intention]
    output = lived_activity_window(
        history,
        planning,
        project_world_catalog([]),
        NOW,
        NOW + timedelta(minutes=30),
        repair_mastery=1,
    )
    completed = next(e for e in output if e.kind == "schedule.completed")
    assert datetime_from(completed) == NOW + timedelta(seconds=actual)
    assert datetime_from(completed) < datetime_from(entry.ends_at)


def test_longer_task_reaches_the_window_unfinished_without_inventing_work():
    planning, _, created, intention, actual = ids_for("longer")
    history = [event("sleep.ended"), created, intention]
    output = lived_activity_window(
        history,
        planning,
        project_world_catalog([]),
        NOW,
        NOW + timedelta(minutes=30),
        repair_mastery=1,
    )
    unfinished = next(e for e in output if e.kind == "activity.execution_unfinished")
    assert unfinished.payload["worked_seconds"] == 1800
    assert unfinished.payload["remaining_seconds"] == actual - 1800
    assert any(e.kind == "schedule.interrupted" for e in output)
    assert not any(e.kind == "schedule.completed" for e in output)


def datetime_from(value):
    from datetime import datetime

    raw = value.payload["simulated_at"] if isinstance(value, DomainEvent) else value
    return datetime.fromisoformat(str(raw))
