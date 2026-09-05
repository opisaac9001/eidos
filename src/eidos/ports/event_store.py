"""Persistence boundary. Append is atomic and checks the caller's revision."""

from typing import Protocol, Sequence

from eidos.domain.events import DomainEvent


class RevisionConflict(Exception):
    """Another writer changed the stream; reload before proposing more events."""


class EventStore(Protocol):
    def read(self, aggregate_id: str) -> list[DomainEvent]: ...

    def append(
        self, aggregate_id: str, events: Sequence[DomainEvent], expected_revision: int
    ) -> None: ...
