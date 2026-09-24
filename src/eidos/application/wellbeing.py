"""Rare physical episodes and their grounded effect on an ordinary day."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.routine import RoutineBeat
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import WellbeingEpisode, project_wellbeing


def wellbeing_events(
    history: Sequence[DomainEvent], state: PathosState, at: datetime
) -> list[DomainEvent]:
    """Start rarely and recover monotonically at the morning wellbeing check."""
    if at.utcoffset() is None:
        raise ValueError("Wellbeing time must be timezone-aware")
    wellbeing = project_wellbeing(history)
    active = wellbeing.active
    if active is not None:
        expected = datetime.fromisoformat(active.expected_end_at)
        if at >= expected:
            return [
                DomainEvent(
                    "wellbeing.episode_resolved",
                    "pathos",
                    {
                        "episode_id": active.episode_id,
                        "condition_kind": active.kind,
                        "reason": "The temporary physical symptoms passed with time and rest.",
                        "simulated_at": at.isoformat(),
                    },
                    correlation_id=active.episode_id,
                )
            ]
        if (
            at.hour == 8
            and active.severity > 0.1
            and datetime.fromisoformat(active.last_changed_at or active.started_at).date()
            < at.date()
        ):
            return [
                DomainEvent(
                    "wellbeing.episode_progressed",
                    "pathos",
                    {
                        "episode_id": active.episode_id,
                        "condition_kind": active.kind,
                        "severity": max(0.1, active.severity - 0.15),
                        "reason": "The symptoms eased without disappearing all at once.",
                        "simulated_at": at.isoformat(),
                    },
                    correlation_id=active.episode_id,
                )
            ]
        return []
    if at.hour != 8 or not state.awake:
        return []
    latest = max(
        (
            datetime.fromisoformat(str(event.payload["simulated_at"]))
            for event in history
            if event.kind == "wellbeing.episode_started"
        ),
        default=None,
    )
    if latest is not None and at - latest < timedelta(days=14):
        return []
    sample = int.from_bytes(sha256(at.date().isoformat().encode()).digest()[:4], "big") / 0xFFFFFFFF
    risk = 0.035 + (0.12 if state.rest < 0.35 else 0.0) + (0.08 if state.hunger > 0.75 else 0.0)
    if sample >= risk:
        return []
    digest = sha256(f"wellbeing:{at.date().isoformat()}".encode()).digest()
    kinds = ("headache", "sore_muscles", "under_the_weather", "poor_sleep_aftereffects")
    kind = kinds[digest[0] % len(kinds)]
    if at.month in (11, 12, 1, 2) and digest[3] % 2 == 0:
        kind = "under_the_weather"  # In the dark months a spell is more often a cold.
    severity = (0.25, 0.35, 0.45, 0.55)[digest[1] % 4]
    duration_hours = (24, 48, 72)[digest[2] % 3]
    episode_id = f"wellbeing:{at.date().isoformat()}"
    return [
        DomainEvent(
            "wellbeing.episode_started",
            "pathos",
            {
                "episode_id": episode_id,
                "condition_kind": kind,
                "severity": severity,
                "expected_end_at": (at + timedelta(hours=duration_hours)).isoformat(),
                "reason": (
                    "Ordinary symptoms surfaced while physical reserves were low."
                    if state.rest < 0.35 or state.hunger > 0.75
                    else "An ordinary, unexplained spell of physical discomfort surfaced."
                ),
                "simulated_at": at.isoformat(),
                "clinical_diagnosis": False,
            },
            correlation_id=episode_id,
        )
    ]


def physically_adjusted_beat(
    beat: RoutineBeat,
    episode: WellbeingEpisode | None,
    *,
    planned: bool,
    protected: bool,
) -> tuple[RoutineBeat, str | None]:
    """Bend ordinary activity while leaving emergencies and mild symptoms intact."""
    if episode is None or protected or episode.severity < 0.3:
        return beat, None
    must_stop = episode.severity >= 0.48
    optional = not planned and beat.activity not in {"work", "repair", "incident_response"}
    if not must_stop and not optional:
        return beat, None
    description = (
        "Stayed home and let a difficult physical spell interrupt the planned activity."
        if planned
        else "Kept the hour quiet at home while temporary physical discomfort passed."
    )
    return (
        RoutineBeat(
            beat.hour,
            "home",
            description,
            min(beat.energy, max(0.3, 0.7 - episode.severity)),
            "physical_recovery",
        ),
        f"{episode.kind.replace('_', ' ')} reduced physical capacity",
    )
