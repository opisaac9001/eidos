import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.activity_execution import (
    activity_effort,
    execution_context,
    execution_events,
    execution_window_events,
)
from eidos.application.life import Life
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.application.time_budget import personal_time_budget
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, parse_agency_candidate, resolve_agency_candidate
from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, Intention, PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import project_world_catalog

NOW = datetime(2026, 1, 2, 10, 10, tzinfo=timezone.utc)


def event(kind, minutes=0, **payload):
    return DomainEvent(
        kind, "pathos", {"simulated_at": (NOW + timedelta(minutes=minutes)).isoformat(), **payload}
    )


def plan(minutes=30):
    entry = CalendarEntry(
        "write",
        "Write a letter",
        NOW.isoformat(),
        "home",
        ends_at=(NOW + timedelta(minutes=minutes)).isoformat(),
        actor_id="pathos",
        action="work",
        intention_id="write-intention",
    )
    return PlanningState(
        calendar={entry.schedule_id: entry},
        intentions={
            "write-intention": Intention(
                "write-intention", "pathos", "work", "Reply to a friend", 0.8
            )
        },
    ), entry


def test_no_reservation_only_completion_or_backdated_work():
    planning, entry = plan()
    end = NOW + timedelta(minutes=30)
    history = [event("sleep.ended")]
    assert not activity_effort(history, entry, end)["ready"]
    result = scheduled_activity_events(
        planning,
        actor_location_id="home",
        simulated_at=end,
        actual_revision=0,
        cognitive_history=history,
        require_execution_evidence=True,
    )
    assert "activity.completed" not in [e.kind for e in result]
    assert "schedule.interrupted" in [e.kind for e in result]
    assert not any(
        e.kind in {"intention.abandoned", "goal.abandoned", "commitment.fulfilled"} for e in result
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=20))
    assert activity_effort(history, entry, end)["worked_seconds"] == 600


def test_conversation_pauses_effort_and_leaves_unfinished_work():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history.append(
        event("scene.started", 5, scene_id="chat", initiator_id="pathos", partner_id="user")
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=5))
    assert history[-1].kind == "activity.execution_paused"
    history.append(event("scene.ended", 15, scene_id="chat"))
    history += execution_events(history, planning, NOW + timedelta(minutes=15))
    assert history[-1].kind == "activity.execution_resumed"
    end = NOW + timedelta(minutes=30)
    history += execution_events(history, planning, end)
    assert activity_effort(history, entry, end)["worked_seconds"] == 1140
    assert history[-1].kind == "activity.execution_unfinished"
    assert execution_events(history, planning, end) == []


def test_low_priority_return_can_shorten_the_session_without_claiming_completion():
    planning, entry = plan()
    intention = planning.intentions[entry.intention_id]
    planning = replace(
        planning, intentions={intention.intention_id: replace(intention, priority=0.5)}
    )
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history.append(
        event("scene.started", 5, scene_id="chat", initiator_id="pathos", partner_id="user")
    )
    history += execution_events(history, planning, NOW + timedelta(minutes=5))
    history.append(event("scene.ended", 25, scene_id="chat"))
    resumed = execution_events(history, planning, NOW + timedelta(minutes=25))
    decision = next(e for e in resumed if e.kind == "activity.resumption_decided")
    assert decision.payload["decision"] == "shorten"
    assert any(e.kind == "activity.scope_shortened" for e in resumed)
    assert any(e.kind == "activity.execution_resumed" for e in resumed)
    history += resumed
    end = NOW + timedelta(minutes=30)
    history += execution_events(history, planning, end)
    assert history[-1].kind == "activity.execution_unfinished"
    assert not any(e.kind == "activity.completed" for e in history)


def test_switching_cost_depends_on_interruption_kind():
    planning, _ = plan()
    costs = {}
    for reason, completed_kind in (
        ("conversation", "scene.ended"),
        ("interruption", "phone.call_completed"),
    ):
        history = [event("sleep.ended")]
        history += execution_events(history, planning, NOW)
        history.append(event("activity.execution_paused", 5, schedule_id="write", reason=reason))
        history.append(
            event(
                completed_kind,
                15,
                **({"scene_id": "chat"} if reason == "conversation" else {"call_id": "call"}),
            )
        )
        decision = next(
            e
            for e in execution_events(history, planning, NOW + timedelta(minutes=15))
            if e.kind == "activity.resumption_decided"
        )
        costs[reason] = decision.payload["switching_cost_seconds"]
    assert costs["interruption"] > costs["conversation"]


def test_interval_is_tick_invariant_and_ignores_private_npc_scenes():
    planning, entry = plan()
    seed = [
        event("sleep.ended"),
        event("scene.started", 5, scene_id="private", initiator_id="mara", partner_id="ellis"),
    ]
    end = NOW + timedelta(minutes=30)
    coarse = seed + execution_window_events(seed, planning, NOW, end)
    fine = seed[:]
    for minute in range(31):
        fine += execution_events(fine, planning, NOW + timedelta(minutes=minute))
    assert activity_effort(coarse, entry, end)["worked_seconds"] == 1800
    assert activity_effort(fine, entry, end)["worked_seconds"] == 1800
    assert activity_effort(coarse, entry, end)["ready"]


def test_sleep_and_absence_do_not_count_as_work():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history += [
        event("pathos.moved", 5, location_id="park"),
        event("pathos.moved", 15, location_id="home"),
        event("sleep.started", 20),
        event("sleep.ended", 25),
    ]
    assert activity_effort(history, entry, NOW + timedelta(minutes=30))["worked_seconds"] == 900


def test_personal_context_is_not_an_exact_permanent_effort_archive():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    at = NOW + timedelta(minutes=10)
    context = execution_context(history, planning, at)
    assert context[0]["effort"] == "some time"
    assert context[0]["has_started"]
    assert "worked_seconds" not in context[0]
    assert execution_context(history, planning, at, observer=True)[0]["worked_seconds"] == 600
    closed = replace(planning, calendar={entry.schedule_id: replace(entry, status="failed")})
    assert execution_context(history, closed, NOW + timedelta(days=1)) == []


def test_an_incident_consumes_attention_even_in_the_same_room():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history += [
        event("incident.response_started", 5, incident_id="spill"),
        event("incident.response_completed", 15, incident_id="spill"),
    ]
    assert activity_effort(history, entry, NOW + timedelta(minutes=30))["worked_seconds"] == 1200


def test_conflicting_imported_plans_do_not_get_parallel_effort():
    planning, first = plan()
    second = replace(first, schedule_id="second", title="A different task")
    planning = replace(planning, calendar={first.schedule_id: first, second.schedule_id: second})
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    assert sum(e.kind == "activity.execution_started" for e in history) == 1
    at = NOW + timedelta(minutes=10)
    total = sum(activity_effort(history, e, at)["worked_seconds"] for e in (first, second))
    assert total == 600


def test_time_budget_changes_without_booking_or_prescribed_preparation():
    planning, entry = plan()
    entry = replace(
        entry,
        starts_at=(NOW + timedelta(hours=1)).isoformat(),
        ends_at=(NOW + timedelta(hours=2)).isoformat(),
        location_id="workshop",
        commitment_id="job",
    )
    planning = replace(planning, calendar={entry.schedule_id: entry})
    catalog = project_world_catalog([])
    ample = personal_time_budget(planning, catalog, NOW, "home")
    rushed = personal_time_budget(planning, catalog, NOW + timedelta(minutes=45), "home")
    assert ample["free_minutes"] > rushed["free_minutes"]
    assert ample["travel_minutes"] > 0
    assert ample["is_commitment"] and not ample["action_authority"]
    assert len(planning.calendar) == 1
    assert personal_time_budget(PlanningState(), catalog, NOW, "home")["free_minutes"] is None


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -1, 0, 0.001, 5])
def test_invalid_short_activity_durations_are_rejected(value):
    payload = dict(
        activity_type="letter_writing",
        title="Write a letter",
        motivation="I want to reply to a friend",
        action="work",
        location_id="home",
        resource_id="none",
        companion_id="none",
        starts_in_hours=0,
        duration_hours=value,
        priority=0.7,
    )
    with pytest.raises(ProposalRejected):
        parse_agency_candidate(json.dumps(payload))


def test_short_activity_runs_between_hourly_updates_in_life(tmp_path):
    candidate = AgencyCandidate(
        "letter_writing",
        "Write a letter",
        "I want to reply to a friend",
        ActionKind.WORK,
        "home",
        None,
        None,
        5 / 60,
        15 / 60,
        0.8,
    )
    result = resolve_agency_candidate(
        candidate,
        proposal_id="letter-2",
        state=PlanningState(),
        catalog=project_world_catalog([]),
        known_companion_ids=set(),
        actual_revision=2,
        simulated_at=NOW,
    )
    assert result.accepted
    store = SQLiteEventStore(tmp_path / "life.sqlite3")
    history = [
        DomainEvent("time.advanced", "pathos", {"simulated_at": NOW}),
        event("sleep.ended"),
        *result.events,
    ]
    store.append("pathos", history, 0)
    life = Life(store, StandInGateway())
    life.advance(20 / 60)
    events = life.history()
    start = next(e for e in events if e.kind == "activity.execution_started")
    assert start.payload["simulated_at"] == (NOW + timedelta(minutes=5)).isoformat()
    assert any(e.kind == "activity.completed" for e in events)
    execution = life.snapshot()["activity_execution"][0]
    assert execution["worked_seconds"] == pytest.approx(execution["required_seconds"])
    assert execution["required_seconds"] != execution["estimated_seconds"]
    assert life.snapshot()["time"] == (NOW + timedelta(minutes=20)).isoformat()
    # The minute-scale executor does not manufacture extra hourly thought/body ticks.
    assert not any(e.kind == "mind.layer_pulsed" for e in events)
    restored = Life(SQLiteEventStore(tmp_path / "life.sqlite3"), StandInGateway())
    assert restored.snapshot()["activity_execution"] == life.snapshot()["activity_execution"]
    assert restored.snapshot()["time"] == life.snapshot()["time"]
