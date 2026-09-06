from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .events import DomainEvent


@dataclass(frozen=True, slots=True)
class PathosState:
    """Small initial projection of Pathos's authoritative state."""

    pathos_id: str = "pathos"
    location_id: str = "home"
    simulated_at: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
    energy: float = 1.0
    valence: float = 0.0
    arousal: float = 0.35
    rest: float = 0.75
    connection: float = 0.5
    curiosity: float = 0.5
    mastery: float = 0.45
    awake: bool = False

    def __post_init__(self) -> None:
        if not self.pathos_id.strip() or not self.location_id.strip():
            raise ValueError("Pathos state requires actor and location identifiers")
        if self.simulated_at.utcoffset() is None:
            raise ValueError("Pathos state time must be timezone-aware")
        _bounded_dimension(self.energy, "energy", 0, 1)
        _bounded_dimension(self.valence, "valence", -1, 1)
        _bounded_dimension(self.arousal, "arousal", 0, 1)
        for name in ("rest", "connection", "curiosity", "mastery"):
            _bounded_dimension(getattr(self, name), name, 0, 1)
        if type(self.awake) is not bool:
            raise ValueError("awake must be boolean")

    def apply(self, event: DomainEvent) -> PathosState:
        if event.aggregate_id != self.pathos_id:
            return self

        match event.kind:
            case "time.advanced":
                simulated_at = event.payload.get("simulated_at")
                if not isinstance(simulated_at, datetime) or simulated_at.tzinfo is None:
                    raise ValueError("time.advanced requires a timezone-aware simulated_at")
                if simulated_at < self.simulated_at:
                    raise ValueError("simulated time cannot move backwards")
                return replace(self, simulated_at=simulated_at)
            case "pathos.moved":
                location_id = event.payload.get("location_id")
                if not isinstance(location_id, str) or not location_id.strip():
                    raise ValueError("pathos.moved requires a location_id")
                return replace(self, location_id=location_id)
            case "affect.changed":
                energy = _bounded_dimension(
                    event.payload.get("energy", self.energy), "energy", 0, 1
                )
                valence = _bounded_dimension(
                    event.payload.get("valence", self.valence), "valence", -1, 1
                )
                arousal = _bounded_dimension(
                    event.payload.get("arousal", self.arousal), "arousal", 0, 1
                )
                return replace(self, energy=energy, valence=valence, arousal=arousal)
            case "needs.changed":
                return replace(
                    self,
                    rest=_bounded_dimension(event.payload.get("rest", self.rest), "rest", 0, 1),
                    connection=_bounded_dimension(
                        event.payload.get("connection", self.connection), "connection", 0, 1
                    ),
                    curiosity=_bounded_dimension(
                        event.payload.get("curiosity", self.curiosity), "curiosity", 0, 1
                    ),
                    mastery=_bounded_dimension(
                        event.payload.get("mastery", self.mastery), "mastery", 0, 1
                    ),
                )
            case "sleep.started":
                if not self.awake:
                    raise ValueError("Pathos is already asleep")
                return replace(self, awake=False)
            case "sleep.ended":
                if self.awake:
                    raise ValueError("Pathos is already awake")
                return replace(self, awake=True)
            case _:
                return self


def _bounded_dimension(value: object, name: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not lower <= result <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return result
