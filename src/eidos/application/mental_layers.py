"""Advance multiple cognitive layers without confusing activation with action."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from eidos.application.inner_life import active_concerns
from eidos.domain.emotions import classify_emotion, project_emotion
from eidos.domain.events import DomainEvent
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import project_planning
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import project_wellbeing


def mental_layer_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    npc_locations: Mapping[str, str],
) -> list[DomainEvent]:
    """Emit bounded hourly layer activations from Pathos-accessible state."""
    if at.utcoffset() is None:
        raise ValueError("Mental layer time must be timezone-aware")
    existing = {
        str(event.payload["pulse_id"])
        for event in history
        if event.kind == "mind.layer_pulsed" and isinstance(event.payload.get("pulse_id"), str)
    }
    planning = project_planning(list(history))
    previous_emotion = project_emotion(history)
    concerns = active_concerns(list(history))
    active_goals = [goal for goal in planning.goals.values() if goal.status == "active"]
    needs = {
        "rest": state.rest,
        "connection": state.connection,
        "curiosity": state.curiosity,
        "mastery": state.mastery,
        "energy": state.energy,
        "nourishment": 1 - state.hunger,
    }
    need_name, need_value = min(needs.items(), key=lambda item: (item[1], item[0]))
    physical = project_wellbeing(history).active
    if physical is not None and physical.severity > 1 - need_value:
        need_name = physical.kind
        need_value = 1 - physical.severity
    focus_type = "concern" if concerns else "goal" if active_goals else "place"
    focus_id = (
        str(concerns[-1].payload["concern_id"])
        if concerns
        else active_goals[0].goal_id
        if active_goals
        else state.location_id
    )
    focus_text = (
        str(concerns[-1].payload["text"])
        if concerns
        else active_goals[0].title
        if active_goals
        else state.location_id
    )
    sustained_low_hours = previous_emotion.sustained_low_hours if state.valence <= -0.35 else 0
    emotion_label = classify_emotion(state.valence, state.arousal, sustained_low_hours)
    specs: list[tuple[CognitiveLayer, str, str, str, str, float]] = [
        (
            CognitiveLayer.SOMATIC,
            "background",
            "need",
            need_name,
            f"Monitor {need_name}",
            min(1.0, 0.25 + (1 - need_value)),
        ),
        (
            CognitiveLayer.ATTENTION,
            "foreground",
            focus_type,
            focus_id,
            focus_text,
            0.75 if concerns else 0.6,
        ),
        (
            CognitiveLayer.AFFECTIVE,
            "background",
            "emotion",
            emotion_label,
            f"Feel {emotion_label}",
            min(1.0, 0.3 + abs(state.valence) + abs(state.arousal - 0.35)),
        ),
        (
            CognitiveLayer.ASSOCIATIVE,
            "background" if state.awake else "dreamward",
            "cue",
            state.location_id,
            f"Associations around {state.location_id}",
            0.55 if state.awake else 0.35,
        ),
    ]
    if state.awake and at.hour % 3 == 0:
        specs.append(
            (
                CognitiveLayer.DELIBERATIVE,
                "foreground",
                "goal" if active_goals else "day",
                active_goals[0].goal_id if active_goals else at.date().isoformat(),
                active_goals[0].title if active_goals else "Shape the next part of the day",
                0.65,
            )
        )
    companions = sorted(
        actor_id for actor_id, location in npc_locations.items() if location == state.location_id
    )
    if state.awake and companions:
        specs.append(
            (
                CognitiveLayer.SOCIAL,
                "foreground",
                "person",
                companions[0],
                f"Notice {companions[0]}",
                min(0.9, 0.5 + 0.2 * state.connection),
            )
        )
    if at.hour == 21:
        specs.append(
            (
                CognitiveLayer.REFLECTIVE,
                "scheduled",
                "day",
                at.date().isoformat(),
                "Review the lived day",
                0.7,
            )
        )
    if not state.awake and at.hour == 23:
        specs.append(
            (
                CognitiveLayer.DREAM,
                "sleep",
                focus_type,
                focus_id,
                focus_text,
                0.6 if concerns else 0.4,
            )
        )
    output = []
    for layer, mode, kind, item_id, text, activation in specs:
        pulse_id = f"{at.isoformat()}:{layer.value}"
        if pulse_id in existing:
            continue
        output.append(
            DomainEvent(
                "mind.layer_pulsed",
                "pathos",
                {
                    "pulse_id": pulse_id,
                    "layer": layer.value,
                    "mode": mode,
                    "focus_type": kind,
                    "focus_id": item_id,
                    "focus_text": text,
                    "activation": activation,
                    "simulated_at": at.isoformat(),
                    "action_authority": False,
                },
                correlation_id=f"mind-{at.isoformat()}",
            )
        )
    return output


def mind_context(history: Sequence[DomainEvent]) -> list[dict[str, object]]:
    mind = project_mind(history)
    return [
        {
            "layer": pulse.layer,
            "mode": pulse.mode,
            "focus_type": pulse.focus_type,
            "focus_id": pulse.focus_id,
            "focus_text": pulse.focus_text,
            "activation": pulse.activation,
        }
        for pulse in mind.latest.values()
    ]
