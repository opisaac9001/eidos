import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.npc_agency import autonomous_npc_plan_events
from eidos.application.offscreen import npc_world_events
from eidos.application.opportunities import available_opportunities, opportunity_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse

NOW = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)


def test_life_processes_npc_arrival_between_hourly_updates(tmp_path):
    store = SQLiteEventStore(tmp_path / "movement.sqlite3")
    before = NOW - timedelta(minutes=1)
    history = [
        DomainEvent("time.advanced", "pathos", {"simulated_at": before}),
        *npc_world_events([], before),
        plan(),
    ]
    store.append("pathos", history, 0)
    life = Life(store, StandInGateway())
    life.advance(1 / 60)
    journey = next(
        event
        for event in life.history()
        if event.kind == "npc.travel_started" and event.payload["plan_id"] == "walk-and-read"
    )
    arrival = datetime.fromisoformat(journey.payload["arrive_at"])
    life.advance((arrival - NOW).total_seconds() / 3600)
    assert arrival.minute != 0
    assert project_npcs(life.history(), arrival).people["rowan"].location_id == "park"
    moved = next(
        event
        for event in life.history()
        if event.kind == "npc.moved" and event.payload["actor_id"] == "rowan"
    )
    assert moved.payload["simulated_at"] == arrival.isoformat()


def plan():
    return DomainEvent(
        "npc.plan_created",
        "pathos",
        {
            "actor_id": "rowan",
            "owner": "rowan",
            "visibility": "private",
            "plan_id": "walk-and-read",
            "title": "Read in the square",
            "action": "read",
            "location_id": "park",
            "scheduled_for": NOW.isoformat(),
            "due_at": (NOW + timedelta(hours=3)).isoformat(),
            "simulated_at": NOW.isoformat(),
        },
    )


def test_no_clock_based_teleport_and_real_time_before_arrival_and_completion():
    history = npc_world_events([], NOW - timedelta(minutes=1))
    history.append(plan())
    departure = npc_world_events(history, NOW)
    history += departure
    journey = next(
        event
        for event in departure
        if event.kind == "npc.travel_started" and event.payload["plan_id"] == "walk-and-read"
    )
    assert project_npcs(history, NOW).people["rowan"].location_id == "in-transit"
    arrival_at = datetime.fromisoformat(journey.payload["arrive_at"])
    assert arrival_at > NOW
    before = npc_world_events(history, arrival_at - timedelta(seconds=1))
    assert not any(
        event.kind == "npc.moved" and event.payload["actor_id"] == "rowan" for event in before
    )
    history += before
    arrival = npc_world_events(history, arrival_at)
    history += arrival
    assert project_npcs(history, arrival_at).people["rowan"].location_id == "park"
    assert not any(event.kind == "npc.plan_completed" for event in arrival)
    assert not [
        event
        for event in npc_world_events(history, arrival_at)
        if event.payload.get("actor_id") == "rowan"
    ]
    finished = npc_world_events(history, arrival_at + timedelta(hours=1))
    assert any(event.kind == "npc.plan_completed" for event in finished)
    history += finished
    assert (
        project_npcs(history, arrival_at + timedelta(hours=1)).people["rowan"].plan_status
        == "completed"
    )
    after = npc_world_events(history, arrival_at + timedelta(hours=1))
    # Only their own day may move them on now that the plan is done.
    assert all(str(event.payload.get("plan_id", "")).startswith("day-") for event in after)


def test_without_a_plan_residents_keep_their_own_day_but_invent_no_activity():
    history = npc_world_events([], NOW)
    for offset in (1, 3, 8, 14):
        events = npc_world_events(history, NOW + timedelta(hours=offset))
        assert not any(event.kind == "npc.activity_recorded" for event in events)
        # Any travel is their ordinary day (work, home for the night), never a teleport.
        assert all(
            event.payload.get("reason") in {"their day", "home for the night"}
            for event in events
            if event.kind == "npc.travel_started"
        )
        history += events
    # Late at night, everyone without plans of their own is home.
    night = NOW.replace(hour=23, minute=30) + timedelta(days=0)
    for step in range(4):
        history += npc_world_events(history, night + timedelta(hours=step))
    people = project_npcs(history, night + timedelta(hours=3)).people
    assert people["mara"].location_id == "home"


def test_npc_can_leave_need_unplanned_before_day_eleven_and_outside_seven_pm():
    class Quiet:
        async def generate(self, request):
            return ModelResponse('{"no_change": true}', "quiet", "test", "stop")

    evidence = DomainEvent(
        "npc.needs_changed",
        "pathos",
        {
            "actor_id": "rowan",
            "owner": "rowan",
            "visibility": "private",
            "energy": 0.7,
            "connection": 0.7,
            "purpose": 0.2,
            "simulated_at": NOW.isoformat(),
        },
    )
    events = asyncio.run(
        autonomous_npc_plan_events([evidence], NOW, Quiet(), project_world_catalog([]))
    )
    assert any(event.kind == "npc.idea_left_unplanned" for event in events)
    assert not any(event.kind == "npc.plan_created" for event in events)
    assert (
        asyncio.run(
            autonomous_npc_plan_events([evidence, *events], NOW, Quiet(), project_world_catalog([]))
        )
        == []
    )


def test_only_observed_opportunities_persist_and_never_create_a_booking():
    def perception(owner):
        return DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": owner,
                "opportunity": "Ask about the maps",
                "location_id": "cafe",
                "duration_hours": 3,
                "simulated_at": NOW.isoformat(),
            },
        )

    history = [perception("mara"), perception("pathos")]
    noticed = opportunity_events(history, NOW)
    assert len(noticed) == 1
    assert noticed[0].causation_id == history[1].event_id
    history += noticed
    assert opportunity_events(history, NOW + timedelta(hours=1)) == []
    options = available_opportunities(history, NOW + timedelta(hours=1))
    assert len(options) == 1 and options[0]["action_authority"] is False
    assert available_opportunities(history, NOW + timedelta(hours=3)) == []
    assert not any(event.kind == "schedule.created" for event in history)
