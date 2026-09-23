"""Small, explicit work processes; prose cannot create inventory or accomplishments.

Stages describe eligible effort, not a guarantee of success. Final action validation
still owns repair results, promises and goal completion. Existing histories without
an execution start are never upgraded into work that supposedly happened.
"""

from datetime import datetime
from typing import Sequence

from eidos.domain.domestic_effort import washed_load
from eidos.domain.events import DomainEvent
from eidos.domain.household import project_household
from eidos.domain.planning import CalendarEntry


def stage_profile(entry: CalendarEntry) -> tuple[tuple[str, str, float], ...]:
    if (
        entry.action == "work"
        and entry.activity_type == "household_dishes"
        and entry.location_id == "home"
    ):
        return (
            ("gather", "Gather the dishes", 0.1),
            ("wash", "Wash the dishes", 0.75),
            ("put_away", "Put things away", 0.15),
        )
    if entry.action == "repair":
        return (
            ("inspect", "Inspect the problem", 0.2),
            ("repair", "Work on the repair", 0.65),
            ("check", "Check the work", 0.15),
        )
    if entry.action == "learn":
        return (("study", "Study or practise", 0.8), ("review", "Review what stuck", 0.2))
    if entry.action == "work":
        return (
            ("prepare", "Get set up", 0.1),
            ("focus", "Work on the task", 0.75),
            ("finish", "Bring this session to a stopping point", 0.15),
        )
    return (("participate", "Take part", 1.0),)


def stage_context(entry: CalendarEntry, effort: dict[str, object]) -> list[dict[str, object]]:
    required = float(str(effort["required_seconds"]))
    worked = float(str(effort["worked_seconds"]))
    cursor = 0.0
    output = []
    for key, label, fraction in stage_profile(entry):
        duration = required * fraction
        completed = required > 0 and worked + 0.001 >= cursor + duration
        output.append(
            {
                "stage_id": key,
                "label": label,
                "required_seconds": duration,
                "worked_seconds": max(0.0, min(duration, worked - cursor)),
                "status": "completed" if completed else "active" if worked > cursor else "pending",
                "threshold_seconds": cursor + duration,
            }
        )
        cursor += duration
    return output


def stage_events(
    history: Sequence[DomainEvent], entry: CalendarEntry, effort: dict[str, object], now: datetime
) -> list[DomainEvent]:
    starts = [
        e
        for e in history
        if e.kind == "activity.execution_started"
        and e.payload.get("schedule_id") == entry.schedule_id
    ]
    if not starts or not starts[0].payload.get("staged_execution"):
        return []
    done = {
        e.payload.get("stage_id")
        for e in history
        if e.kind == "activity.stage_completed"
        and e.payload.get("schedule_id") == entry.schedule_id
    }
    output = []
    for stage in stage_context(entry, effort):
        if stage["status"] != "completed" or stage["stage_id"] in done:
            continue
        source = DomainEvent(
            "activity.stage_completed",
            "pathos",
            {
                **stage,
                "schedule_id": entry.schedule_id,
                "activity_type": entry.activity_type,
                "action": entry.action,
                "location_id": entry.location_id,
                "worked_seconds": effort["worked_seconds"],
                "source_execution_id": str(starts[0].event_id),
                "simulated_at": now.isoformat(),
                "action_authority": False,
            },
            causation_id=starts[0].event_id,
            correlation_id=entry.schedule_id,
        )
        output.append(source)
        # Washing has a consequence even if putting everything away is interrupted.
        # The exact recipe, not an LLM title, authorizes this narrow household effect.
        if (
            entry.action == "work"
            and entry.activity_type == "household_dishes"
            and entry.location_id == "home"
            and stage["stage_id"] == "wash"
        ):
            household = project_household([*history, *output])
            amount = min(
                washed_load(float(str(stage["worked_seconds"]))), household.loads["dishes"]
            )
            if household.established and amount > 0:
                output.append(
                    DomainEvent(
                        "household.task_completed",
                        "pathos",
                        {
                            "task_id": f"activity:{entry.schedule_id}:wash",
                            "task_kind": "dishes",
                            "from_load": household.loads["dishes"],
                            "amount": amount,
                            "load": household.loads["dishes"] - amount,
                            "location_id": "home",
                            "text": "Washed a batch of dishes; more may remain, and putting things away is separate.",
                            "simulated_at": now.isoformat(),
                        },
                        causation_id=source.event_id,
                        correlation_id=entry.schedule_id,
                    )
                )
    return output
