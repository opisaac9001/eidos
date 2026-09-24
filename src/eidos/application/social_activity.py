"""Execute accepted, scheduled social time only when participants are co-present."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.world import npc_location


def scheduled_social_events(
    state: PlanningState,
    *,
    actor_location_id: str,
    simulated_at: datetime,
    actual_revision: int,
    actor_locations: Mapping[str, str] | None = None,
) -> list[DomainEvent]:
    """Resolve due talk intentions; absence leaves them pending for later consequences."""
    output: list[DomainEvent] = []
    projected = state
    for entry in state.calendar.values():
        if entry.status != "scheduled" or entry.action != ActionKind.TALK.value:
            continue
        start = datetime.fromisoformat(entry.starts_at)
        end = datetime.fromisoformat(entry.ends_at) if entry.ends_at else start
        if not start <= simulated_at <= end:
            continue
        target_id = entry.target_id
        if entry.actor_id != "pathos" or target_id is None:
            continue
        target_location = (
            actor_locations.get(target_id)
            if actor_locations is not None
            else npc_location(target_id, simulated_at.hour)
        )
        if entry.location_id != actor_location_id or target_location != actor_location_id:
            continue
        intention = next(
            (
                item
                for item in projected.intentions.values()
                if item.goal_id == entry.goal_id
                and item.action == ActionKind.TALK.value
                and item.status == "active"
            ),
            None,
        )
        if intention is None:
            continue
        resolution = resolve_action(
            ActionProposal(
                proposal_id=f"attend-{entry.schedule_id}",
                actor_id="pathos",
                action=ActionKind.TALK,
                expected_revision=actual_revision + len(output),
                target_id=target_id,
                schedule_id=entry.schedule_id,
                intention_id=intention.intention_id,
            ),
            state=projected,
            actor_location_id=actor_location_id,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at,
        )
        output.extend(resolution.events)
        for event in resolution.events:
            projected = projected.apply(event)
        if not resolution.accepted:
            continue
        accepted = next(event for event in resolution.events if event.kind == "action.accepted")
        correlation = entry.commitment_id or entry.schedule_id

        def consequence(kind: str, payload: dict[str, object]) -> DomainEvent:
            return DomainEvent(
                kind,
                "pathos",
                payload,
                causation_id=accepted.event_id,
                correlation_id=correlation,
            )

        if entry.commitment_id is not None:
            fulfilled = consequence(
                "commitment.fulfilled",
                {
                    "commitment_id": entry.commitment_id,
                    "simulated_at": simulated_at.isoformat(),
                },
            )
            output.append(fulfilled)
            projected = projected.apply(fulfilled)
        if entry.goal_id is not None:
            achieved = consequence(
                "goal.achieved",
                {"goal_id": entry.goal_id, "simulated_at": simulated_at.isoformat()},
            )
            output.append(achieved)
            projected = projected.apply(achieved)
        output.extend(
            (
                consequence(
                    "social.activity_completed",
                    {
                        "activity": "conversation",
                        "person_id": target_id,
                        "schedule_id": entry.schedule_id,
                        "location_id": entry.location_id,
                        "simulated_at": simulated_at.isoformat(),
                    },
                ),
                consequence(
                    "relationship.changed",
                    {
                        "person_id": target_id,
                        "evidence_actor_id": "pathos",
                        "familiarity_delta": 0.04,
                        "trust_delta": 0.02,
                        "reason": "Pathos showed up for accepted time together.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                ),
                consequence(
                    "memory.recorded",
                    {
                        "text": "I showed up for my planned time with "
                        f"{target_id.replace('-', ' ').title()}.",
                        "owner": "pathos",
                        "category": "encounter",
                        "source": "deterministic-consequence",
                        "source_event_id": str(accepted.event_id),
                        "person_id": target_id,
                        "goal_id": entry.goal_id,
                        "location_id": entry.location_id,
                        "importance": 0.7,
                        "confidence": 1.0,
                        "simulated_at": simulated_at.isoformat(),
                    },
                ),
            )
        )
    return output
