"""Advance multiple cognitive layers without confusing activation with action."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.inner_life import active_concerns
from eidos.domain.emotions import classify_emotion, project_emotion
from eidos.domain.events import DomainEvent
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import CalendarEntry, Goal, PlanningState, project_planning
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import project_wellbeing


def mental_layer_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    npc_locations: Mapping[str, str],
    *,
    household_loads: Mapping[str, float] | None = None,
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
    focus_type, focus_id, focus_text, focus_activation = _attention_focus(
        history,
        state,
        at,
        planning,
        concerns,
        active_goals,
        npc_locations,
        need_name,
        need_value,
        household_loads or {},
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
            focus_activation,
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
    upcoming = _next_upcoming_plan(planning, at, within_hours=8)
    if state.awake and upcoming is not None:
        starts_at, item = upcoming
        hours_until = max(0.0, (starts_at - at).total_seconds() / 3600)
        activation = 0.38 + 0.42 * (1 - min(8.0, hours_until) / 8)
        specs.append(
            (
                CognitiveLayer.PROSPECTIVE,
                "background",
                "planned_activity",
                item.schedule_id,
                f"Look ahead to {item.title}, while knowing the plan may still change",
                activation,
            )
        )
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


def _attention_focus(
    history: Sequence[DomainEvent],
    state: PathosState,
    at: datetime,
    planning: PlanningState,
    concerns: Sequence[DomainEvent],
    active_goals: Sequence[Goal],
    npc_locations: Mapping[str, str],
    need_name: str,
    need_value: float,
    household_loads: Mapping[str, float],
) -> tuple[str, str, str, float]:
    """Choose one foreground focus while preserving bounded attentional inertia."""
    candidates: list[tuple[float, str, str, str]] = [
        (
            0.3 + 0.6 * (1 - need_value),
            "need",
            need_name,
            f"Notice the need for {need_name.replace('_', ' ')}",
        ),
        (0.3, "place", state.location_id, f"Notice {state.location_id}"),
    ]
    if household_loads and state.awake and state.location_id == "home" and at.hour in {7, 18, 21}:
        task, load = max(household_loads.items(), key=lambda item: (item[1], item[0]))
        if load >= 0.48:
            candidates.append(
                (
                    0.3 + 0.45 * load,
                    "household",
                    task,
                    f"Notice the accumulating {task}",
                )
            )
    if concerns:
        concern = concerns[-1]
        raw_importance = concern.payload.get("importance", 0.8)
        importance = (
            float(raw_importance)
            if isinstance(raw_importance, (int, float)) and not isinstance(raw_importance, bool)
            else 0.8
        )
        recent_focuses = sum(
            event.kind == "mind.layer_pulsed"
            and event.payload.get("layer") == CognitiveLayer.ATTENTION.value
            and event.payload.get("focus_id") == concern.payload.get("concern_id")
            and _within_recent_hours(event, at, 6)
            for event in history
        )
        candidates.append(
            (
                max(0.35, 0.55 + 0.28 * min(1.0, max(0.0, importance)) - 0.12 * recent_focuses),
                "concern",
                str(concern.payload["concern_id"]),
                str(concern.payload["text"]),
            )
        )
    if active_goals:
        goal = active_goals[0]
        candidates.append((0.62, "goal", goal.goal_id, goal.title))
    companions = sorted(
        actor_id for actor_id, location in npc_locations.items() if location == state.location_id
    )
    if companions:
        person_id = companions[0]
        candidates.append(
            (
                0.45 + 0.4 * (1 - state.connection),
                "person",
                person_id,
                f"Notice {person_id}",
            )
        )
    recent_encounter = next(
        (
            event
            for event in reversed(history)
            if event.kind == "npc.encountered"
            and isinstance(event.payload.get("person_id"), str)
            and _within_recent_hours(event, at, 2)
        ),
        None,
    )
    if recent_encounter is not None:
        person_id = str(recent_encounter.payload["person_id"])
        candidates.append(
            (
                0.7,
                "person",
                person_id,
                f"Keep the recent meeting with {person_id} in mind",
            )
        )
    upcoming = _next_upcoming_plan(planning, at, within_hours=2)
    if upcoming is not None:
        starts_at, item = upcoming
        minutes = max(0, int((starts_at - at).total_seconds() / 60))
        candidates.append(
            (
                0.9 if minutes <= 30 else 0.72,
                "commitment",
                item.schedule_id,
                f"Prepare for {item.title}",
            )
        )
    previous = project_mind(history).latest.get(CognitiveLayer.ATTENTION.value)
    scored = [
        (
            min(1.0, score + (0.08 if previous and previous.focus_id == item_id else 0.0)),
            focus_type,
            item_id,
            text,
        )
        for score, focus_type, item_id, text in candidates
    ]
    score, focus_type, item_id, text = max(
        scored,
        key=lambda item: (item[0], item[1], item[2]),
    )
    return focus_type, item_id, text, score


def _next_upcoming_plan(
    planning: PlanningState, at: datetime, *, within_hours: int
) -> tuple[datetime, CalendarEntry] | None:
    upcoming = sorted(
        (
            (datetime.fromisoformat(item.starts_at), item)
            for item in planning.calendar.values()
            if item.status == "scheduled"
            and item.actor_id in {None, "pathos"}
            and at <= datetime.fromisoformat(item.starts_at)
            <= at + timedelta(hours=within_hours)
        ),
        key=lambda pair: (pair[0], pair[1].schedule_id),
    )
    return upcoming[0] if upcoming else None


def _within_recent_hours(event: DomainEvent, at: datetime, hours: int) -> bool:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        return False
    try:
        observed_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    return observed_at.utcoffset() is not None and timedelta(0) <= at - observed_at <= timedelta(
        hours=hours
    )


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
