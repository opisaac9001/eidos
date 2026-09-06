"""External town-signal boundary; reports are observations, never world commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class TownSignal:
    signal_id: str
    kind: str
    town: str
    title: str
    summary: str
    observed_at: datetime
    source_name: str
    source_url: str


class TownSignalSource(Protocol):
    def read(self) -> Sequence[TownSignal]: ...
