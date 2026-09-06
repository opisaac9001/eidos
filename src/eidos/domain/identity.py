"""Stable, explicit identity facts used to ground choices and performer context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent

DEFAULT_VALUES: Mapping[str, float] = {
    "care": 0.78,
    "curiosity": 0.84,
    "reliability": 0.74,
    "autonomy": 0.68,
    "craft": 0.72,
}
DEFAULT_PREFERENCES = (
    "quiet mornings",
    "repairing useful objects",
    "unhurried neighborhood walks",
)


@dataclass(frozen=True, slots=True)
class IdentityState:
    name: str
    values: Mapping[str, float]
    preferences: tuple[str, ...]
    established: bool


def default_identity() -> IdentityState:
    return IdentityState("Pathos", dict(DEFAULT_VALUES), DEFAULT_PREFERENCES, False)


def identity_established_event(simulated_at: str) -> DomainEvent:
    return DomainEvent(
        "identity.established",
        "pathos",
        {
            "name": "Pathos",
            **{f"value_{name}": value for name, value in DEFAULT_VALUES.items()},
            **{
                f"preference_{position}": preference
                for position, preference in enumerate(DEFAULT_PREFERENCES, 1)
            },
            "simulated_at": simulated_at,
            "source": "character-pack-v1",
        },
        correlation_id="identity-pathos-v1",
    )


def project_identity(events: Sequence[DomainEvent]) -> IdentityState:
    identity = default_identity()
    for event in events:
        if event.kind != "identity.established":
            continue
        if identity.established:
            raise ValueError("Identity can only be established once")
        name = event.payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Identity requires a name")
        values: dict[str, float] = {}
        for key in DEFAULT_VALUES:
            value = event.payload.get(f"value_{key}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Identity values must be numeric")
            if not 0 <= float(value) <= 1:
                raise ValueError("Identity values must be between zero and one")
            values[key] = float(value)
        raw_preferences = tuple(
            event.payload.get(f"preference_{position}")
            for position in range(1, len(DEFAULT_PREFERENCES) + 1)
        )
        if not all(isinstance(item, str) and item.strip() for item in raw_preferences):
            raise ValueError("Identity preferences must be non-empty text")
        identity = IdentityState(name, values, tuple(str(item) for item in raw_preferences), True)
    return identity
