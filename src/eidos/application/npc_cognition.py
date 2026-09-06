"""Bounded NPC belief formation from each actor's own accepted perceptions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.beliefs import BeliefProposal, project_beliefs, resolve_belief
from eidos.domain.events import DomainEvent


def npc_belief_events(history: Sequence[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    """Turn unprocessed public-event perceptions into private, owned beliefs."""
    output: list[DomainEvent] = []
    state = project_beliefs(history)
    used_evidence = {belief.last_evidence_id for belief in state.beliefs.values()}
    for perception in history:
        owner = perception.payload.get("owner")
        location_id = perception.payload.get("location_id")
        if (
            perception.kind != "perception.recorded"
            or perception.payload.get("source_kind") != "world_event"
            or not isinstance(owner, str)
            or owner == "pathos"
            or not isinstance(location_id, str)
            or str(perception.event_id) in used_evidence
        ):
            continue
        belief_id = f"{owner}-{location_id}-community-activity"
        resolution = resolve_belief(
            BeliefProposal(
                proposal_id=f"interpret-{perception.event_id}",
                belief_id=belief_id,
                owner_id=owner,
                subject_id=location_id,
                predicate="community_activity",
                object_value="neighbors gather here",
                confidence=0.85,
                evidence_event_id=perception.event_id,
                expected_revision=len(history) + len(output),
            ),
            state=state,
            history=[*history, *output],
            actual_revision=len(history) + len(output),
            simulated_at=simulated_at,
        )
        output.extend(resolution.events)
        for event in resolution.events:
            state = state.apply(event)
        if resolution.accepted:
            used_evidence.add(str(perception.event_id))
            formed = next(event for event in resolution.events if event.kind == "belief.formed")
            output.append(
                DomainEvent(
                    "npc.plan_created",
                    "pathos",
                    {
                        "actor_id": owner,
                        "plan_id": f"{owner}-sketch-seed-swap",
                        "title": "Make a small sketch of the neighborhood seed swap",
                        "action": "sketch",
                        "location_id": location_id,
                        "due_at": (
                            datetime.fromisoformat(simulated_at) + timedelta(days=2)
                        ).isoformat(),
                        "owner": owner,
                        "visibility": "private",
                        "simulated_at": simulated_at,
                    },
                    causation_id=formed.event_id,
                    correlation_id=formed.correlation_id,
                )
            )
    return output
