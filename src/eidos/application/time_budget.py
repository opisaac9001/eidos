"""Describe room around accepted commitments without prescribing a routine."""

from datetime import datetime

from eidos.domain.planning import PlanningState
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import WorldCatalog


def personal_time_budget(
    planning: PlanningState, catalog: WorldCatalog, now: datetime, location_id: str
) -> dict[str, object]:
    if now.utcoffset() is None:
        raise ValueError("Time budgets require timezone-aware time")
    entries = sorted(
        (
            e
            for e in planning.calendar.values()
            if e.actor_id in {None, "pathos"}
            and e.status == "scheduled"
            and datetime.fromisoformat(e.ends_at or e.starts_at) > now
        ),
        key=lambda e: datetime.fromisoformat(e.starts_at),
    )
    if not entries:
        return {"next_plan": None, "free_minutes": None, "action_authority": False}
    entry = entries[0]
    minutes = (datetime.fromisoformat(entry.starts_at) - now).total_seconds() / 60
    try:
        travel = (
            route_duration(location_id, entry.location_id, catalog.route_minutes).total_seconds()
            / 60
        )
    except ValueError:
        travel = None
    return {
        "next_plan": entry.title,
        "schedule_id": entry.schedule_id,
        "starts_at": entry.starts_at,
        "location_id": entry.location_id,
        "is_commitment": entry.commitment_id is not None,
        "minutes_until_start": minutes,
        "travel_minutes": travel,
        "free_minutes": max(0.0, minutes - travel) if travel is not None else None,
        "late_by_minutes": max(0.0, travel - minutes) if travel is not None else None,
        "action_authority": False,
        "meaning": "A constraint, not an instruction. Preparation, a shorter activity, waiting, or doing nothing are choices. No routine has been performed or booked.",
    }
