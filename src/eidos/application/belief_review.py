"""Conservative deterministic belief review for accepted relationship evidence."""

from __future__ import annotations

from eidos.domain.beliefs import BeliefProposal, BeliefState, project_beliefs, resolve_belief
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


def testimony_belief_events(history: list[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    """Review structured heard claims and later direct confirmations as distinct evidence."""
    considered = {
        str(event.payload["evidence_event_id"])
        for event in history
        if event.kind in {"belief.formed", "belief.revised", "belief.corrected", "belief.contested"}
    }
    output: list[DomainEvent] = []
    for evidence in history:
        evidence_id = str(evidence.event_id)
        if evidence_id in considered:
            continue
        if evidence.kind == "perception.recorded":
            if evidence.payload.get("owner") != "pathos":
                continue
            subject_id = evidence.payload.get("claim_subject_id")
            predicate = evidence.payload.get("claim_predicate")
            object_value = evidence.payload.get("claim_value")
            claim_confidence = evidence.payload.get("claim_confidence")
            speaker_id = evidence.payload.get("speaker_id")
            if not isinstance(speaker_id, str) or not _claim_shape(
                subject_id, predicate, object_value, claim_confidence
            ):
                continue
            assert isinstance(claim_confidence, (int, float)) and not isinstance(
                claim_confidence, bool
            )
            confidence = float(claim_confidence) * _speaker_reliability(
                project_beliefs([*history, *output]), speaker_id
            )
        elif evidence.kind == "resource.confirmed":
            subject_id = evidence.payload.get("subject_id")
            predicate = evidence.payload.get("predicate")
            object_value = evidence.payload.get("object_value")
            claim_confidence = evidence.payload.get("confidence", 0.95)
            if not _claim_shape(subject_id, predicate, object_value, claim_confidence):
                continue
            assert isinstance(claim_confidence, (int, float)) and not isinstance(
                claim_confidence, bool
            )
            confidence = float(claim_confidence)
        else:
            continue
        assert isinstance(subject_id, str)
        assert isinstance(predicate, str)
        assert isinstance(object_value, str)
        combined = [*history, *output]
        proposal = BeliefProposal(
            proposal_id=f"review-claim-{evidence.event_id}",
            belief_id=f"pathos-{subject_id}-{predicate}",
            owner_id="pathos",
            subject_id=subject_id,
            predicate=predicate,
            object_value=object_value,
            confidence=confidence,
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
        considered.add(evidence_id)
    return output


def _claim_shape(
    subject_id: object, predicate: object, object_value: object, confidence: object
) -> bool:
    return (
        all(
            isinstance(value, str) and bool(value.strip())
            for value in (subject_id, predicate, object_value)
        )
        and not isinstance(confidence, bool)
        and isinstance(confidence, (int, float))
        and 0 <= confidence <= 1
    )


def _speaker_reliability(state: BeliefState, speaker_id: str) -> float:
    belief = state.beliefs.get(f"pathos-{speaker_id}-testimony_reliability")
    if belief is None or belief.status == "contested":
        return 0.6
    if belief.object_value == "reliable":
        return 0.75
    if belief.object_value == "unreliable":
        return 0.35
    return 0.6
