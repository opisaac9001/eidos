import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.agency import autonomous_activity_events
from eidos.application.causal_opportunities import fresh_cause
from eidos.application.life import Life
from eidos.application.self_projects import autonomous_project_events
from eidos.application.world_improvisation import improvised_world_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse

NOW = datetime(2026, 1, 12, 14, tzinfo=timezone.utc)


class QuietGateway(StandInGateway):
    def __init__(self):
        self.decisions = []

    async def generate(self, request):
        if request.capability in {
            "pathos_agency",
            "pathos_project",
            "moira_event",
            "moira_expansion",
        }:
            self.decisions.append(request)
            return ModelResponse('{"no_change": true}', "quiet", "test", "stop")
        return await super().generate(request)


def agency(history, gateway, current_location_id=None):
    return asyncio.run(
        autonomous_activity_events(
            history,
            NOW,
            len(history),
            gateway,
            planning=PlanningState(),
            catalog=project_world_catalog(history),
            needs={"curiosity": 0.3},
            emotion={},
            values={},
            preferences=(),
            traits={},
            memories=(),
            current_location_id=current_location_id,
        )
    )


def test_clock_alone_cannot_create_a_plan():
    gateway = QuietGateway()
    assert agency([], gateway) == []
    assert gateway.decisions == []


def test_explicit_do_nothing_is_a_choice_without_becoming_an_activity():
    class StillGateway(QuietGateway):
        async def generate(self, request):
            if request.capability == "pathos_agency":
                self.decisions.append(request)
                return ModelResponse(
                    '{"no_change": true, "mode": "do_nothing"}', "still", "test", "stop"
                )
            return await super().generate(request)

    thought = DomainEvent(
        "thought.recorded",
        "pathos",
        {"text": "I could do something, but I might not.", "simulated_at": NOW.isoformat()},
    )
    events = agency([thought], StillGateway(), current_location_id="home")
    choice = next(event for event in events if event.kind == "agency.choice_made")
    attended = next(event for event in events if event.kind == "agency.impulses_attended")
    chosen = next(event for event in events if event.kind == "agency.impulse_chosen")
    assert choice.payload["decision"] == "do_nothing"
    assert chosen.causation_id == attended.event_id
    assert choice.causation_id == chosen.event_id
    assert any(event.kind == "agency.left_unplanned" for event in events)
    assert not any(event.kind == "schedule.created" for event in events)


def test_private_deliberation_can_stop_before_the_scheduling_model_runs():
    class NoPlanGateway(QuietGateway):
        async def generate(self, request):
            self.decisions.append(request)
            if request.capability == "pathos_deliberation":
                return ModelResponse('{"no_change": true, "mode": "wait"}', "still", "test", "stop")
            raise AssertionError("Scheduling must not run after a decision to wait")

    thought = DomainEvent(
        "thought.recorded",
        "pathos",
        {"text": "Maybe later.", "simulated_at": NOW.isoformat()},
    )
    gateway = NoPlanGateway()
    events = agency([thought], gateway, current_location_id="home")
    assert [request.capability for request in gateway.decisions] == ["pathos_deliberation"]
    assert (
        next(event for event in events if event.kind == "agency.choice_made").payload["decision"]
        == "wait"
    )
    assert not any(event.kind == "agency.generation_requested" for event in events)


def test_project_thought_can_be_left_unplanned_without_becoming_a_failure():
    thought = DomainEvent(
        "thought.recorded",
        "pathos",
        {
            "text": "Not sure I want another project.",
            "simulated_at": NOW.isoformat(),
        },
    )
    events = asyncio.run(
        autonomous_project_events(
            [thought],
            NOW,
            1,
            QuietGateway(),
            planning=PlanningState(),
            catalog=project_world_catalog([]),
            needs={},
            emotion={},
            values={},
            preferences=(),
            traits={},
            memories=(),
        )
    )
    assert any(event.kind == "self_project.left_unplanned" for event in events)
    assert not any(event.kind in {"role.failed", "schedule.created"} for event in events)


def test_explicit_choice_can_start_here_now_but_cannot_teleport():
    class ChoiceGateway(QuietGateway):
        async def generate(self, request):
            if request.capability == "pathos_deliberation":
                context = json.loads(request.messages[0].content)
                impulse = next(
                    item
                    for item in context["choice_field"]["attended_impulses"]
                    if item["kind"] == "thought"
                )
                return ModelResponse(
                    json.dumps(
                        {
                            "mode": "pursue",
                            "chosen_impulse_id": impulse["impulse_id"],
                            "intention": "Read a little at home now.",
                        }
                    ),
                    "choice",
                    "test",
                    "stop",
                )
            return ModelResponse(
                json.dumps(
                    {
                        "activity_type": "quiet_reading",
                        "title": "Read a little at home",
                        "motivation": "I want to spend an hour reading here now.",
                        "action": "learn",
                        "location_id": "home",
                        "resource_id": "none",
                        "companion_id": "none",
                        "starts_in_hours": 0,
                        "duration_hours": 1,
                        "estimate_confidence": 0.6,
                        "priority": 0.5,
                    }
                ),
                "choice",
                "test",
                "stop",
            )

    history = [
        DomainEvent(
            "thought.recorded",
            "pathos",
            {
                "text": "I want to read here now.",
                "importance": 1.0,
                "simulated_at": NOW.isoformat(),
            },
        )
    ]
    here = agency(history, ChoiceGateway(), current_location_id="home")
    entry = next(event for event in here if event.kind == "schedule.created")
    assert entry.payload["starts_at"] == NOW.isoformat()
    elsewhere = agency(history, ChoiceGateway(), current_location_id="park")
    assert not any(event.kind == "schedule.created" for event in elsewhere)
    assert any(event.payload.get("error_code") == "travel_required" for event in elsewhere)


def test_thought_can_remain_private_without_a_booking_and_is_not_reconsidered_forever():
    gateway = QuietGateway()
    thought = DomainEvent(
        "thought.recorded",
        "pathos",
        {
            "text": "Maybe I will go for a walk. Or just stay here.",
            "simulated_at": NOW.isoformat(),
        },
    )
    events = agency([thought], gateway)
    assert any(event.kind == "agency.left_unplanned" for event in events)
    assert not any(event.kind == "schedule.created" for event in events)
    assert events[0].causation_id == thought.event_id
    assert agency([thought, *events], gateway) == []
    assert len(gateway.decisions) == 1


def test_stale_future_and_untimed_events_are_not_current_causes():
    for timestamp in (
        None,
        "bad",
        (NOW - timedelta(days=1)).isoformat(),
        (NOW + timedelta(hours=1)).isoformat(),
    ):
        event = DomainEvent("thought.recorded", "pathos", {"simulated_at": timestamp})
        assert fresh_cause([event], NOW, frozenset({"thought.recorded"})) is None


def test_world_does_not_generate_an_incident_because_it_is_six_oclock():
    gateway = QuietGateway()
    result = asyncio.run(
        improvised_world_events(
            [],
            NOW.replace(hour=18),
            0,
            gateway,
            season="winter",
            weather="Clear",
        )
    )
    assert result == []
    assert gateway.decisions == []


def test_default_life_has_no_authored_itinerary_or_automatic_opening_bookings(tmp_path):
    life = Life(SQLiteEventStore(tmp_path / "natural.sqlite3"), QuietGateway())
    life.advance(24)
    history = life.history()
    # The only bookings a new life has are shifts under the job agreement he accepted.
    agreements = {event.event_id for event in history if event.kind == "work.agreement_accepted"}
    bookings = [event for event in history if event.kind == "schedule.created"]
    assert agreements
    assert all(event.causation_id in agreements for event in bookings)
    assert not any(
        event.kind == "memory.recorded" and event.payload.get("source") == "authored-routine"
        for event in history
    )
