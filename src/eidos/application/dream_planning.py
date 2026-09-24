"""Allow dream-sourced possibilities to influence, but never authorize, ordinary plans."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from eidos.application.inner_life import active_dream_inspirations
from eidos.domain.events import DomainEvent
from eidos.domain.folding import event_index, events_of

_LINK_KINDS = ("dream.inspiration_plan_linked", "dream.inspiration_project_linked")


def dream_planning_workspace(
    history: Sequence[DomainEvent],
    workspace: Sequence[Mapping[str, object]],
    simulated_at: datetime,
) -> list[Mapping[str, object]]:
    """Rate-limit dream influence on agency while leaving other cognition untouched."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream planning time must be timezone-aware")
    recent_link = any(
        _within(event, simulated_at, days=14) for event in events_of(history, *_LINK_KINDS)
    )
    if not recent_link:
        return list(workspace)
    return [item for item in workspace if item.get("kind") != "dream_inspiration"]


def dream_project_link_events(
    history: Sequence[DomainEvent],
    workspace: Sequence[Mapping[str, object]],
    project_events: Sequence[DomainEvent],
    simulated_at: datetime,
) -> list[DomainEvent]:
    """Link an aligned accepted multi-step project to one active dream possibility."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream project planning time must be timezone-aware")
    accepted = next(
        (event for event in project_events if event.kind == "self_project.accepted"), None
    )
    proposed = next(
        (event for event in project_events if event.kind == "self_project.proposed"), None
    )
    if accepted is None or proposed is None:
        return []
    inspiration = _active_workspace_inspiration(history, workspace, simulated_at)
    if inspiration is None:
        return []
    source_dream_id = inspiration.payload.get("source_dream_id")
    motif = inspiration.payload.get("motif")
    if not isinstance(source_dream_id, str) or not isinstance(motif, str):
        return []
    if _inspiration_already_linked(history, inspiration):
        return []
    related = [
        event
        for event in project_events
        if event.correlation_id == accepted.correlation_id
        and event.kind in {"self_project.proposed", "schedule.created"}
    ]
    if not _matches_motif(motif, *related):
        return []
    goal = next((event for event in project_events if event.kind == "goal.activated"), None)
    if goal is None:
        return []
    return [
        DomainEvent(
            "dream.inspiration_project_linked",
            "pathos",
            {
                "source_dream_id": source_dream_id,
                "source_inspiration_event_id": str(inspiration.event_id),
                "accepted_project_event_id": str(accepted.event_id),
                "proposal_id": accepted.payload["proposal_id"],
                "goal_id": goal.payload["goal_id"],
                "project_type": accepted.payload["project_type"],
                "motif": motif,
                "text": (
                    "A fictional dream possibility resembled a multi-step project Pathos "
                    "independently proposed and passed through ordinary planning."
                ),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id=accepted.correlation_id,
        )
    ]


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
    inspiration = _active_workspace_inspiration(history, workspace, simulated_at)
    if inspiration is None:
        return []
    source_dream_id = inspiration.payload.get("source_dream_id")
    motif = inspiration.payload.get("motif")
    if not isinstance(source_dream_id, str) or not isinstance(motif, str):
        return []
    if _inspiration_already_linked(history, inspiration):
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
        for event in events_of(
            history, "dream.inspiration_plan_realized", "dream.inspiration_plan_failed"
        )
        if isinstance(event.payload.get("source_plan_link_id"), str)
    }
    dismissed_dream_ids = _dismissed_dream_ids(history)
    output: list[DomainEvent] = []
    links = events_of(history, "dream.inspiration_plan_linked")
    outcomes = (
        events_of(history, "agency.activity_realized", "agency.activity_missed") if links else []
    )
    for link in links:
        link_id = str(link.event_id)
        if link_id in terminal_link_ids:
            continue
        schedule_id = link.payload.get("schedule_id")
        outcome = next(
            (event for event in outcomes if event.payload.get("schedule_id") == schedule_id),
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


def dream_project_outcome_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Close dream-project lineage only after the whole ordinary project resolves."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Dream project outcome time must be timezone-aware")
    terminal_link_ids = {
        str(event.payload["source_project_link_id"])
        for event in events_of(
            history, "dream.inspiration_project_realized", "dream.inspiration_project_failed"
        )
        if isinstance(event.payload.get("source_project_link_id"), str)
    }
    dismissed_dream_ids = _dismissed_dream_ids(history)
    output: list[DomainEvent] = []
    links = events_of(history, "dream.inspiration_project_linked")
    outcomes = events_of(history, "self_project.completed", "self_project.failed") if links else []
    for link in links:
        link_id = str(link.event_id)
        if link_id in terminal_link_ids:
            continue
        proposal_id = link.payload.get("proposal_id")
        outcome = next(
            (event for event in outcomes if event.payload.get("proposal_id") == proposal_id),
            None,
        )
        if outcome is None:
            continue
        realized = outcome.kind == "self_project.completed"
        terminal = DomainEvent(
            (
                "dream.inspiration_project_realized"
                if realized
                else "dream.inspiration_project_failed"
            ),
            "pathos",
            {
                "source_project_link_id": link_id,
                "source_inspiration_event_id": link.payload["source_inspiration_event_id"],
                "source_dream_id": link.payload["source_dream_id"],
                "proposal_id": proposal_id,
                "goal_id": link.payload["goal_id"],
                "outcome_event_id": str(outcome.event_id),
                "text": (
                    "The independently chosen project was completed; its dream origin remains fiction."
                    if realized
                    else "The independently chosen project failed; dream imagery did not guarantee reality."
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
                        "source_project_link_id": link_id,
                        "reason": "The dream-linked possibility reached a whole-project outcome.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=terminal.event_id,
                    correlation_id=link.correlation_id,
                )
            )
            dismissed_dream_ids.add(source_dream_id)
    return output


def _dismissed_dream_ids(history: Sequence[DomainEvent]) -> set[str]:
    return {
        str(event.payload["source_dream_id"])
        for event in events_of(history, "dream.inspiration_dismissed")
        if isinstance(event.payload.get("source_dream_id"), str)
    }


def _matches_motif(motif: str, *proposals: DomainEvent) -> bool:
    text = " ".join(
        str(proposal.payload.get(field, ""))
        for proposal in proposals
        for field in (
            "activity_type",
            "project_type",
            "title",
            "motivation",
            "location_id",
            "companion_id",
        )
    ).casefold()
    cues = {
        "light": ("light", "observe", "observation", "sketch", "texture"),
        "mending": ("repair", "mend", "practice", "joint", "worn object"),
        "growth": ("outdoor", "park", "garden", "walk", "street texture"),
        "companionship": ("shared", "someone", "conversation", "together", "companion"),
        "unfinished_time": ("quiet", "notes", "write", "observation", "unscheduled"),
    }.get(motif, ())
    companion = any(isinstance(proposal.payload.get("companion_id"), str) for proposal in proposals)
    return (motif == "companionship" and companion) or any(cue in text for cue in cues)


def _active_workspace_inspiration(
    history: Sequence[DomainEvent],
    workspace: Sequence[Mapping[str, object]],
    simulated_at: datetime,
) -> DomainEvent | None:
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
        return None
    inspiration = _event_by_id(history, str(inspiration_item["source_event_id"]))
    if inspiration is None or inspiration.kind != "dream.inspiration_considered":
        return None
    active_ids = {item.source_dream_id for item in active_dream_inspirations(history, simulated_at)}
    return inspiration if inspiration.payload.get("source_dream_id") in active_ids else None


def _inspiration_already_linked(history: Sequence[DomainEvent], inspiration: DomainEvent) -> bool:
    return any(
        event.payload.get("source_inspiration_event_id") == str(inspiration.event_id)
        for event in events_of(history, *_LINK_KINDS)
    )


def _event_by_id(history: Sequence[DomainEvent], event_id: str) -> DomainEvent | None:
    return event_index(history).get(event_id)


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
