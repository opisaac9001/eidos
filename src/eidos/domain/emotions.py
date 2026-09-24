"""Persistent emotional interpretation and bounded effects on future choices."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import (
    GrowOnlyMap,
    IncrementalFold,
    event_index,
    events_of,
    payload_candidates,
)
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
    secondary_label: str | None = None
    complexity: float = 0.0
    positive_source_event_id: str | None = None
    negative_source_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class EmotionalPlanningBias:
    initiative: float
    social_openness: float
    risk_tolerance: float
    pace: float


@dataclass(frozen=True, slots=True)
class EmotionalSpeechBias:
    openness: float
    warmth: float
    elaboration: float
    hesitation: float
    cadence: str
    target_words: int


def classify_emotion(valence: float, arousal: float, sustained_low_hours: int = 0) -> str:
    _dimensions(valence, arousal)
    if sustained_low_hours >= 72 and valence <= -0.35:
        return "prolonged low mood"
    if valence >= 0.35 and arousal >= 0.5:
        return "joy"
    if valence >= 0.18 and arousal >= 0.5:
        return "excitement"
    if valence >= 0.07:
        return "contentment"
    if valence <= -0.28 and arousal <= 0.5:
        return "sadness"
    if valence <= -0.18 and arousal >= 0.55:
        return "anxiety"
    if valence <= -0.1 and arousal >= 0.42:
        return "frustration"
    if valence <= -0.06:
        return "melancholy"
    if arousal >= 0.7:
        return "alertness"
    if arousal <= 0.2:
        return "calm"
    return "quiet"


def emotional_planning_bias(
    valence: float,
    arousal: float,
    sustained_low_hours: int = 0,
    complexity: float = 0.0,
) -> EmotionalPlanningBias:
    _dimensions(valence, arousal)
    if not 0 <= complexity <= 1:
        raise ValueError("Emotional complexity must be between zero and one")
    positive = max(0.0, valence)
    negative = max(0.0, -valence)
    strain = max(0.0, arousal - 0.6)
    persistence = min(0.3, sustained_low_hours / 240)
    return EmotionalPlanningBias(
        initiative=_clamp(
            0.55 + 0.25 * positive - 0.3 * negative - persistence - 0.08 * complexity
        ),
        social_openness=_clamp(0.55 + 0.3 * positive - 0.25 * negative - 0.2 * strain),
        risk_tolerance=_clamp(
            0.5 + 0.15 * positive - 0.25 * negative - 0.35 * strain - 0.12 * complexity
        ),
        pace=_clamp(
            0.6 + 0.2 * positive - 0.2 * negative - 0.25 * strain - persistence - 0.05 * complexity
        ),
    )


def emotional_speech_bias(
    valence: float,
    arousal: float,
    energy: float,
    sustained_low_hours: int = 0,
    complexity: float = 0.0,
    *,
    hurried: bool = False,
) -> EmotionalSpeechBias:
    """Translate persistent affect into style without dictating speech content."""
    _dimensions(valence, arousal)
    if not 0 <= energy <= 1 or not 0 <= complexity <= 1 or sustained_low_hours < 0:
        raise ValueError("Speech disposition inputs are outside their bounds")
    positive = max(0.0, valence)
    negative = max(0.0, -valence)
    strain = max(0.0, arousal - 0.6)
    persistence = min(0.3, sustained_low_hours / 240)
    openness = _clamp(0.52 + 0.24 * positive + 0.14 * energy - 0.25 * negative - persistence)
    warmth = _clamp(0.58 + 0.22 * positive - 0.12 * negative - 0.08 * strain)
    elaboration = _clamp(
        0.32
        + 0.32 * energy
        + 0.18 * openness
        - 0.2 * strain
        - 0.12 * complexity
        - (0.22 if hurried else 0.0)
    )
    hesitation = _clamp(0.12 + 0.32 * complexity + 0.18 * negative + 0.12 * strain)
    if hurried or arousal >= 0.78:
        cadence = "clipped"
    elif energy <= 0.3 or sustained_low_hours >= 24:
        cadence = "slow"
    elif complexity >= 0.45:
        cadence = "hesitant"
    elif valence >= 0.3 and energy >= 0.55:
        cadence = "easy"
    else:
        cadence = "steady"
    return EmotionalSpeechBias(
        openness=openness,
        warmth=warmth,
        elaboration=elaboration,
        hesitation=hesitation,
        cadence=cadence,
        target_words=max(6, min(48, round(8 + 36 * elaboration))),
    )


def emotion_sample_events(
    history: Sequence[DomainEvent], state: PathosState, at: datetime
) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Emotion sampling time must be timezone-aware")
    sample_id = f"emotion:{at.isoformat()}"
    if any(
        event.kind == "emotion.sampled" and event.payload.get("sample_id") == sample_id
        for event in payload_candidates(history, "sample_id", sample_id)
    ):
        return []
    previous = project_emotion(history)
    low_hours = previous.sustained_low_hours + 1 if state.valence <= -0.35 else 0
    label = classify_emotion(state.valence, state.arousal, low_hours)
    intensity = _clamp(max(abs(state.valence), abs(state.arousal - 0.35) * 1.25))
    pattern = "prolonged" if low_hours >= 72 else "sustained" if low_hours >= 24 else "transient"
    positive, negative = _recent_opposed_appraisals(history, at, previous)
    secondary_label = None
    complexity = 0.0
    if positive is not None and negative is not None:
        positive_weight = float(positive.payload["desirability"])
        negative_weight = abs(float(negative.payload["desirability"]))
        complexity = _clamp((positive_weight + negative_weight) / 2)
        secondary_label = (
            ("sadness" if negative_weight >= 0.5 else "unease")
            if state.valence >= 0
            else ("hope" if positive_weight >= 0.5 else "warmth")
        )
    source = next(
        (
            event
            for event in reversed(history)
            if event.kind in {"appraisal.recorded", "affect.episode_started", "affect.changed"}
        ),
        None,
    )
    sampled = DomainEvent(
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
    output = [sampled]
    if positive is not None and negative is not None and secondary_label is not None:
        positive_id = str(positive.event_id)
        negative_id = str(negative.event_id)
        changed = (
            previous.positive_source_event_id != positive_id
            or previous.negative_source_event_id != negative_id
            or previous.secondary_label != secondary_label
        )
        if changed:
            output.append(
                DomainEvent(
                    "emotion.mixed_state_recognized",
                    "pathos",
                    {
                        "mixed_state_id": f"mixed:{sample_id}",
                        "secondary_label": secondary_label,
                        "complexity": complexity,
                        "positive_source_event_id": positive_id,
                        "negative_source_event_id": negative_id,
                        "reason": f"{label} remained alongside {secondary_label}",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=negative.event_id,
                    correlation_id=f"affect-{at.date().isoformat()}",
                )
            )
    elif previous.secondary_label is not None:
        output.append(
            DomainEvent(
                "emotion.mixed_state_resolved",
                "pathos",
                {
                    "positive_source_event_id": previous.positive_source_event_id,
                    "negative_source_event_id": previous.negative_source_event_id,
                    "reason": "The opposed appraisal pair moved outside the active window.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=sampled.event_id,
                correlation_id=f"affect-{at.date().isoformat()}",
            )
        )
    return output


class _EmotionFold(NamedTuple):
    state: EmotionState
    appraisals: GrowOnlyMap[str, DomainEvent]
    samples: GrowOnlyMap[str, bool]


def _emotion_step(fold: _EmotionFold, event: DomainEvent) -> _EmotionFold:
    state = fold.state
    if event.kind == "appraisal.recorded":
        return fold._replace(appraisals=fold.appraisals.with_item(str(event.event_id), event))
    if event.kind == "emotion.mixed_state_recognized":
        secondary = event.payload.get("secondary_label")
        positive_source = event.payload.get("positive_source_event_id")
        negative_source = event.payload.get("negative_source_event_id")
        complexity = _number(event.payload.get("complexity"), "complexity")
        positive = fold.appraisals.get(str(positive_source))
        negative = fold.appraisals.get(str(negative_source))
        if (
            not isinstance(secondary, str)
            or not secondary.strip()
            or not 0 < complexity <= 1
            or positive is None
            or negative is None
            or float(positive.payload.get("desirability", 0)) < 0.3
            or float(negative.payload.get("desirability", 0)) > -0.3
            or event.causation_id != negative.event_id
        ):
            raise ValueError("Mixed emotion requires opposed appraisal evidence")
        return fold._replace(
            state=replace(
                state,
                secondary_label=secondary.strip(),
                complexity=complexity,
                positive_source_event_id=str(positive_source),
                negative_source_event_id=str(negative_source),
            )
        )
    if event.kind == "emotion.mixed_state_resolved":
        if state.secondary_label is None or str(event.causation_id) not in fold.samples:
            raise ValueError("Only a sampled mixed emotion can resolve")
        return fold._replace(
            state=replace(
                state,
                secondary_label=None,
                complexity=0.0,
                positive_source_event_id=None,
                negative_source_event_id=None,
            )
        )
    if event.kind != "emotion.sampled":
        return fold
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
    return _EmotionFold(
        EmotionState(
            label=str(label),
            intensity=intensity,
            valence=valence,
            arousal=arousal,
            sustained_low_hours=low_hours,
            pattern=str(pattern),
            simulated_at=simulated_at,
            secondary_label=state.secondary_label,
            complexity=state.complexity,
            positive_source_event_id=state.positive_source_event_id,
            negative_source_event_id=state.negative_source_event_id,
        ),
        fold.appraisals,
        fold.samples.with_item(str(event.event_id), True),
    )


_EMOTION_FOLD: IncrementalFold[_EmotionFold] = IncrementalFold(
    lambda: _EmotionFold(EmotionState(), GrowOnlyMap(), GrowOnlyMap()), _emotion_step
)


def project_emotion(events: Sequence[DomainEvent]) -> EmotionState:
    return _EMOTION_FOLD(events).state


def _dimensions(valence: float, arousal: float) -> None:
    if not -1 <= valence <= 1 or not 0 <= arousal <= 1:
        raise ValueError("Emotion dimensions are outside their bounds")


def _recent_opposed_appraisals(
    events: Sequence[DomainEvent], at: datetime, previous: EmotionState
) -> tuple[DomainEvent | None, DomainEvent | None]:
    positive = None
    negative = None
    cutoff = at - timedelta(hours=12)
    # Event ids are unique in a stream, so the first event with an id is the only one.
    by_id = event_index(events)
    carried_positive = by_id.get(previous.positive_source_event_id or "")
    carried_negative = by_id.get(previous.negative_source_event_id or "")
    if _eligible_appraisal(carried_positive, cutoff, at, positive=True) and _eligible_appraisal(
        carried_negative, cutoff, at, positive=False
    ):
        return carried_positive, carried_negative
    for event in reversed(events_of(events, "appraisal.recorded")):
        raw_time = event.payload.get("simulated_at")
        desirability = event.payload.get("desirability")
        if (
            not isinstance(raw_time, str)
            or isinstance(desirability, bool)
            or not isinstance(desirability, (int, float))
        ):
            continue
        try:
            event_time = datetime.fromisoformat(raw_time)
        except ValueError:
            continue
        if event_time.utcoffset() is None or event_time < cutoff or event_time > at:
            continue
        if positive is None and desirability >= 0.3:
            positive = event
        elif negative is None and desirability <= -0.3:
            negative = event
        if positive is not None and negative is not None:
            break
    return positive, negative


def _eligible_appraisal(
    event: DomainEvent | None, cutoff: datetime, at: datetime, *, positive: bool
) -> bool:
    if event is None or event.kind != "appraisal.recorded":
        return False
    raw_time = event.payload.get("simulated_at")
    desirability = event.payload.get("desirability")
    if (
        not isinstance(raw_time, str)
        or isinstance(desirability, bool)
        or not isinstance(desirability, (int, float))
    ):
        return False
    try:
        event_time = datetime.fromisoformat(raw_time)
    except ValueError:
        return False
    threshold_met = desirability >= 0.3 if positive else desirability <= -0.3
    return event_time.utcoffset() is not None and cutoff <= event_time <= at and threshold_met


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Emotion {name} must be numeric")
    return float(value)
