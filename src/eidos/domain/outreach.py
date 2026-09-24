"""Opt-in, in-app-only outreach configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of


@dataclass(frozen=True, slots=True)
class OutreachConfig:
    enabled: bool = False
    quiet_start_hour: int = 22
    quiet_end_hour: int = 8
    minimum_interval_hours: int = 0


def project_outreach_config(history: Sequence[DomainEvent]) -> OutreachConfig:
    config = OutreachConfig()
    for event in events_of(history, "outreach.configured"):
        enabled = event.payload.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Outreach enabled must be true or false")
        if (
            event.payload.get("quiet_start_hour") != config.quiet_start_hour
            or event.payload.get("quiet_end_hour") != config.quiet_end_hour
            # Replay legacy 72-hour settings without retaining the retired cooldown.
            or event.payload.get("minimum_interval_hours") not in {0, 72}
        ):
            raise ValueError("Outreach safety limits cannot be changed by an event")
        config = OutreachConfig(enabled=enabled)
    return config
