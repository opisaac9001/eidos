"""Persistence boundary. Append is atomic and checks the caller's revision."""

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from eidos.domain.events import DomainEvent


class RevisionConflict(Exception):
    """Another writer changed the stream; reload before proposing more events."""


@dataclass(frozen=True, slots=True)
class EventRecord:
    revision: int
    event: DomainEvent


@dataclass(frozen=True, slots=True)
class EventPage:
    records: tuple[EventRecord, ...]
    next_before_revision: int | None


@dataclass(frozen=True, slots=True)
class StateCheckpoint:
    aggregate_id: str
    revision: int
    last_event_id: str
    state: Mapping[str, Any]


@runtime_checkable
class StateCheckpointStore(Protocol):
    def load_checkpoint(self, aggregate_id: str, max_revision: int) -> StateCheckpoint | None: ...

    def save_checkpoint(self, checkpoint: StateCheckpoint) -> None: ...


class EventStore(Protocol):
    def read(self, aggregate_id: str) -> list[DomainEvent]: ...

    def read_page(
        self, aggregate_id: str, *, before_revision: int | None = None, limit: int = 100
    ) -> EventPage: ...

    def append(
        self, aggregate_id: str, events: Sequence[DomainEvent], expected_revision: int
    ) -> None: ...
