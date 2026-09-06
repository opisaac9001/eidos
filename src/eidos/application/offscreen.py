"""Low-detail deterministic NPC activity that persists without granting omniscience."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.world import PEOPLE, npc_location


def npc_world_events(history: Sequence[DomainEvent], simulated_at: datetime) -> list[DomainEvent]:
    """Advance location hourly and private needs at six-hour intervals."""
    state = project_npcs(history, simulated_at)
    output: list[DomainEvent] = []
    starting = not any(event.kind == "npc.simulation_started" for event in history)
    if starting:
        output.append(
            DomainEvent(
                "npc.simulation_started",
                "pathos",
                {"simulated_at": simulated_at.isoformat(), "schema_version": 1},
            )
        )
    for person in PEOPLE:
        actor_id = str(person["id"])
        current = state.people[actor_id]
        desired = npc_location(actor_id, simulated_at.hour)
        if starting or current.location_id != desired:
            moved = DomainEvent(
                "npc.moved",
                "pathos",
                {
                    "actor_id": actor_id,
                    "location_id": desired,
                    "simulated_at": simulated_at.isoformat(),
                    "visibility": "world",
                },
            )
            output.append(moved)
            state = state.apply(moved)
            current = state.people[actor_id]
        if simulated_at.hour not in {0, 6, 12, 18}:
            continue
        activity = DomainEvent(
            "npc.activity_recorded",
            "pathos",
            {
                "actor_id": actor_id,
                "location_id": desired,
                "activity": _activity(actor_id, desired),
                "simulated_at": simulated_at.isoformat(),
                "visibility": "private",
                "owner": actor_id,
            },
        )
        energy, connection, purpose = _next_needs(
            current.energy, current.connection, current.purpose, desired
        )
        changed = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": actor_id,
                "energy": energy,
                "connection": connection,
                "purpose": purpose,
                "simulated_at": simulated_at.isoformat(),
                "visibility": "private",
                "owner": actor_id,
            },
            causation_id=activity.event_id,
            correlation_id=f"npc-{actor_id}-{simulated_at.isoformat()}",
        )
        output.extend((activity, changed))
        state = state.apply(activity).apply(changed)
        if (
            current.plan_status == "active"
            and current.plan_action == "sketch"
            and current.plan_location_id == desired
            and "sketching" in str(activity.payload["activity"])
            and current.plan_id is not None
        ):
            completed = DomainEvent(
                "npc.plan_completed",
                "pathos",
                {
                    "actor_id": actor_id,
                    "plan_id": current.plan_id,
                    "owner": actor_id,
                    "visibility": "private",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=activity.event_id,
                correlation_id=current.plan_id,
            )
            output.append(completed)
            state = state.apply(completed)
    return output


def _activity(actor_id: str, location_id: str) -> str:
    if location_id == "home":
        return "resting at home"
    return {
        "mara": "running the cafe",
        "ellis": "working on repairs" if location_id == "workshop" else "taking a walk",
        "rowan": "sketching" if location_id == "park" else "visiting the cafe",
    }[actor_id]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _next_needs(
    energy: float, connection: float, purpose: float, location_id: str
) -> tuple[float, float, float]:
    if location_id == "home":
        return (
            _clamp(energy + 0.05),
            _toward(connection, 0.5, 0.02),
            _toward(purpose, 0.5, 0.05),
        )
    deltas = {
        "cafe": (-0.04, 0.06, 0.02),
        "workshop": (-0.06, 0.02, 0.06),
        "park": (0.02, 0.01, 0.03),
    }[location_id]
    return (
        _clamp(energy + deltas[0]),
        _clamp(connection + deltas[1]),
        _clamp(purpose + deltas[2]),
    )


def _toward(value: float, target: float, step: float) -> float:
    if value < target:
        return min(target, value + step)
    if value > target:
        return max(target, value - step)
    return value
