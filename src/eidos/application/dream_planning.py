"""Allow dream-sourced possibilities to influence, but never authorize, ordinary plans."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from eidos.application.inner_life import active_dream_inspirations
from eidos.domain.events import DomainEvent


def dream_planning_workspace(
    history: Sequence[DomainEvent],
    workspace: Sequence[Mapping[str, object]],
    simulated_at: datetime,
) -> list[Mapping[str, object]]:
    """Rate-limit dream influence on agency while leaving other cognition untouched."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream planning time must be timezone-aware")
    recent_link = any(
        event.kind == "dream.inspiration_plan_linked" and _within(event, simulated_at, days=14)
        for event in history
    )
    if not recent_link:
        return list(workspace)
    return [item for item in workspace if item.get("kind") != "dream_inspiration"]


def dream_plan_link_events(
    history: Sequence[DomainEvent],
    workspace: Sequence[Mapping[str, object]],
    plan_events: Sequence[DomainEvent],
    simulated_at: datetime,
) -> list[DomainEvent]:
    """Link an aligned, independently accepted plan to one active dream possibility."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream planning time must be timezone-aware")
    accepted = next(
        (event for event in plan_events if event.kind == "agency.activity_accepted"), None
    )
    proposed = next(
        (event for event in plan_events if event.kind == "agency.activity_proposed"), None
    )
    schedule = next((event for event in plan_events if event.kind == "schedule.created"), None)
    if accepted is None or proposed is None or schedule is None:
        return []
    inspiration_item = next(
        (
            item
            for item in workspace
            if item.get("kind") == "dream_inspiration"
            and item.get("epistemic_status") == "fiction_sourced_possibility"
            and item.get("action_authority") is False
            and isinstance(item.get("source_event_id"), str)
        ),
        None,
    )
    if inspiration_item is None:
        return []
    inspiration = _event_by_id(history, str(inspiration_item["source_event_id"]))
    if inspiration is None or inspiration.kind != "dream.inspiration_considered":
        return []
    source_dream_id = inspiration.payload.get("source_dream_id")
    motif = inspiration.payload.get("motif")
    if not isinstance(source_dream_id, str) or not isinstance(motif, str):
        return []
    if source_dream_id not in {
        item.source_dream_id for item in active_dream_inspirations(history, simulated_at)
    }:
        return []
    if any(
        event.kind == "dream.inspiration_plan_linked"
        and event.payload.get("source_inspiration_event_id") == str(inspiration.event_id)
        for event in history
    ):
        return []
    if not _matches_motif(motif, proposed):
        return []
    return [
        DomainEvent(
            "dream.inspiration_plan_linked",
            "pathos",
            {
                "source_dream_id": source_dream_id,
                "source_inspiration_event_id": str(inspiration.event_id),
                "accepted_plan_event_id": str(accepted.event_id),
                "schedule_id": schedule.payload["schedule_id"],
                "activity_type": proposed.payload["activity_type"],
                "motif": motif,
                "text": (
                    "A temporary possibility left by a dream resembled an ordinary activity "
                    "Pathos independently chose and passed through normal planning."
                ),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id=schedule.correlation_id,
        )
    ]


def dream_plan_outcome_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Close linked inspiration only when the ordinary plan succeeds or fails."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream plan outcome time must be timezone-aware")
    terminal_link_ids = {
        str(event.payload["source_plan_link_id"])
        for event in history
        if event.kind in {"dream.inspiration_plan_realized", "dream.inspiration_plan_failed"}
        and isinstance(event.payload.get("source_plan_link_id"), str)
    }
    dismissed_dream_ids = {
        str(event.payload["source_dream_id"])
        for event in history
        if event.kind == "dream.inspiration_dismissed"
        and isinstance(event.payload.get("source_dream_id"), str)
    }
    output: list[DomainEvent] = []
    for link in history:
        link_id = str(link.event_id)
        if link.kind != "dream.inspiration_plan_linked" or link_id in terminal_link_ids:
            continue
        schedule_id = link.payload.get("schedule_id")
        outcome = next(
            (
                event
                for event in history
                if event.kind in {"agency.activity_realized", "agency.activity_missed"}
                and event.payload.get("schedule_id") == schedule_id
            ),
            None,
        )
        if outcome is None:
            continue
        realized = outcome.kind == "agency.activity_realized"
        terminal = DomainEvent(
            "dream.inspiration_plan_realized" if realized else "dream.inspiration_plan_failed",
            "pathos",
            {
                "source_plan_link_id": link_id,
                "source_inspiration_event_id": link.payload["source_inspiration_event_id"],
                "source_dream_id": link.payload["source_dream_id"],
                "schedule_id": schedule_id,
                "outcome_event_id": str(outcome.event_id),
                "text": (
                    "The ordinary activity happened; the dream remains only its fictional origin."
                    if realized
                    else "The ordinary plan failed; the dream possibility did not bypass reality."
                ),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=outcome.event_id,
            correlation_id=link.correlation_id,
        )
        output.append(terminal)
        source_dream_id = str(link.payload["source_dream_id"])
        if source_dream_id not in dismissed_dream_ids:
            output.append(
                DomainEvent(
                    "dream.inspiration_dismissed",
                    "pathos",
                    {
                        "source_dream_id": source_dream_id,
                        "source_plan_link_id": link_id,
                        "reason": "The dream-linked possibility reached an ordinary plan outcome.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=terminal.event_id,
                    correlation_id=link.correlation_id,
                )
            )
            dismissed_dream_ids.add(source_dream_id)
    return output


def _matches_motif(motif: str, proposal: DomainEvent) -> bool:
    text = " ".join(
        str(proposal.payload.get(field, ""))
        for field in ("activity_type", "title", "motivation", "location_id", "companion_id")
    ).casefold()
    cues = {
        "light": ("light", "observe", "observation", "sketch", "texture"),
        "mending": ("repair", "mend", "practice", "joint", "worn object"),
        "growth": ("outdoor", "park", "garden", "walk", "street texture"),
        "companionship": ("shared", "someone", "conversation", "together", "companion"),
        "unfinished_time": ("quiet", "notes", "write", "observation", "unscheduled"),
    }.get(motif, ())
    companion = proposal.payload.get("companion_id")
    return (motif == "companionship" and isinstance(companion, str)) or any(
        cue in text for cue in cues
    )


def _event_by_id(history: Sequence[DomainEvent], event_id: str) -> DomainEvent | None:
    return next((event for event in history if str(event.event_id) == event_id), None)


def _within(event: DomainEvent, simulated_at: datetime, *, days: int) -> bool:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        return False
    try:
        event_at = datetime.fromisoformat(value)
    except ValueError:
        return False
    return event_at.utcoffset() is not None and 0 <= (simulated_at - event_at).total_seconds() < (
        days * 86_400
    )
