"""Replayable attempts to respond to emotion without erasing its causes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from eidos.domain.events import DomainEvent

STRATEGIES = {
    "grounding_pause",
    "make_space_for_feeling",
    "name_mixed_feeling",
    "protect_rest",
}


@dataclass(frozen=True, slots=True)
class RegulationAttempt:
    regulation_id: str
    strategy: str
    trigger_sample_id: str
    selected_at: str
    status: str = "selected"
    practiced_at: str | None = None
    completed_at: str | None = None
    outcome: str | None = None


@dataclass(frozen=True, slots=True)
class RegulationState:
    attempts: Mapping[str, RegulationAttempt]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", MappingProxyType(dict(self.attempts)))

    @classmethod
    def empty(cls) -> RegulationState:
        return cls({})

    def apply(self, event: DomainEvent) -> RegulationState:
        attempts = dict(self.attempts)
        if event.kind == "emotion.regulation_selected":
            regulation_id = _required(event, "regulation_id")
            if regulation_id in attempts:
                raise ValueError("Emotional regulation attempt already exists")
            strategy = _required(event, "strategy")
            if strategy not in STRATEGIES:
                raise ValueError("Unknown emotional regulation strategy")
            if (
                event.payload.get("owner") != "pathos"
                or event.payload.get("visibility") != "private"
            ):
                raise ValueError("Emotional regulation must begin private to Pathos")
            attempts[regulation_id] = RegulationAttempt(
                regulation_id,
                strategy,
                _required(event, "trigger_sample_id"),
                _required(event, "simulated_at"),
            )
        elif event.kind == "emotion.regulation_practiced":
            regulation_id = _required(event, "regulation_id")
            attempt = _existing(attempts, regulation_id)
            if attempt.status != "selected" or attempt.strategy == "protect_rest":
                raise ValueError("Only an immediate selected strategy can be practiced")
            attempts[regulation_id] = replace(
                attempt,
                status="completed",
                practiced_at=_required(event, "simulated_at"),
                completed_at=_required(event, "simulated_at"),
                outcome=_required(event, "outcome"),
            )
        elif event.kind == "emotion.regulation_completed":
            regulation_id = _required(event, "regulation_id")
            attempt = _existing(attempts, regulation_id)
            if attempt.status != "selected" or attempt.strategy != "protect_rest":
                raise ValueError("Only selected rest protection can complete later")
            attempts[regulation_id] = replace(
                attempt,
                status="completed",
                completed_at=_required(event, "simulated_at"),
                outcome=_required(event, "outcome"),
            )
        return RegulationState(attempts)


def project_regulation(events: Sequence[DomainEvent]) -> RegulationState:
    state = RegulationState.empty()
    prior: dict[str, DomainEvent] = {}
    for event in events:
        if event.kind == "emotion.regulation_selected":
            source_id = _required(event, "source_emotion_event_id")
            source = prior.get(source_id)
            if (
                source is None
                or source.kind != "emotion.sampled"
                or event.causation_id != source.event_id
                or event.payload.get("trigger_sample_id") != source.payload.get("sample_id")
            ):
                raise ValueError("Emotional regulation needs its triggering emotion sample")
        elif event.kind == "emotion.regulation_practiced":
            regulation_id = _required(event, "regulation_id")
            selected = next(
                (
                    item
                    for item in prior.values()
                    if item.kind == "emotion.regulation_selected"
                    and item.payload.get("regulation_id") == regulation_id
                ),
                None,
            )
            if selected is None or event.causation_id != selected.event_id:
                raise ValueError("Emotional practice needs its selected strategy")
        elif event.kind == "emotion.regulation_completed":
            source_id = _required(event, "source_sleep_event_id")
            source = prior.get(source_id)
            if (
                source is None
                or source.kind != "sleep.started"
                or event.causation_id != source.event_id
            ):
                raise ValueError("Rest protection completes only through actual sleep")
        state = state.apply(event)
        prior[str(event.event_id)] = event
    return state


def _existing(attempts: Mapping[str, RegulationAttempt], regulation_id: str) -> RegulationAttempt:
    if regulation_id not in attempts:
        raise ValueError("Unknown emotional regulation attempt")
    return attempts[regulation_id]


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()
