"""Choose bounded coping responses from Pathos's actual emotional state."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from eidos.domain.emotional_regulation import project_regulation
from eidos.domain.emotions import EmotionState
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


def emotional_regulation_events(
    history: Sequence[DomainEvent],
    state: PathosState,
    emotion: EmotionState,
    simulated_at: datetime,
) -> tuple[list[DomainEvent], PathosState]:
    """Resolve rest protection, then select at most one honest response per day."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Emotional regulation time must be timezone-aware")
    output: list[DomainEvent] = []
    regulation = project_regulation(history)
    pending_rest = next(
        (
            attempt
            for attempt in regulation.attempts.values()
            if attempt.strategy == "protect_rest" and attempt.status == "selected"
        ),
        None,
    )
    if pending_rest is not None:
        selected = next(
            event
            for event in history
            if event.kind == "emotion.regulation_selected"
            and event.payload.get("regulation_id") == pending_rest.regulation_id
        )
        sleep = next(
            (
                event
                for event in history
                if event.kind == "sleep.started"
                and str(event.payload.get("simulated_at", "")) >= pending_rest.selected_at
            ),
            None,
        )
        if sleep is not None:
            output.append(
                DomainEvent(
                    "emotion.regulation_completed",
                    "pathos",
                    {
                        "regulation_id": pending_rest.regulation_id,
                        "strategy": pending_rest.strategy,
                        "source_sleep_event_id": str(sleep.event_id),
                        "outcome": "Pathos protected the intended sleep window.",
                        "owner": "pathos",
                        "visibility": "private",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=sleep.event_id,
                    correlation_id=selected.correlation_id,
                )
            )
        return output, state
    if not state.awake or simulated_at.hour != 21:
        return output, state
    date = simulated_at.date().isoformat()
    latest_selection = max(
        (datetime.fromisoformat(attempt.selected_at) for attempt in regulation.attempts.values()),
        default=None,
    )
    if latest_selection is not None and simulated_at - latest_selection < timedelta(hours=72):
        return output, state
    source = next(
        (
            event
            for event in reversed(history)
            if event.kind == "emotion.sampled"
            and event.payload.get("sample_id") == f"emotion:{simulated_at.isoformat()}"
        ),
        None,
    )
    if source is None:
        return output, state
    if emotion.arousal >= 0.65:
        strategy = "grounding_pause"
        reason = "Arousal was high enough to narrow attention."
        arousal_step = 0.05
    elif emotion.valence <= -0.3 and state.rest <= 0.45:
        strategy = "protect_rest"
        reason = "Low feeling coincided with depleted rest."
        arousal_step = 0.0
    elif emotion.valence <= -0.3:
        strategy = "make_space_for_feeling"
        reason = "The low feeling needed acknowledgment rather than forced cheerfulness."
        arousal_step = 0.025
    elif emotion.secondary_label is not None and emotion.complexity >= 0.65:
        strategy = "name_mixed_feeling"
        reason = "Opposed recent experiences were both still emotionally active."
        arousal_step = 0.02
    else:
        return output, state
    regulation_id = f"regulation-{date}"
    selected = DomainEvent(
        "emotion.regulation_selected",
        "pathos",
        {
            "regulation_id": regulation_id,
            "strategy": strategy,
            "trigger_sample_id": str(source.payload["sample_id"]),
            "source_emotion_event_id": str(source.event_id),
            "reason": reason,
            "owner": "pathos",
            "visibility": "private",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=source.event_id,
        correlation_id=regulation_id,
    )
    output.append(selected)
    if strategy == "protect_rest":
        return output, state
    practiced = DomainEvent(
        "emotion.regulation_practiced",
        "pathos",
        {
            "regulation_id": regulation_id,
            "strategy": strategy,
            "outcome": "Pathos practiced the selected response without claiming the feeling ended.",
            "owner": "pathos",
            "visibility": "private",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=selected.event_id,
        correlation_id=regulation_id,
    )
    output.append(practiced)
    new_arousal = _toward(state.arousal, 0.35, arousal_step)
    if new_arousal != state.arousal:
        changed = DomainEvent(
            "affect.changed",
            "pathos",
            {
                "arousal": new_arousal,
                "reason": f"bounded effect of {strategy}",
                "regulation_id": regulation_id,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=practiced.event_id,
            correlation_id=regulation_id,
        )
        output.append(changed)
        state = state.apply(changed)
    return output, state


def _toward(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    if value > target:
        return max(target, value - step)
    return value
