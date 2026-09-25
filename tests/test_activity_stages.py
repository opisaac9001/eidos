from dataclasses import replace
from datetime import timedelta

import pytest
from test_activity_execution import NOW, event, plan

from eidos.application.activity_execution import (
    activity_effort,
    execution_context,
    execution_events,
)
from eidos.application.household import household_foundation_events
from eidos.domain.household import project_household


def test_short_batch_cleaning_is_tick_invariant_and_never_applied_twice():
    planning, entry = plan(5)
    entry = replace(entry, activity_type="household_dishes")
    planning = replace(planning, calendar={entry.schedule_id: entry})
    seed = [
        event("sleep.ended"),
        event("household.established", dishes=0.8, laundry=0, tidying=0, paperwork=0),
    ]
    for points in ([0, 5], range(6)):
        history = list(seed)
        for minute in points:
            history += execution_events(history, planning, NOW + timedelta(minutes=minute))
        assert project_household(history).loads["dishes"] == pytest.approx(0.8 - 0.55 / 6)
        assert execution_events(history, planning, NOW + timedelta(minutes=5)) == []
        assert len([e for e in history if e.kind == "household.task_completed"]) == 1


def test_dishes_washed_survive_interruption_before_putting_away():
    planning, entry = plan(20)
    entry = replace(entry, activity_type="household_dishes")
    planning = replace(planning, calendar={entry.schedule_id: entry})
    history = [event("sleep.ended"), *household_foundation_events([], NOW)]
    history += execution_events(history, planning, NOW)
    at = NOW + timedelta(minutes=17)
    history += execution_events(history, planning, at)
    assert project_household(history).loads["dishes"] == 0
    history.append(
        event("scene.started", 17, scene_id="chat", initiator_id="pathos", partner_id="user")
    )
    history += execution_events(history, planning, at)
    end = NOW + timedelta(minutes=20)
    history += execution_events(history, planning, end)
    assert not activity_effort(history, entry, end)["ready"]
    stages = execution_context(history, planning, end, observer=True)[0]["stages"]
    assert [s["status"] for s in stages] == ["completed", "completed", "pending"]
    assert execution_events(history, planning, end) == []
    assert len([e for e in history if e.kind == "household.task_completed"]) == 1


def test_title_alone_does_not_authorize_household_effect():
    planning, entry = plan(20)
    entry = replace(entry, title="Wash the dishes")
    planning = replace(planning, calendar={entry.schedule_id: entry})
    history = [event("sleep.ended"), *household_foundation_events([], NOW)]
    history += execution_events(history, planning, NOW)
    history += execution_events(history, planning, NOW + timedelta(minutes=20))
    assert project_household(history).loads["dishes"] == 0.12


def test_retimed_work_keeps_effort_without_counting_time_between_sessions():
    planning, entry = plan(30)
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history.append(
        event("schedule.interrupted", 10, schedule_id=entry.schedule_id, reason="A visitor")
    )
    history += execution_events(
        history,
        replace(planning, calendar={entry.schedule_id: replace(entry, status="interrupted")}),
        NOW + timedelta(minutes=10),
    )
    history.append(
        event(
            "schedule.rescheduled",
            15,
            schedule_id=entry.schedule_id,
            starts_at=(NOW + timedelta(hours=2)).isoformat(),
            ends_at=(NOW + timedelta(hours=2, minutes=30)).isoformat(),
        )
    )
    later = replace(
        entry,
        starts_at=(NOW + timedelta(hours=2)).isoformat(),
        ends_at=(NOW + timedelta(hours=2, minutes=30)).isoformat(),
    )
    planning = replace(planning, calendar={later.schedule_id: later})
    history += execution_events(history, planning, NOW + timedelta(hours=2))
    at = NOW + timedelta(hours=2, minutes=20)
    history += execution_events(history, planning, at)
    effort = activity_effort(history, later, at)
    assert effort["worked_seconds"] == 1800
    assert effort["ready"]
    assert len([e for e in history if e.kind == "activity.stage_completed"]) == 3


def test_depleted_attention_can_defer_resumption_without_polling_rerolls():
    planning, entry = plan()
    intention = planning.intentions[entry.intention_id]
    planning = replace(
        planning, intentions={intention.intention_id: replace(intention, priority=0.4)}
    )
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history.append(
        event("scene.started", 5, scene_id="chat", initiator_id="pathos", partner_id="user")
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=5))
    history.extend(
        [event("scene.ended", 10, scene_id="chat"), event("affect.changed", 10, energy=0.1)]
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=10))
    assert history[-1].payload["decision"] == "defer"
    assert execution_events(history, planning, NOW + timedelta(minutes=11)) == []
    assert activity_effort(history, entry, NOW + timedelta(minutes=11))["worked_seconds"] == 300
    history.append(event("affect.changed", 12, energy=0.7))
    history += execution_events(history, planning, NOW + timedelta(minutes=12))
    assert history[-1].kind == "activity.execution_resumed"


def test_missing_or_borrowed_resource_cannot_count_as_work():
    planning, entry = plan()
    entry = replace(entry, resource_id="book")
    planning = replace(planning, calendar={entry.schedule_id: entry})
    history = [event("sleep.ended")]
    assert execution_events(history, planning, NOW) == []
    history.append(
        event(
            "object.registered",
            object_id="book",
            location_id="home",
            custodian_id="pathos",
            condition="good",
        )
    )
    history += execution_events(history, planning, NOW)
    history.append(
        event(
            "object.custody_changed", 5, object_id="book", custodian_id="mara", location_id="home"
        )
    )
    assert activity_effort(history, entry, NOW + timedelta(minutes=30))["worked_seconds"] == 300


def test_a_chat_in_the_last_hour_of_a_long_shift_does_not_leave_it_unfinished():
    planning, entry = plan(360)
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history.append(
        event("scene.started", 300, scene_id="chat", initiator_id="ellis", partner_id="pathos")
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=300))
    end = NOW + timedelta(minutes=360)
    assert activity_effort(history, entry, end)["ready"]
    short_planning, short = plan(60)
    brief = [event("sleep.ended")]
    brief += execution_events(brief, short_planning, NOW)
    brief.append(
        event("scene.started", 50, scene_id="chat", initiator_id="ellis", partner_id="pathos")
    )
    assert not activity_effort(brief, short, NOW + timedelta(minutes=60))["ready"]


def test_talking_with_ellis_on_a_shift_is_part_of_the_work():
    planning, entry = plan(360)
    entry = replace(entry, schedule_id="work-rota-2026-01-02")
    history = [event("sleep.ended")]
    started = replace(planning, calendar={entry.schedule_id: entry})
    history += execution_events(history, started, NOW)
    chat = [event("scene.started", 60, scene_id="bench", initiator_id="pathos", partner_id="ellis")]
    assert activity_effort([*history, *chat], entry, NOW + timedelta(minutes=180))[
        "worked_seconds"
    ] == pytest.approx(180 * 60)
    visitor = [
        event("scene.started", 60, scene_id="visit", initiator_id="nina", partner_id="pathos")
    ]
    assert (
        activity_effort([*history, *visitor], entry, NOW + timedelta(minutes=180))["blocked_by"]
        == "conversation"
    )


def test_someone_dropping_into_the_workshop_is_talked_to_over_the_bench():
    planning, entry = plan(360)
    entry = replace(entry, schedule_id="work-rota-2026-01-02")
    history = [event("sleep.ended")]
    history += execution_events(
        history, replace(planning, calendar={entry.schedule_id: entry}), NOW
    )
    drop_in = [
        event(
            "scene.started",
            60,
            scene_id="customer",
            initiator_id="townsfolk-8103",
            partner_id="pathos",
            location_id=entry.location_id,
        )
    ]
    effort = activity_effort([*history, *drop_in], entry, NOW + timedelta(minutes=180))
    assert effort["blocked_by"] is None
    assert effort["worked_seconds"] == pytest.approx(180 * 60)


def test_on_an_evening_out_whoever_is_there_is_part_of_the_evening():
    planning, entry = plan(150)
    entry = replace(entry, schedule_id="romance-date-x", activity_type="an_evening_out")
    history = [event("sleep.ended")]
    history += execution_events(
        history, replace(planning, calendar={entry.schedule_id: entry}), NOW
    )
    mara = [
        event(
            "scene.started",
            0,
            scene_id="hello",
            initiator_id="pathos",
            partner_id="mara",
            location_id=entry.location_id,
        )
    ]
    effort = activity_effort([*history, *mara], entry, NOW + timedelta(minutes=120))
    assert effort["blocked_by"] is None
