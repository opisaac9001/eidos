"""Ingest attributed real-town reports as non-authoritative creative signals."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence
from urllib.parse import urlsplit

from eidos.domain.events import DomainEvent
from eidos.domain.folding import payload_candidates
from eidos.ports.town_signals import TownSignal, TownSignalSource

KINDS = {"weather", "daylight", "local_news"}


def town_signal_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    source: TownSignalSource | None,
) -> list[DomainEvent]:
    """Poll once each simulated morning; failure never changes fictional world state."""
    if source is None or simulated_at.hour != 6:
        return []
    poll_id = f"town-signals-{simulated_at.date().isoformat()}"
    if any(
        event.payload.get("poll_id") == poll_id
        for event in payload_candidates(history, "poll_id", poll_id)
    ):
        return []
    requested = DomainEvent(
        "external_signal.poll_requested",
        "pathos",
        {"poll_id": poll_id, "simulated_at": simulated_at.isoformat()},
        correlation_id=poll_id,
    )
    try:
        signals = list(source.read())
        for signal in signals:
            _validate(signal)
    except Exception as error:
        return [
            requested,
            DomainEvent(
                "external_signal.poll_failed",
                "pathos",
                {
                    "poll_id": poll_id,
                    "reason": str(error)[:300],
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=requested.event_id,
                correlation_id=poll_id,
            ),
        ]
    existing = {
        str(event.payload["signal_id"])
        for event in history
        if event.kind == "external_signal.observed"
    }
    output = [requested]
    for signal in signals:
        if signal.signal_id in existing:
            continue
        observed = DomainEvent(
            "external_signal.observed",
            "pathos",
            {
                "poll_id": poll_id,
                "signal_id": signal.signal_id,
                "signal_kind": signal.kind,
                "town": signal.town,
                "title": signal.title,
                "summary": signal.summary,
                "external_observed_at": signal.observed_at.isoformat(),
                "source_name": signal.source_name,
                "source_url": signal.source_url,
                "world_fact": False,
                "action_authority": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=requested.event_id,
            correlation_id=poll_id,
        )
        inspiration = DomainEvent(
            "world.signal_inspiration",
            "pathos",
            {
                "signal_id": signal.signal_id,
                "signal_kind": signal.kind,
                "town": signal.town,
                "text": f"{signal.title}: {signal.summary}",
                "source_name": signal.source_name,
                "source_url": signal.source_url,
                "expires_at": (
                    simulated_at + timedelta(hours=72 if signal.kind == "local_news" else 24)
                ).isoformat(),
                "world_fact": False,
                "action_authority": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=observed.event_id,
            correlation_id=poll_id,
        )
        output.extend((observed, inspiration))
        existing.add(signal.signal_id)
    return output


def active_town_signal_context(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> dict[str, str]:
    return {
        str(event.payload["signal_id"]): str(event.payload["text"])
        for event in history
        if event.kind == "world.signal_inspiration"
        and datetime.fromisoformat(str(event.payload["expires_at"])) > simulated_at
    }


def _validate(signal: TownSignal) -> None:
    if signal.kind not in KINDS:
        raise ValueError("Town signal kind is unsupported")
    if signal.observed_at.utcoffset() is None:
        raise ValueError("Town signal time must be timezone-aware")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            signal.signal_id,
            signal.town,
            signal.title,
            signal.summary,
            signal.source_name,
            signal.source_url,
        )
    ):
        raise ValueError("Town signal text fields must be non-empty")
    parsed = urlsplit(signal.source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Town signal attribution URL must be credential-free HTTPS")
