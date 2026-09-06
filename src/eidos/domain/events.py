from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """An immutable fact accepted by the simulation.

    LLM responses are proposals until domain rules turn them into events.
    """

    kind: str
    aggregate_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("event kind must not be empty")
        if not self.aggregate_id.strip():
            raise ValueError("aggregate_id must not be empty")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        for key, value in self.payload.items():
            if not isinstance(key, str):
                raise ValueError("event payload keys must be strings")
            if value is not None and not isinstance(value, (str, bool, int, float, datetime)):
                raise ValueError("event payload values must be immutable scalars")
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("event payload numbers must be finite")
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError("event payload timestamps must be timezone-aware")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
