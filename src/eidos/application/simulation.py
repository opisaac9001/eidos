from datetime import timedelta
from math import isfinite

from eidos.domain.events import DomainEvent
from eidos.domain.routine import beats_between
from eidos.domain.state import PathosState
from eidos.ports.event_store import EventStore


class Simulation:
    def __init__(self, store: EventStore) -> None:
        self.store = store

    def state(self) -> PathosState:
        state = PathosState()
        for event in self.store.read(state.pathos_id):
            state = state.apply(event)
        return state

    def advance(self, hours: float) -> PathosState:
        if isinstance(hours, bool) or not isfinite(hours) or not 0 < hours <= 168:
            raise ValueError("Advance must be greater than zero and at most 168 hours")
        history = self.store.read("pathos")
        state = PathosState()
        for event in history:
            state = state.apply(event)
        target = state.simulated_at + timedelta(hours=hours)
        if target <= state.simulated_at:
            raise ValueError("Advance is smaller than clock precision")
        proposed = []
        for at, beat in beats_between(state.simulated_at, target):
            proposed.extend([
                DomainEvent("time.advanced", "pathos", {"simulated_at": at}),
                DomainEvent("pathos.moved", "pathos", {"location_id": beat.location_id}),
                DomainEvent("affect.changed", "pathos", {"energy": beat.energy}),
                DomainEvent("memory.recorded", "pathos", {
                    "text": beat.description, "simulated_at": at.isoformat(),
                    "source": "authored-routine", "location_id": beat.location_id,
                }),
            ])
        proposed.append(DomainEvent("time.advanced", "pathos", {"simulated_at": target}))
        for event in proposed:
            state = state.apply(event)
        self.store.append("pathos", proposed, expected_revision=len(history))
        return state

    def journal(self) -> list[DomainEvent]:
        return [e for e in self.store.read("pathos") if e.kind == "memory.recorded"]
