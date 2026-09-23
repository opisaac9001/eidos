import re
from datetime import datetime, timedelta

from test_activity_execution import NOW, event, plan

from eidos.application.activity_execution import activity_effort, execution_events
from eidos.application.lived_activity_window import lived_activity_window
from eidos.application.phone_calls import phone_call_events
from eidos.domain.agency import agency_output_schema
from eidos.domain.planning import PlanningState
from eidos.domain.world_catalog import project_world_catalog


def test_phone_call_occupies_time_and_cannot_stack_another_call():
    goal = event(
        "npc.goal_formed",
        actor_id="mara",
        goal_id="mara-connection-one",
        title="Speak with someone familiar",
        motivation_need="connection",
    )
    history = [event("sleep.ended"), goal]
    calls = phone_call_events(
        history,
        NOW,
        len(history),
        actor_locations={"pathos": "home", "mara": "cafe"},
        pathos_awake=True,
        pathos_energy=1.0,
        social_openness=1.0,
        instant_calls=False,
    )
    assert not any(e.kind == "phone.call_completed" for e in calls)
    answered = next(e for e in calls if e.kind == "phone.call_answered")
    ends = datetime.fromisoformat(answered.payload["ends_at"])
    assert 3 <= (ends - NOW).total_seconds() / 60 <= 12
    history.extend(calls)
    assert (
        phone_call_events(
            history,
            NOW + timedelta(minutes=1),
            len(history),
            actor_locations={"pathos": "home"},
            pathos_awake=True,
            instant_calls=False,
        )
        == []
    )
    output = lived_activity_window(
        history, PlanningState(), project_world_catalog([]), NOW, ends, repair_mastery=1
    )
    completed = next(e for e in output if e.kind == "phone.call_completed")
    assert completed.payload["simulated_at"] == ends.isoformat()


def test_natural_call_can_be_declined_without_a_user_conversation():
    history = [
        event("sleep.ended"),
        event(
            "npc.goal_formed",
            actor_id="mara",
            goal_id="mara-connection-one",
            title="Speak with someone familiar",
            motivation_need="connection",
        ),
    ]
    calls = phone_call_events(
        history,
        NOW,
        len(history),
        actor_locations={"pathos": "home", "mara": "cafe"},
        pathos_awake=True,
        pathos_energy=0.0,
        social_openness=0.0,
        instant_calls=False,
    )
    assert [e.kind for e in calls] == [
        "phone.call_received",
        "phone.call_declined",
        "phone.callback_scheduled",
    ]
    assert "conversation" not in calls[1].payload["reason"]
    assert (
        phone_call_events(
            [*history, *calls],
            NOW + timedelta(minutes=1),
            len(history) + len(calls),
            actor_locations={"pathos": "home", "mara": "cafe"},
            pathos_awake=True,
            instant_calls=False,
        )
        == []
    )


def test_answered_phone_time_is_not_activity_effort():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history += [
        event("phone.call_answered", 5, call_id="call"),
        event("phone.call_completed", 15, call_id="call"),
    ]
    assert activity_effort(history, entry, NOW + timedelta(minutes=30))["worked_seconds"] == 1200


def test_absorption_can_delay_notice_without_claiming_a_conscious_decline():
    goal = event(
        "npc.goal_formed",
        actor_id="mara",
        goal_id="mara-connection-one",
        title="Speak with someone familiar",
        motivation_need="connection",
    )
    history = [event("sleep.ended"), goal]
    missed = phone_call_events(
        history,
        NOW,
        len(history),
        actor_locations={"pathos": "home", "mara": "cafe"},
        pathos_awake=True,
        instant_calls=False,
        attention_absorption=1.0,
    )
    assert [e.kind for e in missed] == ["phone.call_received", "phone.call_missed"]
    assert "chose" not in missed[-1].payload["reason"].casefold()
    before = datetime.fromisoformat(str(missed[-1].payload["notice_after"])) - timedelta(seconds=1)
    assert (
        phone_call_events(
            [*history, *missed],
            before,
            len(history) + 2,
            actor_locations={"pathos": "home", "mara": "cafe"},
            pathos_awake=True,
            instant_calls=False,
        )
        == []
    )
    noticed_at = datetime.fromisoformat(str(missed[-1].payload["notice_after"]))
    noticed = phone_call_events(
        [*history, *missed],
        noticed_at,
        len(history) + 2,
        actor_locations={"pathos": "home", "mara": "cafe"},
        pathos_awake=True,
        instant_calls=False,
    )
    assert [e.kind for e in noticed] == ["phone.notification_noticed", "phone.callback_scheduled"]
    assert noticed[0].causation_id == missed[-1].event_id
    assert noticed[1].causation_id == noticed[0].event_id


def test_transport_slug_pattern_matches_the_whole_value():
    pattern = agency_output_schema(["home"], [], [])["properties"]["activity_type"]["pattern"]
    assert re.search(pattern, "letter_writing")
    assert not re.search(pattern, "unhurried neighborhood walk")
