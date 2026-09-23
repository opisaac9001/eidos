from datetime import datetime, timezone
from uuid import UUID

from eidos.application.volition import attended_impulses, impulse_attention_event, volition_snapshot
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState

NOW = datetime(2026, 2, 12, 8, tzinfo=timezone.utc)


def field(**changes):
    values = {
        "history": [],
        "decision_id": "same-decision",
        "planning": PlanningState(),
        "needs": {
            "energy": 0.7,
            "rest": 0.7,
            "hunger": 0.8,
            "connection": 0.2,
            "curiosity": 0.4,
            "mastery": 0.5,
            "household_dishes": 0.8,
        },
        "emotion": {"arousal": 0.35},
        "traits": {"follow_through": 0.64, "sociability": 0.52, "openness": 0.68},
        "workspace": [],
        "opportunities": [],
        "preparation": {"optional_scales": [{"scope": "small_batch"}]},
        "time_budget": {"next_plan": None},
        "current_location_id": "home",
    }
    values.update(changes)
    return attended_impulses(**values)


def test_attention_is_bounded_replay_stable_and_does_not_choose():
    first = field()
    second = field()
    assert first == second
    assert len(first["attended_impulses"]) == 4
    assert all(item["action_authority"] is False for item in first["attended_impulses"])
    assert {item["kind"] for item in first["attended_impulses"]} >= {"need", "domestic"}
    assert "winner" not in first


def test_low_energy_narrows_attention_and_makes_inaction_competitive():
    result = field(
        needs={
            "energy": 0.1,
            "rest": 0.1,
            "hunger": 0.8,
            "connection": 0.2,
            "curiosity": 0.4,
            "mastery": 0.5,
            "household_dishes": 0.8,
        }
    )
    assert result["attention_capacity"] == 3
    selected = {item["impulse_id"]: item for item in result["attended_impulses"]}
    assert "quiet:none" in selected
    assert selected["quiet:none"]["attention_strength"] > 0.5


def test_unperceived_opportunity_cannot_enter_the_choice_field():
    seen = field(
        opportunities=[{"opportunity_id": "maps", "text": "Ask about the maps", "owner": "pathos"}]
    )
    unseen = field(opportunities=[])
    assert any(item["target_id"] == "maps" for item in seen["attended_impulses"])
    assert not any(item.get("target_id") == "maps" for item in unseen["attended_impulses"])


def test_attention_event_has_scalar_payload_and_carries_inertia_once():
    source = DomainEvent(
        "thought.recorded",
        "pathos",
        {"text": "Maybe", "simulated_at": NOW.isoformat()},
        event_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    initial = field()
    event = impulse_attention_event(initial, "same-decision", source, NOW)
    assert event.payload["attended_count"] == len(initial["attended_impulses"])
    later = field(history=[event])
    carried = [item for item in later["attended_impulses"] if item.get("inertial_carryover")]
    assert carried
    assert all(event.payload[f"attended_impulse_{i}"] for i in range(1, 5))
    choice = DomainEvent(
        "agency.choice_made",
        "pathos",
        {"decision": "wait", "simulated_at": NOW.isoformat()},
        correlation_id="same-decision",
    )
    snapshot = volition_snapshot([event, choice])
    assert snapshot is not None
    assert snapshot["choice"] == "wait"
    assert snapshot["impulses"][0]["description"]


def test_completed_execution_does_not_create_false_momentum():
    history = [
        DomainEvent(
            "activity.execution_started",
            "pathos",
            {"schedule_id": "read", "title": "Read", "simulated_at": NOW.isoformat()},
        ),
        DomainEvent(
            "activity.execution_ready",
            "pathos",
            {"schedule_id": "read", "simulated_at": NOW.isoformat()},
        ),
    ]
    assert not any(
        item["kind"] == "continuation" for item in field(history=history)["attended_impulses"]
    )
