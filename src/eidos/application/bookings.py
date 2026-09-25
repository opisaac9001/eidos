"""Putting an agreed plan on his calendar.

Every booking must be caused by the decision or agreement that made it (a plan agreed with
a friend, a ticket bought, a promise made). This builds the intention and the calendar
entry for one such plan, citing it, in the shape the planner and executor expect.
"""

from __future__ import annotations

from datetime import datetime

from eidos.domain.events import DomainEvent


def book(
    cause: DomainEvent,
    *,
    schedule_id: str,
    title: str,
    starts: datetime,
    ends: datetime,
    place_id: str,
    activity_type: str,
    source: str,
    motivation: str,
    at: datetime,
    companion_id: str | None = None,
    priority: float = 0.85,
) -> list[DomainEvent]:
    """[intention.adopted, schedule.created] for a plan ``cause`` decided."""
    intention_id = f"{schedule_id}-intention"
    return [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place_id,
                "goal_id": None,
                "priority": priority,
                "motivation": motivation,
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id,
            correlation_id=schedule_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": title,
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "location_id": place_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place_id,
                "resource_id": None,
                "companion_id": companion_id,
                "activity_type": activity_type,
                "source": source,
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id,
            correlation_id=schedule_id,
        ),
    ]


def remember(
    source: DomainEvent,
    text: str,
    at: datetime,
    importance: float,
    *,
    origin: str,
    category: str = "relationship",
    person_id: str | None = None,
    location_id: str | None = None,
) -> DomainEvent:
    """A memory of ``source``, in his words."""
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": category,
            "source": origin,
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **({"person_id": person_id} if person_id else {}),
            **({"location_id": location_id} if location_id else {}),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )
