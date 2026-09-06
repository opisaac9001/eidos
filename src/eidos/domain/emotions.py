"""Persistent emotional interpretation and bounded effects on future choices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


@dataclass(frozen=True, slots=True)
class EmotionState:
    label: str = "quiet"
    intensity: float = 0.0
    valence: float = 0.0
    arousal: float = 0.35
    sustained_low_hours: int = 0
    pattern: str = "transient"
    simulated_at: str | None = None


@dataclass(frozen=True, slots=True)
class EmotionalPlanningBias:
    initiative: float
    social_openness: float
    risk_tolerance: float
    pace: float


def classify_emotion(valence: float, arousal: float, sustained_low_hours: int = 0) -> str:
    _dimensions(valence, arousal)
    if sustained_low_hours >= 72 and valence <= -0.35:
        return "prolonged low mood"
    if valence >= 0.55 and arousal >= 0.55:
        return "joy"
    if valence >= 0.3 and arousal >= 0.55:
        return "excitement"
    if valence >= 0.2:
        return "contentment"
    if valence <= -0.5 and arousal <= 0.5:
        return "sadness"
    if valence <= -0.3 and arousal >= 0.65:
        return "anxiety"
    if valence <= -0.2 and arousal >= 0.45:
        return "frustration"
    if valence <= -0.15:
        return "melancholy"
    if arousal >= 0.7:
        return "alertness"
    if arousal <= 0.2:
        return "calm"
    return "quiet"


def emotional_planning_bias(
    valence: float, arousal: float, sustained_low_hours: int = 0
) -> EmotionalPlanningBias:
    _dimensions(valence, arousal)
    positive = max(0.0, valence)
    negative = max(0.0, -valence)
    strain = max(0.0, arousal - 0.6)
    persistence = min(0.3, sustained_low_hours / 240)
    return EmotionalPlanningBias(
        initiative=_clamp(0.55 + 0.25 * positive - 0.3 * negative - persistence),
        social_openness=_clamp(0.55 + 0.3 * positive - 0.25 * negative - 0.2 * strain),
        risk_tolerance=_clamp(0.5 + 0.15 * positive - 0.25 * negative - 0.35 * strain),
        pace=_clamp(0.6 + 0.2 * positive - 0.2 * negative - 0.25 * strain - persistence),
    )


def emotion_sample_events(
    history: Sequence[DomainEvent], state: PathosState, at: datetime
) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Emotion sampling time must be timezone-aware")
    sample_id = f"emotion:{at.isoformat()}"
    if any(
        event.kind == "emotion.sampled" and event.payload.get("sample_id") == sample_id
        for event in history
    ):
        return []
    previous = project_emotion(history)
    low_hours = previous.sustained_low_hours + 1 if state.valence <= -0.35 else 0
    label = classify_emotion(state.valence, state.arousal, low_hours)
    intensity = _clamp(max(abs(state.valence), abs(state.arousal - 0.35) * 1.25))
    pattern = "prolonged" if low_hours >= 72 else "sustained" if low_hours >= 24 else "transient"
    source = next(
        (
            event
            for event in reversed(history)
            if event.kind in {"appraisal.recorded", "affect.episode_started", "affect.changed"}
        ),
        None,
    )
    return [
        DomainEvent(
            "emotion.sampled",
            "pathos",
            {
                "sample_id": sample_id,
                "label": label,
                "intensity": intensity,
                "valence": state.valence,
                "arousal": state.arousal,
                "sustained_low_hours": low_hours,
                "pattern": pattern,
                "source_event_id": str(source.event_id) if source else None,
                "simulated_at": at.isoformat(),
                "clinical_diagnosis": False,
            },
            causation_id=source.event_id if source else None,
            correlation_id=f"affect-{at.date().isoformat()}",
        )
    ]


def project_emotion(events: Sequence[DomainEvent]) -> EmotionState:
    state = EmotionState()
    for event in events:
        if event.kind != "emotion.sampled":
            continue
        payload = event.payload
        label = payload.get("label")
        pattern = payload.get("pattern")
        simulated_at = payload.get("simulated_at")
        if not all(
            isinstance(value, str) and value.strip() for value in (label, pattern, simulated_at)
        ):
            raise ValueError("Emotion sample requires label, pattern, and time")
        assert isinstance(simulated_at, str)
        if datetime.fromisoformat(simulated_at).utcoffset() is None:
            raise ValueError("Emotion sample time must be timezone-aware")
        valence = _number(payload.get("valence"), "valence")
        arousal = _number(payload.get("arousal"), "arousal")
        _dimensions(valence, arousal)
        intensity = _number(payload.get("intensity"), "intensity")
        low_hours = payload.get("sustained_low_hours")
        if (
            not 0 <= intensity <= 1
            or isinstance(low_hours, bool)
            or not isinstance(low_hours, int)
            or low_hours < 0
        ):
            raise ValueError("Emotion intensity or duration is invalid")
        state = EmotionState(
            str(label), intensity, valence, arousal, low_hours, str(pattern), simulated_at
        )
    return state


def _dimensions(valence: float, arousal: float) -> None:
    if not -1 <= valence <= 1 or not 0 <= arousal <= 1:
        raise ValueError("Emotion dimensions are outside their bounds")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Emotion {name} must be numeric")
    return float(value)
