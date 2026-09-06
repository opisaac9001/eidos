"""A restart-safe first self-directed project completed through real activity."""

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import PlanningState, project_planning

GOAL_ID = "bind-pocket-notebook"
TARGET_ID = "bookbinding-basics"


def personal_project_events(
    current: datetime,
    existing: Sequence[DomainEvent],
    actor_location_id: str,
) -> list[DomainEvent]:
    """Start and advance one modest project from deterministic evidence."""

    history = list(existing)
    planning = project_planning(history)
    day = (current.date() - datetime(2026, 1, 1).date()).days + 1
    if day == 1 and current.hour == 7 and GOAL_ID not in planning.goals:
        return _start_project(current, history, planning)
    if day not in {3, 5} or current.hour != 16:
        return []

    session = 1 if day == 3 else 2
    schedule_id = f"bind-pocket-notebook-session-{session}"
    intention_id = f"{schedule_id}-intention"
    schedule = planning.calendar.get(schedule_id)
    intention = planning.intentions.get(intention_id)
    if (
        schedule is None
        or intention is None
        or schedule.status != "scheduled"
        or intention.status != "active"
    ):
        return []
    resolution = resolve_action(
        ActionProposal(
            proposal_id=f"complete-{schedule_id}",
            actor_id="pathos",
            action=ActionKind.LEARN,
            target_id=TARGET_ID,
            schedule_id=schedule_id,
            intention_id=intention_id,
            expected_revision=len(history),
        ),
        state=planning,
        actor_location_id=actor_location_id,
        actual_revision=len(history),
        simulated_at=current,
    )
    if not resolution.accepted:
        return list(resolution.events)
    activity = next(event for event in resolution.events if event.kind == "activity.completed")
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": (
                "I practiced folding, stitching, and fitting a cover for a pocket notebook."
                if session == 1
                else "I finished binding a small pocket notebook after two focused sessions."
            ),
            "simulated_at": current.isoformat(),
            "source": "authored-personal-project",
            "source_event_id": str(activity.event_id),
            "category": "personal-project",
            "location_id": actor_location_id,
            "goal_id": GOAL_ID,
            "owner": "pathos",
            "importance": 0.65 if session == 1 else 0.8,
            "confidence": 1.0,
        },
        causation_id=activity.event_id,
        correlation_id=GOAL_ID,
    )
    return [*resolution.events, memory]


def _start_project(
    current: datetime, history: list[DomainEvent], planning: PlanningState
) -> list[DomainEvent]:
    correlation = GOAL_ID
    sessions = (
        (1, (current + timedelta(days=2)).replace(hour=14), 2),
        (2, (current + timedelta(days=4)).replace(hour=14), 2),
    )
    base = [
        DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": GOAL_ID,
                "title": "Learn to bind a pocket notebook",
                "motivation": "Make something useful by hand and become more capable.",
                "simulated_at": current.isoformat(),
            },
            correlation_id=correlation,
        )
    ]
    for session, starts_at, duration in sessions:
        base.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": f"bind-pocket-notebook-session-{session}",
                    "title": f"Bookbinding practice {session}",
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=duration)).isoformat(),
                    "location_id": "workshop",
                    "actor_id": "pathos",
                    "action": ActionKind.LEARN.value,
                    "target_id": TARGET_ID,
                    "goal_id": GOAL_ID,
                    "simulated_at": current.isoformat(),
                },
                correlation_id=correlation,
            )
        )
    projected = planning
    for event in base:
        projected = projected.apply(event)
    events = list(base)
    for session, _, _ in sessions:
        intention = resolve_intention(
            IntentionProposal(
                proposal_id=f"intend-bind-pocket-notebook-session-{session}",
                intention_id=f"bind-pocket-notebook-session-{session}-intention",
                actor_id="pathos",
                action=ActionKind.LEARN,
                motivation="Practice bookbinding to complete a self-chosen useful object.",
                priority=0.65,
                expected_revision=len(history) + len(events),
                goal_id=GOAL_ID,
                target_id=TARGET_ID,
            ),
            state=projected,
            actual_revision=len(history) + len(events),
            simulated_at=current,
        )
        events.extend(intention.events)
        for event in intention.events:
            projected = projected.apply(event)
    return events
