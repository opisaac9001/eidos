"""Replayable activation state for Pathos's concurrent cognitive layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent


class CognitiveLayer(StrEnum):
    SOMATIC = "somatic"
    AFFECTIVE = "affective"
    ATTENTION = "attention"
    ASSOCIATIVE = "associative"
    DELIBERATIVE = "deliberative"
    PROSPECTIVE = "prospective"
    SOCIAL = "social"
    REFLECTIVE = "reflective"
    DREAM = "dream"


@dataclass(frozen=True, slots=True)
class LayerPulse:
    pulse_id: str
    layer: str
    mode: str
    focus_type: str
    focus_id: str
    focus_text: str
    activation: float
    simulated_at: str


@dataclass(frozen=True, slots=True)
class MindState:
    latest: Mapping[str, LayerPulse]
    pulse_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "latest", MappingProxyType(dict(self.latest)))
        object.__setattr__(self, "pulse_counts", MappingProxyType(dict(self.pulse_counts)))

    @classmethod
    def empty(cls) -> MindState:
        return cls({}, {})

    def apply(self, event: DomainEvent) -> MindState:
        if event.kind != "mind.layer_pulsed":
            return self
        payload = event.payload
        pulse_id = _required(payload, "pulse_id")
        layer = _required(payload, "layer")
        try:
            CognitiveLayer(layer)
        except ValueError:
            raise ValueError("Unknown cognitive layer") from None
        activation = payload.get("activation")
        if (
            isinstance(activation, bool)
            or not isinstance(activation, (int, float))
            or not 0 <= activation <= 1
        ):
            raise ValueError("Layer activation must be between zero and one")
        simulated_at = _required(payload, "simulated_at")
        if datetime.fromisoformat(simulated_at).utcoffset() is None:
            raise ValueError("Layer pulse time must be timezone-aware")
        pulse = LayerPulse(
            pulse_id,
            layer,
            _required(payload, "mode"),
            _required(payload, "focus_type"),
            _required(payload, "focus_id"),
            _required(payload, "focus_text"),
            float(activation),
            simulated_at,
        )
        latest = dict(self.latest)
        counts = dict(self.pulse_counts)
        latest[layer] = pulse
        counts[layer] = counts.get(layer, 0) + 1
        return MindState(latest, counts)


def project_mind(events: Sequence[DomainEvent]) -> MindState:
    state = MindState.empty()
    for event in events:
        state = state.apply(event)
    return state


def _required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value
