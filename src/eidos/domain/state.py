from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Sequence

from .events import DomainEvent
from .folding import IncrementalFold


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
    hunger: float = 0.15
    awake: bool = False

    def __post_init__(self) -> None:
        if not self.pathos_id.strip() or not self.location_id.strip():
            raise ValueError("Pathos state requires actor and location identifiers")
        if self.simulated_at.utcoffset() is None:
            raise ValueError("Pathos state time must be timezone-aware")
        _bounded_dimension(self.energy, "energy", 0, 1)
        _bounded_dimension(self.valence, "valence", -1, 1)
        _bounded_dimension(self.arousal, "arousal", 0, 1)
        for name in ("rest", "connection", "curiosity", "mastery", "hunger"):
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
            case "pathos.travel_started":
                if event.payload.get("origin_id") != self.location_id:
                    raise ValueError("Journey must start at the current location")
                depart = datetime.fromisoformat(str(event.payload["depart_at"]))
                arrive = datetime.fromisoformat(str(event.payload["arrive_at"]))
                if depart.utcoffset() is None or arrive.utcoffset() is None or arrive <= depart:
                    raise ValueError("Journey requires an aware, positive duration")
                return replace(self, location_id="in_transit")
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
                    hunger=_bounded_dimension(
                        event.payload.get("hunger", self.hunger), "hunger", 0, 1
                    ),
                )
            case "meal.eaten":
                if not self.awake:
                    raise ValueError("Pathos cannot eat while asleep")
                meal_id = event.payload.get("meal_id")
                meal_kind = event.payload.get("meal_kind")
                text = event.payload.get("text")
                location_id = event.payload.get("location_id")
                simulated_at = event.payload.get("simulated_at")
                if not isinstance(meal_id, str) or not meal_id.strip():
                    raise ValueError("A meal requires an identifier")
                if meal_kind not in {"breakfast", "lunch", "evening_meal", "snack"}:
                    raise ValueError("Unknown meal kind")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("A meal requires experienced detail")
                provision_source = event.payload.get("provision_source")
                provision_id = event.payload.get("provision_object_id")
                if provision_source not in {"household_stock", "cafe_service"}:
                    raise ValueError("A meal requires a known provision source")
                if provision_source == "household_stock" and provision_id != "household-provisions":
                    raise ValueError("A household meal requires provision evidence")
                if provision_source == "cafe_service" and provision_id is not None:
                    raise ValueError("A cafe meal cannot claim household stock")
                if location_id != self.location_id:
                    raise ValueError("A meal must occur at Pathos's current location")
                if not isinstance(simulated_at, str):
                    raise ValueError("A meal requires simulation time")
                meal_at = datetime.fromisoformat(simulated_at)
                if meal_at.utcoffset() is None or meal_at != self.simulated_at:
                    raise ValueError("A meal must occur at the current aware simulation time")
                before = _bounded_dimension(
                    event.payload.get("hunger_before"), "hunger_before", 0, 1
                )
                hunger = _bounded_dimension(event.payload.get("hunger_after"), "hunger_after", 0, 1)
                energy = _bounded_dimension(event.payload.get("energy_after"), "energy_after", 0, 1)
                if abs(before - self.hunger) > 1e-9:
                    raise ValueError("Meal hunger evidence does not match current state")
                if hunger >= before:
                    raise ValueError("A meal must reduce hunger")
                if before - hunger > 0.46 + 1e-9:
                    raise ValueError("A meal cannot erase excessive hunger")
                if energy < self.energy:
                    raise ValueError("A meal cannot directly reduce energy")
                if energy - self.energy > 0.07 + 1e-9:
                    raise ValueError("A meal cannot restore excessive energy")
                return replace(self, hunger=hunger, energy=energy)
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


_STATE_FOLD: IncrementalFold[PathosState] = IncrementalFold(
    PathosState, lambda state, event: state.apply(event), capacity=8
)


def replay_state(events: Sequence[DomainEvent]) -> PathosState:
    """Pathos's state after ``events``, resuming from any identical folded prefix."""
    return _STATE_FOLD(events)
