"""Derive bounded development events from authoritative repeated behavior."""

from typing import Sequence

from eidos.domain.events import DomainEvent


def development_events(history: Sequence[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    processed = {
        str(event.payload["source_event_id"])
        for event in history
        if event.kind in {"skill.practiced", "habit.reinforced"}
    }
    output: list[DomainEvent] = []
    for source in history:
        source_id = str(source.event_id)
        if source_id in processed:
            continue
        if source.kind == "action.accepted" and source.payload.get("action") == "repair":
            output.append(
                DomainEvent(
                    "skill.practiced",
                    "pathos",
                    {
                        "skill_id": "repair",
                        "delta": 0.05,
                        "source_event_id": source_id,
                        "owner": "pathos",
                        "simulated_at": simulated_at,
                    },
                    causation_id=source.event_id,
                    correlation_id=source.correlation_id,
                )
            )
            processed.add(source_id)
        elif (
            source.kind == "activity.completed"
            and source.payload.get("activity") == "learn"
            and source.payload.get("target_id") == "bookbinding-basics"
        ):
            output.append(
                DomainEvent(
                    "skill.practiced",
                    "pathos",
                    {
                        "skill_id": "bookbinding",
                        "delta": 0.05,
                        "source_event_id": source_id,
                        "owner": "pathos",
                        "simulated_at": simulated_at,
                    },
                    causation_id=source.event_id,
                    correlation_id=source.correlation_id,
                )
            )
            processed.add(source_id)
    cafe_visits = [
        event
        for event in history
        if event.kind == "memory.recorded"
        and event.payload.get("source") == "authored-routine"
        and event.payload.get("text") == "Visited the cafe before work."
    ]
    if len(cafe_visits) >= 3:
        source = cafe_visits[-1]
        source_id = str(source.event_id)
        if source_id not in processed:
            output.append(
                DomainEvent(
                    "habit.reinforced",
                    "pathos",
                    {
                        "habit_id": "morning-cafe-visit",
                        "delta": 0.025,
                        "source_event_id": source_id,
                        "owner": "pathos",
                        "simulated_at": simulated_at,
                    },
                    causation_id=source.event_id,
                    correlation_id="habit-morning-cafe-visit",
                )
            )
    return output
