"""Choose whether a paused user conversation can genuinely resume."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.scenes import (
    SceneEndProposal,
    SceneEndReason,
    SceneResumeProposal,
    project_scenes,
    resolve_scene_end,
    resolve_scene_resume,
)


def recover_user_scene(
    history: Sequence[DomainEvent],
    scene_id: str,
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
    source_event: DomainEvent,
    decision_key: str,
) -> list[DomainEvent]:
    """Resume a paused visit only when presence, time, energy, and inclination allow it."""
    scene = project_scenes(history).scenes.get(scene_id)
    if scene is None or scene.status != "paused":
        return []
    planning = project_planning(history)
    upcoming = min(
        (
            entry
            for entry in planning.calendar.values()
            if entry.status == "scheduled"
            and datetime.fromisoformat(entry.starts_at) > simulated_at
        ),
        key=lambda entry: datetime.fromisoformat(entry.starts_at),
        default=None,
    )
    minutes_until = (
        (datetime.fromisoformat(upcoming.starts_at) - simulated_at).total_seconds() / 60
        if upcoming is not None
        else None
    )
    co_present = (
        actor_locations.get("pathos") == scene.location_id
        and actor_locations.get("user") == scene.location_id
    )
    resume_score = max(0.05, min(0.95, 0.42 + 0.5 * pathos_energy))
    if minutes_until is not None and minutes_until <= 120:
        resume_score -= 0.3
    if not co_present:
        decision, reason = "end", "One of you was no longer present after the interruption."
    elif pathos_energy < 0.22:
        decision, reason = "end", "The interruption used the energy Pathos had left."
    elif minutes_until is not None and minutes_until <= 60:
        decision, reason = "end", "Pathos had to prepare for his next commitment."
    elif _sample(decision_key) >= max(0.05, resume_score):
        decision, reason = "end", "Pathos could not settle back into the conversation."
    else:
        decision, reason = "resume", "Pathos still had time and attention to come back."
    decided = DomainEvent(
        "scene.resumption_decided",
        "pathos",
        {
            "scene_id": scene_id,
            "decision": decision,
            "reason": reason,
            "decision_energy": pathos_energy,
            "decision_co_present": co_present,
            "upcoming_schedule_id": upcoming.schedule_id if upcoming else None,
            "minutes_until_schedule": minutes_until,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=source_event.event_id,
        correlation_id=scene_id,
    )
    output = [decided]
    if decision == "resume":
        resolution = resolve_scene_resume(
            SceneResumeProposal(
                f"resume-after-{decision_key}",
                scene_id,
                "pathos",
                actual_revision + 1,
            ),
            state=project_scenes([*history, decided]),
            actor_locations=actor_locations,
            actual_revision=actual_revision + 1,
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(resolution.events)
        text = "Pathos came back and the conversation continued."
    else:
        resolution = resolve_scene_end(
            SceneEndProposal(
                f"end-after-{decision_key}",
                scene_id,
                "pathos",
                SceneEndReason.INTERRUPTED if co_present else SceneEndReason.LEFT,
                actual_revision + 1,
                decided.event_id,
            ),
            state=project_scenes([*history, decided]),
            history=[*history, decided],
            actual_revision=actual_revision + 1,
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(resolution.events)
        text = f"Pathos could not return to the conversation: {reason}"
    if resolution.accepted:
        output.append(
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "system",
                    "text": text,
                    "channel": "live_visit",
                    "scene_id": scene_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=resolution.events[-1].event_id,
                correlation_id=scene_id,
            )
        )
    return output


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
