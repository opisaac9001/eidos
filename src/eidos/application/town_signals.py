"""Ingest attributed real-town reports as non-authoritative creative signals."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence
from urllib.parse import urlsplit

from eidos.application.causal_opportunities import instant, timeline_fold
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, payload_candidates
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
        str(event.payload["signal_id"]) for event in events_of(history, "external_signal.observed")
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


def _expiry_key(event: DomainEvent) -> timedelta:
    # Anything not certainly an aware expiry sorts above every bound, so it is still read.
    try:
        expires = datetime.fromisoformat(str(event.payload["expires_at"]))
    except Exception:
        return timedelta.max
    return timedelta.max if expires.utcoffset() is None else instant(expires)


_INSPIRATIONS = timeline_fold("world.signal_inspiration", _expiry_key)


def active_town_signal_context(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> dict[str, str]:
    if simulated_at.utcoffset() is None:
        inspirations = events_of(history, "world.signal_inspiration")
    else:
        # Stop where every earlier inspiration has already expired.
        unexpired = instant(simulated_at) + timedelta(microseconds=1)
        inspirations = [event for _, event in _INSPIRATIONS(history).newest_from(unexpired)][::-1]
    return {
        str(event.payload["signal_id"]): str(event.payload["text"])
        for event in inspirations
        if datetime.fromisoformat(str(event.payload["expires_at"])) > simulated_at
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


# WMO weather codes, as the four kinds of weather the world knows.
_WEATHER_CODES = (
    (range(0, 2), "Clear"),
    (range(2, 4), "Cloudy"),
    (range(45, 49), "Cloudy"),
    (range(51, 68), "Light rain"),
    (range(71, 78), "Cloudy"),
    (range(80, 83), "Light rain"),
    (range(85, 87), "Cloudy"),
    (range(95, 100), "Light rain"),
)
_CODE = re.compile(r"Weather code (\d+)")
_WIND_AFTER = 12.0  # fall back to "Breezy" for an unknown code


def real_weather(
    history: Sequence[DomainEvent], at: datetime, now: datetime, *, live: bool = False
) -> str | None:
    """Today's real weather where the town is, if his world runs live or his day is today."""
    if not live and abs(at - now) > timedelta(days=1):
        return None
    for event in reversed(events_of(history, "external_signal.observed")[-20:]):
        if event.payload.get("signal_kind") != "weather":
            continue
        observed = datetime.fromisoformat(str(event.payload["external_observed_at"]))
        if abs(observed - now) > timedelta(hours=12):
            return None
        match = _CODE.search(str(event.payload.get("summary", "")))
        if match is None:
            return None
        code = int(match.group(1))
        return next((name for codes, name in _WEATHER_CODES if code in codes), "Breezy")
    return None
