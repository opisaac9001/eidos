"""Conservative deterministic belief review for accepted relationship evidence."""

from __future__ import annotations

from eidos.domain.beliefs import BeliefProposal, project_beliefs, resolve_belief
from eidos.domain.events import DomainEvent


def relationship_belief_events(history: list[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    considered = {
        str(event.payload["evidence_event_id"])
        for event in history
        if event.kind in {"belief.formed", "belief.revised", "belief.corrected", "belief.contested"}
    }
    output: list[DomainEvent] = []
    for evidence in history:
        if evidence.kind != "relationship.changed" or str(evidence.event_id) in considered:
            continue
        subject_id = evidence.payload.get("evidence_actor_id")
        trust_delta = evidence.payload.get("trust_delta", 0.0)
        if (
            not isinstance(subject_id, str)
            or isinstance(trust_delta, bool)
            or not isinstance(trust_delta, (int, float))
        ):
            continue
        combined = [*history, *output]
        proposal = BeliefProposal(
            proposal_id=f"review-relationship-{evidence.event_id}",
            belief_id=f"pathos-{subject_id}-commitment-reliability",
            owner_id="pathos",
            subject_id=subject_id,
            predicate="commitment_reliability",
            object_value="reliable" if trust_delta > 0 else "unreliable",
            confidence=min(0.9, 0.6 + abs(float(trust_delta))),
            evidence_event_id=evidence.event_id,
            expected_revision=len(combined),
        )
        resolution = resolve_belief(
            proposal,
            state=project_beliefs(combined),
            history=combined,
            actual_revision=len(combined),
            simulated_at=simulated_at,
        )
        output.extend(resolution.events)
        considered.add(str(evidence.event_id))
    return output
