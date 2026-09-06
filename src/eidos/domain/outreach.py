"""Opt-in, in-app-only outreach configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class OutreachConfig:
    enabled: bool = False
    quiet_start_hour: int = 22
    quiet_end_hour: int = 8
    minimum_interval_hours: int = 72


def project_outreach_config(history: Sequence[DomainEvent]) -> OutreachConfig:
    config = OutreachConfig()
    for event in history:
        if event.kind != "outreach.configured":
            continue
        enabled = event.payload.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Outreach enabled must be true or false")
        if (
            event.payload.get("quiet_start_hour") != config.quiet_start_hour
            or event.payload.get("quiet_end_hour") != config.quiet_end_hour
            or event.payload.get("minimum_interval_hours") != config.minimum_interval_hours
        ):
            raise ValueError("Outreach safety limits cannot be changed by an event")
        config = OutreachConfig(enabled=enabled)
    return config
