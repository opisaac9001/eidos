from dataclasses import replace
from datetime import timedelta

from test_activity_execution import NOW, event, plan

from eidos.application.activity_execution import activity_effort, execution_window_events
from eidos.application.messaging import communication_availability
from eidos.application.personal_journeys import journey_context, journey_window_events
from eidos.domain.state import PathosState
from eidos.domain.world_catalog import project_world_catalog


def trip():
    planning, entry = plan()
    entry = replace(
        entry,
        location_id="workshop",
        starts_at=(NOW + timedelta(minutes=30)).isoformat(),
        ends_at=(NOW + timedelta(minutes=60)).isoformat(),
    )
    return replace(planning, calendar={entry.schedule_id: entry}), entry


def test_trip_has_a_real_middle_and_no_early_arrival():
    planning, entry = trip()
    catalog = project_world_catalog([])
    history = [event("sleep.ended")]
    at = NOW + timedelta(minutes=29)
    history += journey_window_events(history, planning, catalog, NOW, at)
    assert [e.kind for e in history] == ["sleep.ended", "pathos.travel_started"]
    state = PathosState()
    for e in history:
        state = state.apply(e)
    assert state.location_id == "in_transit"
    assert not communication_availability(history, state).can_visit
    assert journey_context(history, at, catalog)["remaining_minutes"] == 1
    history += execution_window_events(history, planning, NOW, at)
    assert activity_effort(history, entry, at)["worked_seconds"] == 0
    history += journey_window_events(history, planning, catalog, at, at + timedelta(minutes=1))
    assert history[-1].kind == "pathos.moved"
    assert journey_context(history, at + timedelta(minutes=1), catalog) is None


def test_coarse_and_minute_travel_have_identical_times_and_effort():
    planning, entry = trip()
    catalog = project_world_catalog([])
    seed = [event("sleep.ended")]
    end = NOW + timedelta(minutes=60)
    coarse = seed + journey_window_events(seed, planning, catalog, NOW, end)
    coarse += execution_window_events(coarse, planning, NOW, end)
    fine = seed[:]
    for minute in range(60):
        start = NOW + timedelta(minutes=minute)
        stop = start + timedelta(minutes=1)
        fine += journey_window_events(fine, planning, catalog, start, stop)
        fine += execution_window_events(fine, planning, start, stop)

    def trips(events):
        return [
            (e.kind, e.payload["simulated_at"])
            for e in events
            if e.kind.startswith("pathos.travel") or e.kind == "pathos.moved"
        ]

    assert trips(coarse) == trips(fine)
    assert activity_effort(coarse, entry, end)["worked_seconds"] == 1800
    assert activity_effort(fine, entry, end)["worked_seconds"] == 1800


def test_late_waking_does_not_backdate_departure():
    planning, _ = trip()
    catalog = project_world_catalog([])
    history = [event("sleep.ended", 29)]
    result = journey_window_events(history, planning, catalog, NOW, NOW + timedelta(minutes=30))
    assert len(result) == 1
    assert result[0].payload["depart_at"] == (NOW + timedelta(minutes=29)).isoformat()
    assert result[0].payload["arrive_at"] > (NOW + timedelta(minutes=30)).isoformat()


def test_life_snapshot_and_restart_mid_journey(tmp_path):
    from eidos.adapters.sqlite_store import SQLiteEventStore
    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.life import Life
    from eidos.domain.actions import ActionKind
    from eidos.domain.agency import AgencyCandidate, resolve_agency_candidate
    from eidos.domain.events import DomainEvent
    from eidos.domain.planning import PlanningState

    result = resolve_agency_candidate(
        AgencyCandidate(
            "letter_writing",
            "Write at the workshop",
            "A quiet place to write",
            ActionKind.WORK,
            "workshop",
            None,
            None,
            0.5,
            0.5,
            0.8,
        ),
        proposal_id="trip",
        state=PlanningState(),
        catalog=project_world_catalog([]),
        known_companion_ids=set(),
        actual_revision=2,
        simulated_at=NOW,
    )
    assert result.accepted
    store = SQLiteEventStore(tmp_path / "journey.sqlite3")
    store.append(
        "pathos",
        [
            DomainEvent("time.advanced", "pathos", {"simulated_at": NOW}),
            event("sleep.ended"),
            *result.events,
        ],
        0,
    )
    life = Life(store, StandInGateway())
    life.advance(29 / 60)
    snapshot = life.snapshot()
    assert snapshot["journey"]["remaining_minutes"] == 1
    assert snapshot["pathos"]["location_id"] == "in_transit"
    assert snapshot["communication"]["can_visit"] is False
    assert (
        Life(SQLiteEventStore(tmp_path / "journey.sqlite3"), StandInGateway()).snapshot()
        == snapshot
    )
    life.advance(1 / 60)
    assert life.snapshot()["pathos"]["location_id"] == "workshop"
    life.advance(0.5)
    assert any(e.kind == "activity.completed" for e in life.history())


def test_no_plan_no_trip_and_sleep_blocks_departure():
    planning, _ = trip()
    assert (
        journey_window_events(
            [], planning, project_world_catalog([]), NOW, NOW + timedelta(minutes=60)
        )
        == []
    )
