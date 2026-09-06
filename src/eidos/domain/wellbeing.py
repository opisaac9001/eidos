"""Replayable, bounded, non-clinical physical wellbeing episodes."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent

_KINDS = {"headache", "sore_muscles", "under_the_weather", "poor_sleep_aftereffects"}


@dataclass(frozen=True, slots=True)
class WellbeingEpisode:
    episode_id: str
    kind: str
    severity: float
    started_at: str
    expected_end_at: str
    reason: str
    status: str = "active"
    last_changed_at: str | None = None


@dataclass(frozen=True, slots=True)
class WellbeingState:
    episodes: dict[str, WellbeingEpisode] = field(default_factory=dict)

    @property
    def active(self) -> WellbeingEpisode | None:
        return next(
            (episode for episode in reversed(self.episodes.values()) if episode.status == "active"),
            None,
        )

    def apply(self, event: DomainEvent) -> WellbeingState:
        episodes = dict(self.episodes)
        if event.kind == "wellbeing.episode_started":
            episode_id = _required(event, "episode_id")
            if episode_id in episodes or self.active is not None:
                raise ValueError("Only one new physical episode can be active")
            kind = _required(event, "condition_kind")
            if kind not in _KINDS:
                raise ValueError("Unknown physical condition kind")
            severity = _severity(event)
            started = _aware(event, "simulated_at")
            expected = _aware(event, "expected_end_at")
            if not timedelta(hours=24) <= expected - started <= timedelta(hours=72):
                raise ValueError("Physical episodes must resolve within one to three days")
            if event.payload.get("clinical_diagnosis") is not False:
                raise ValueError("Ordinary wellbeing episodes cannot claim a diagnosis")
            episodes[episode_id] = WellbeingEpisode(
                episode_id,
                kind,
                severity,
                started.isoformat(),
                expected.isoformat(),
                _required(event, "reason"),
                last_changed_at=started.isoformat(),
            )
        elif event.kind == "wellbeing.episode_progressed":
            episode = _active(episodes, event)
            severity = _severity(event)
            at = _aware(event, "simulated_at")
            if severity >= episode.severity:
                raise ValueError("A recovery update must reduce physical severity")
            if at <= datetime.fromisoformat(episode.last_changed_at or episode.started_at):
                raise ValueError("Physical recovery must move forward in time")
            episodes[episode.episode_id] = replace(
                episode, severity=severity, last_changed_at=at.isoformat()
            )
        elif event.kind == "wellbeing.episode_resolved":
            episode = _active(episodes, event)
            at = _aware(event, "simulated_at")
            if at < datetime.fromisoformat(episode.expected_end_at):
                raise ValueError("A physical episode cannot resolve before its recovery window")
            episodes[episode.episode_id] = replace(
                episode, status="resolved", severity=0.0, last_changed_at=at.isoformat()
            )
        return WellbeingState(episodes)


def project_wellbeing(events: Sequence[DomainEvent]) -> WellbeingState:
    state = WellbeingState()
    for event in events:
        state = state.apply(event)
    return state


def _active(episodes: dict[str, WellbeingEpisode], event: DomainEvent) -> WellbeingEpisode:
    episode_id = _required(event, "episode_id")
    episode = episodes.get(episode_id)
    if episode is None or episode.status != "active":
        raise ValueError("Physical recovery requires an active episode")
    return episode


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Wellbeing event requires {key}")
    return value


def _aware(event: DomainEvent, key: str) -> datetime:
    value = datetime.fromisoformat(_required(event, key))
    if value.utcoffset() is None:
        raise ValueError("Wellbeing time must be timezone-aware")
    return value


def _severity(event: DomainEvent) -> float:
    value = event.payload.get("severity")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.1 <= value <= 0.6:
        raise ValueError("Physical severity must be between 0.1 and 0.6")
    return float(value)
