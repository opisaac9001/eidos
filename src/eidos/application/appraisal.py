"""Bounded deterministic appraisal connecting experiences to durable needs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.sleep import sleep_window_at
from eidos.domain.state import PathosState


def baseline_affect_events(
    state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Move transient affect gently toward baseline without erasing its causes."""
    valence_step = 0.025 if not state.awake else 0.012 if state.valence < 0 else 0.018
    arousal_step = 0.035 if not state.awake else 0.02
    valence = _toward(state.valence, 0.0, valence_step)
    arousal = _toward(state.arousal, 0.35, arousal_step)
    if valence == state.valence and arousal == state.arousal:
        return [], state
    event = DomainEvent(
        "affect.changed",
        "pathos",
        {
            "valence": valence,
            "arousal": arousal,
            "reason": "sleep recovery" if not state.awake else "baseline recovery",
            "simulated_at": simulated_at.isoformat(),
        },
    )
    return [event], state.apply(event)


def affect_episode_events(
    history: Sequence[DomainEvent], state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Translate each new appraisal into one bounded, source-linked affect episode."""
    processed = {
        str(event.payload["appraisal_id"])
        for event in history
        if event.kind == "affect.episode_started"
    }
    output: list[DomainEvent] = []
    current = state
    for appraisal in history:
        appraisal_id = str(appraisal.event_id)
        if appraisal.kind != "appraisal.recorded" or appraisal_id in processed:
            continue
        desirability = float(appraisal.payload["desirability"])
        novelty = float(appraisal.payload["novelty"])
        already_applied = appraisal.payload.get("source_kind") == "dream.effect_applied"
        valence_delta, adaptation = (
            (0.0, 1.0)
            if already_applied
            else _episode_valence_delta(
                [*history, *output], current, appraisal, desirability, simulated_at
            )
        )
        arousal_delta = max(
            -0.06,
            min(
                0.18,
                (novelty - 0.25) * 0.12
                + abs(desirability) * (0.08 if desirability < 0 else 0.04 * adaptation),
            ),
        )
        episode = DomainEvent(
            "affect.episode_started",
            "pathos",
            {
                "appraisal_id": appraisal_id,
                "source_event_id": str(appraisal.payload["source_event_id"]),
                "source_kind": str(appraisal.payload["source_kind"]),
                "valence_delta": valence_delta,
                "adaptation": adaptation,
                "arousal_delta": arousal_delta,
                "already_applied": already_applied,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=appraisal.event_id,
            correlation_id=appraisal.correlation_id,
        )
        changed = DomainEvent(
            "affect.changed",
            "pathos",
            {
                "valence": max(-1.0, min(1.0, current.valence + valence_delta)),
                "arousal": max(0.0, min(1.0, current.arousal + arousal_delta)),
                "reason": "bounded appraisal episode",
                "appraisal_id": appraisal_id,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=episode.event_id,
            correlation_id=appraisal.correlation_id,
        )
        output.extend((episode, changed))
        processed.add(appraisal_id)
        current = current.apply(changed)
    return output, current


def sleep_and_need_events(
    state: PathosState,
    simulated_at: datetime,
    history: Sequence[DomainEvent] = (),
    *,
    pathos_busy: bool = False,
) -> tuple[list[DomainEvent], PathosState]:
    """Apply selected sleep or a legacy circadian fallback and hourly needs."""
    events: list[DomainEvent] = []
    current = state
    window = sleep_window_at(history, simulated_at) if history else None
    if window is None:
        should_be_awake = 7 <= simulated_at.hour < 23
        reason = "circadian fallback"
    else:
        should_be_awake = not (window.bed <= simulated_at < window.wake)
        reason = f"selected nightly window: {window.reason}"
    if not should_be_awake and current.awake and pathos_busy:
        should_be_awake = True
    if should_be_awake != current.awake:
        transition = DomainEvent(
            "sleep.ended" if should_be_awake else "sleep.started",
            "pathos",
            {
                "simulated_at": simulated_at.isoformat(),
                "reason": reason,
            },
        )
        events.append(transition)
        current = current.apply(transition)
    deltas = (
        {
            "rest": -0.03,
            "connection": -0.012,
            "curiosity": -0.003,
            "mastery": -0.006,
            "hunger": 0.045,
        }
        if current.awake
        else {
            "rest": 0.04,
            "connection": -0.004,
            "curiosity": -0.001,
            "mastery": -0.002,
            "hunger": 0.015,
        }
    )
    payload = {
        name: max(0.0, min(1.0, float(getattr(current, name)) + delta))
        for name, delta in deltas.items()
    }
    drift = DomainEvent(
        "needs.changed",
        "pathos",
        {
            **payload,
            "reason": "sleep recovery" if not current.awake else "hourly need pressure",
            "simulated_at": simulated_at.isoformat(),
        },
    )
    events.append(drift)
    current = current.apply(drift)
    return events, current


def appraisal_events(
    history: Sequence[DomainEvent], state: PathosState, simulated_at: datetime
) -> tuple[list[DomainEvent], PathosState]:
    """Appraise each eligible source once and return updated projected state."""
    appraised = {
        str(event.payload["source_event_id"])
        for event in history
        if event.kind == "appraisal.recorded"
    }
    output: list[DomainEvent] = []
    current = state
    for source in history:
        source_id = str(source.event_id)
        if source_id in appraised:
            continue
        effect = _effect(source, history)
        if effect is None:
            continue
        need, delta, desirability, novelty, controllability = effect
        appraisal = DomainEvent(
            "appraisal.recorded",
            "pathos",
            {
                "source_event_id": source_id,
                "source_kind": source.kind,
                "need": need,
                "need_delta": delta,
                "desirability": desirability,
                "novelty": novelty,
                "controllability": controllability,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=source.event_id,
            correlation_id=source.correlation_id,
        )
        output.append(appraisal)
        appraised.add(source_id)
        if need != "affect":
            value = max(0.0, min(1.0, float(getattr(current, need)) + delta))
            changed = DomainEvent(
                "needs.changed",
                "pathos",
                {
                    need: value,
                    "reason": f"appraisal of {source.kind}",
                    "source_event_id": source_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=appraisal.event_id,
                correlation_id=source.correlation_id,
            )
            output.append(changed)
            current = current.apply(changed)
    return output, current


def _effect(
    event: DomainEvent, history: Sequence[DomainEvent]
) -> tuple[str, float, float, float, float] | None:
    if (
        event.kind == "mind.layer_pulsed"
        and event.payload.get("layer") == "prospective"
        and not _prospective_focus_already_appraised(event, history)
    ):
        tone = event.payload.get("anticipatory_valence")
        activation = event.payload.get("activation")
        if (
            isinstance(tone, bool)
            or not isinstance(tone, (int, float))
            or not -0.25 <= float(tone) <= 0.3
            or isinstance(activation, bool)
            or not isinstance(activation, (int, float))
            or not 0 <= float(activation) <= 1
        ):
            return None
        return (
            "affect",
            0.0,
            float(tone),
            0.25 + 0.3 * float(activation),
            0.55,
        )
    if event.kind == "schedule.cancelled":
        schedule_id = event.payload.get("schedule_id")
        anticipated = next(
            (
                item
                for item in reversed(history)
                if item.kind == "mind.layer_pulsed"
                and item.payload.get("layer") == "prospective"
                and item.payload.get("focus_id") == schedule_id
                and isinstance(item.payload.get("anticipatory_valence"), (int, float))
                and not isinstance(item.payload.get("anticipatory_valence"), bool)
            ),
            None,
        )
        if anticipated is not None:
            anticipated_tone = float(anticipated.payload["anticipatory_valence"])
            return (
                "affect",
                0.0,
                max(-0.22, min(0.18, round(-0.8 * anticipated_tone, 3))),
                0.38,
                0.55,
            )
    if event.kind == "prospective_memory.lapsed":
        return ("affect", 0.0, -0.2, 0.42, 0.7)
    if event.kind == "memory.recorded" and event.payload.get("source") == "authored-routine":
        location = event.payload.get("location_id")
        if not isinstance(location, str):
            return None
        return {
            "home": ("rest", 0.05, 0.35, 0.1, 0.8),
            "cafe": ("connection", 0.04, 0.3, 0.25, 0.7),
            "park": ("curiosity", 0.05, 0.35, 0.35, 0.8),
            "workshop": ("mastery", 0.04, 0.4, 0.25, 0.85),
        }.get(location)
    if (
        event.kind == "memory.recorded"
        and event.payload.get("owner") == "pathos"
        and event.payload.get("source") == "direct-perception"
        and event.payload.get("category") in {"world-event", "world-thread"}
    ):
        affective_tone = event.payload.get("affective_tone")
        if (
            not isinstance(affective_tone, bool)
            and isinstance(affective_tone, (int, float))
            and -1 <= float(affective_tone) <= 1
        ):
            tone = float(affective_tone)
            return (
                "affect",
                0.0,
                tone,
                max(0.2, min(0.8, float(event.payload.get("importance", 0.5)))),
                0.45,
            )
        return (
            "curiosity",
            0.03 if event.payload.get("category") == "world-event" else 0.02,
            0.15,
            0.5 if event.payload.get("category") == "world-event" else 0.3,
            0.55,
        )
    if event.kind == "npc.encountered":
        return ("connection", 0.05, 0.4, 0.45, 0.6)
    if event.kind == "social.activity_completed":
        return ("connection", 0.06, 0.55, 0.35, 0.8)
    if event.kind == "scene.turn_taken" and _pathos_experienced_scene_turn(event, history):
        return ("connection", 0.025, 0.3, 0.35, 0.75)
    if event.kind == "meal.eaten":
        return ("affect", 0.0, 0.25, 0.1, 0.9)
    if event.kind == "meal.unavailable":
        return ("affect", 0.0, -0.2, 0.2, 0.65)
    if event.kind == "finance.payment_missed":
        return ("affect", 0.0, -0.5, 0.35, 0.45)
    if (
        event.kind == "finance.transaction_recorded"
        and event.payload.get("category") == "work_income"
    ):
        return ("affect", 0.0, 0.2, 0.15, 0.75)
    if event.kind == "wellbeing.episode_started":
        severity = float(event.payload.get("severity", 0.3))
        return ("affect", 0.0, -severity, 0.3, 0.35)
    if event.kind == "wellbeing.episode_progressed":
        return ("affect", 0.0, 0.12, 0.1, 0.45)
    if event.kind == "wellbeing.episode_resolved":
        return ("affect", 0.0, 0.22, 0.15, 0.8)
    if event.kind == "household.task_completed":
        return ("mastery", 0.025, 0.18, 0.1, 0.9)
    if event.kind == "activity.completed":
        if event.payload.get("activity") == "attend":
            return ("connection", 0.05, 0.45, 0.3, 0.75)
        if event.payload.get("activity") in {"learn", "work"}:
            return ("mastery", 0.06, 0.6, 0.3, 0.85)
    if event.kind == "schedule.interrupted":
        return ("mastery", -0.04, -0.35, 0.5, 0.4)
    if event.kind == "action.accepted" and event.payload.get("action") == "repair":
        return ("mastery", 0.08, 0.7, 0.35, 0.9)
    if event.kind == "commitment.missed":
        return ("connection", -0.08, -0.75, 0.3, 0.65)
    if event.kind == "goal.achieved":
        return ("mastery", 0.08, 0.8, 0.4, 0.9)
    if event.kind == "incident.response_completed":
        return ("connection", 0.04, 0.45, 0.55, 0.75)
    if event.kind in {"incident.response_declined", "incident.response_abandoned"}:
        return ("affect", 0.0, -0.3, 0.45, 0.65)
    if event.kind == "disagreement.expressed":
        return ("affect", 0.0, -0.6, 0.65, 0.55)
    if event.kind == "boundary.stated":
        return ("affect", 0.0, -0.15, 0.5, 0.8)
    if event.kind == "apology.offered":
        return ("connection", 0.04, 0.55, 0.35, 0.85)
    if event.kind == "dream.effect_applied":
        return ("affect", 0.0, float(event.payload.get("valence_delta", 0)), 0.65, 0.15)
    if event.kind == "reflection.recorded":
        source_memory_id = event.payload.get("source_memory_id")
        if not isinstance(source_memory_id, str):
            return None
        memory = next(
            (
                item
                for item in history
                if str(item.event_id) == source_memory_id
                and item.kind == "memory.recorded"
                and item.aggregate_id == "pathos"
                and item.payload.get("owner", "pathos") == "pathos"
            ),
            None,
        )
        if memory is None or memory.payload.get("category") == "dream":
            return None
        source_ids = {str(memory.event_id)}
        remembered_source = memory.payload.get("source_event_id")
        if isinstance(remembered_source, str):
            source_ids.add(remembered_source)
        prior = next(
            (
                item
                for item in reversed(history)
                if item.kind == "appraisal.recorded"
                and item.payload.get("source_event_id") in source_ids
            ),
            None,
        )
        if prior is None:
            return None
        desirability = max(-0.28, min(0.28, float(prior.payload["desirability"]) * 0.35))
        return ("affect", 0.0, desirability, 0.12, 0.7)
    return None


def _prospective_focus_already_appraised(
    event: DomainEvent, history: Sequence[DomainEvent]
) -> bool:
    focus_id = event.payload.get("focus_id")
    if not isinstance(focus_id, str):
        return True
    sources = {
        str(item.payload["source_event_id"])
        for item in history
        if item.kind == "appraisal.recorded"
        and item.payload.get("source_kind") == "mind.layer_pulsed"
        and isinstance(item.payload.get("source_event_id"), str)
    }
    return any(
        str(item.event_id) in sources
        and item.kind == "mind.layer_pulsed"
        and item.payload.get("layer") == "prospective"
        and item.payload.get("focus_id") == focus_id
        for item in history
    )


def _pathos_experienced_scene_turn(event: DomainEvent, history: Sequence[DomainEvent]) -> bool:
    """Require participation or an exact owned perception before appraisal."""
    if "pathos" in {event.payload.get("actor_id"), event.payload.get("audience_id")}:
        return True
    source_id = str(event.event_id)
    return any(
        perceived.kind == "perception.recorded"
        and perceived.payload.get("owner") == "pathos"
        and perceived.payload.get("source_event_id") == source_id
        for perceived in history
    )


def _toward(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    if value > target:
        return max(target, value - step)
    return value


def _episode_valence_delta(
    history: Sequence[DomainEvent],
    state: PathosState,
    appraisal: DomainEvent,
    desirability: float,
    simulated_at: datetime,
) -> tuple[float, float]:
    """Apply loss salience, positive saturation, and ordinary hedonic adaptation."""
    if desirability == 0:
        return 0.0, 1.0
    if desirability < 0:
        # Unpleasant experiences are consequential, but their effect tapers near
        # the lower bound instead of driving an unbounded spiral.
        saturation = max(0.4, 1.0 - max(0.0, -state.valence) * 0.6)
        return max(-0.16, desirability * 0.16 * saturation), 1.0

    source_kind = str(appraisal.payload.get("source_kind", ""))
    cutoff = simulated_at - timedelta(hours=24)
    repeats = 0
    for event in history:
        if (
            event.kind != "affect.episode_started"
            or event.payload.get("source_kind") != source_kind
        ):
            continue
        raw_time = event.payload.get("simulated_at")
        if not isinstance(raw_time, str):
            continue
        try:
            occurred_at = datetime.fromisoformat(raw_time)
        except ValueError:
            continue
        if occurred_at.utcoffset() is not None and cutoff <= occurred_at <= simulated_at:
            repeats += 1
    repetition = max(0.2, 1.0 / (1.0 + repeats * 0.45))
    saturation = max(0.15, 1.0 - max(0.0, state.valence) * 0.85)
    adaptation = round(repetition * saturation, 4)
    return min(0.06, desirability * 0.06 * adaptation), adaptation
