from dataclasses import replace

from test_activity_execution import NOW, event, plan

from eidos.application.activity_execution import execution_events
from eidos.application.attention import attention_state


def test_actual_work_and_fresh_focus_can_be_engrossing():
    planning, _ = plan()
    history = [
        event("sleep.ended"),
        event(
            "mind.layer_pulsed",
            pulse_id="focus",
            layer="attention",
            mode="foreground",
            focus_type="task",
            focus_id="write",
            focus_text="The letter",
            activation=0.7,
        ),
    ]
    history += execution_events(history, planning, NOW)
    state = attention_state(history, planning, NOW)
    assert state["mode"] == "engrossed"
    assert state["absorption"] == 0.94
    assert state["working_schedule_id"] == "write"
    assert state["action_authority"] is False


def test_paused_or_completed_work_does_not_remain_engrossing():
    planning, entry = plan()
    history = [event("sleep.ended")]
    history += execution_events(history, planning, NOW)
    history += execution_events(history, planning, NOW.replace(minute=40))
    completed = replace(planning, calendar={entry.schedule_id: replace(entry, status="completed")})
    assert attention_state(history, completed, NOW.replace(minute=40))["mode"] == "open"
