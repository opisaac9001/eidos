"""Actor-owned, evidence-linked beliefs kept separate from world truth."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


@dataclass(frozen=True, slots=True)
class Belief:
    belief_id: str
    owner_id: str
    subject_id: str
    predicate: str
    object_value: str
    confidence: float
    status: str
    revision: int
    evidence_count: int
    last_evidence_id: str
    alternative_value: str | None = None


@dataclass(frozen=True, slots=True)
class BeliefState:
    beliefs: Mapping[str, Belief]

    def __post_init__(self) -> None:
        object.__setattr__(self, "beliefs", MappingProxyType(dict(self.beliefs)))

    @classmethod
    def empty(cls) -> BeliefState:
        return cls({})

    def apply(self, event: DomainEvent) -> BeliefState:
        beliefs = dict(self.beliefs)
        payload = event.payload
        if event.kind == "belief.formed":
            belief_id = _required(payload, "belief_id")
            if belief_id in beliefs:
                raise ValueError("Belief already exists")
            identity = (
                _required(payload, "owner_id"),
                _required(payload, "subject_id"),
                _required(payload, "predicate"),
            )
            if any(
                (belief.owner_id, belief.subject_id, belief.predicate) == identity
                for belief in beliefs.values()
            ):
                raise ValueError("Belief identity already exists")
            beliefs[belief_id] = Belief(
                belief_id=belief_id,
                owner_id=identity[0],
                subject_id=identity[1],
                predicate=identity[2],
                object_value=_required(payload, "object_value"),
                confidence=_confidence(payload),
                status="held",
                revision=1,
                evidence_count=1,
                last_evidence_id=_required(payload, "evidence_event_id"),
            )
        elif event.kind in {"belief.revised", "belief.corrected", "belief.contested"}:
            belief_id = _required(payload, "belief_id")
            if belief_id not in beliefs:
                raise ValueError("Unknown belief")
            belief = beliefs[belief_id]
            expected = payload.get("prior_revision")
            if expected != belief.revision:
                raise ValueError("Belief revision is stale")
            evidence_id = _required(payload, "evidence_event_id")
            if evidence_id == belief.last_evidence_id:
                raise ValueError("Evidence cannot reinforce itself twice")
            if event.kind == "belief.contested":
                beliefs[belief_id] = replace(
                    belief,
                    confidence=_confidence(payload),
                    status="contested",
                    revision=belief.revision + 1,
                    evidence_count=belief.evidence_count + 1,
                    last_evidence_id=evidence_id,
                    alternative_value=_required(payload, "alternative_value"),
                )
            else:
                beliefs[belief_id] = replace(
                    belief,
                    object_value=_required(payload, "object_value"),
                    confidence=_confidence(payload),
                    status="held",
                    revision=belief.revision + 1,
                    evidence_count=belief.evidence_count + 1,
                    last_evidence_id=evidence_id,
                    alternative_value=None,
                )
        return BeliefState(beliefs)


@dataclass(frozen=True, slots=True)
class BeliefProposal:
    proposal_id: str
    belief_id: str
    owner_id: str
    subject_id: str
    predicate: str
    object_value: str
    confidence: float
    evidence_event_id: UUID
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class BeliefResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "belief_id",
    "owner_id",
    "subject_id",
    "predicate",
    "object_value",
    "confidence",
    "evidence_event_id",
    "expected_revision",
}


def parse_belief_proposal(content: str) -> BeliefProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Belief proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Belief fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Belief schema is not supported")
    for field in (
        "proposal_id",
        "belief_id",
        "owner_id",
        "subject_id",
        "predicate",
        "object_value",
    ):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    confidence = value["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ProposalRejected("invalid_confidence", "confidence must be between zero and one")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        evidence_id = UUID(value["evidence_event_id"])
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_evidence", "evidence_event_id must be a UUID") from None
    return BeliefProposal(
        proposal_id=value["proposal_id"],
        belief_id=value["belief_id"],
        owner_id=value["owner_id"],
        subject_id=value["subject_id"],
        predicate=value["predicate"],
        object_value=value["object_value"],
        confidence=float(confidence),
        evidence_event_id=evidence_id,
        expected_revision=revision,
    )


def resolve_belief(
    proposal: BeliefProposal,
    *,
    state: BeliefState,
    history: Sequence[DomainEvent],
    actual_revision: int,
    simulated_at: str,
) -> BeliefResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "belief_id": proposal.belief_id,
        "owner_id": proposal.owner_id,
        "subject_id": proposal.subject_id,
        "predicate": proposal.predicate,
        "object_value": proposal.object_value,
        "confidence": proposal.confidence,
        "evidence_event_id": str(proposal.evidence_event_id),
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at,
    }
    proposed = DomainEvent("belief.proposed", "pathos", common, correlation_id=proposal.proposal_id)

    def effect(kind: str, extra: Mapping[str, object]) -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            {**common, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> BeliefResolution:
        return BeliefResolution(
            False,
            code,
            (proposed, effect("belief.rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The evidence context changed")
    evidence = next((item for item in history if item.event_id == proposal.evidence_event_id), None)
    if evidence is None:
        return reject("missing_evidence", "The cited evidence does not exist")
    if evidence.kind == "memory.consolidated":
        return reject("derived_evidence", "A consolidation is not independent evidence")
    if not _visible_to(proposal.owner_id, evidence):
        return reject("private_evidence", "The belief owner cannot access this evidence")
    if evidence.kind == "dream.recorded" or (
        evidence.kind == "memory.recorded" and evidence.payload.get("category") == "dream"
    ):
        return reject("dream_evidence", "Dream content cannot establish a factual belief")
    references = {
        value
        for key, value in evidence.payload.items()
        if key.endswith("_id") and key != "source_event_id" and isinstance(value, str)
    }
    if proposal.subject_id not in references:
        return reject("unlinked_subject", "The evidence does not identify the belief subject")
    existing = state.beliefs.get(proposal.belief_id)
    if existing is None:
        if any(
            (belief.owner_id, belief.subject_id, belief.predicate)
            == (proposal.owner_id, proposal.subject_id, proposal.predicate)
            for belief in state.beliefs.values()
        ):
            return reject("duplicate_identity", "This belief already exists under another ID")
        formed = effect("belief.formed", {})
        return BeliefResolution(True, "formed", (proposed, formed))
    if (existing.owner_id, existing.subject_id, existing.predicate) != (
        proposal.owner_id,
        proposal.subject_id,
        proposal.predicate,
    ):
        return reject("identity_mismatch", "A belief ID cannot change owner, subject, or predicate")
    if existing.last_evidence_id == str(proposal.evidence_event_id):
        return reject("duplicate_evidence", "The same evidence was already considered")
    if existing.object_value == proposal.object_value:
        confidence = min(0.98, max(existing.confidence, proposal.confidence) + 0.03)
        revised = effect(
            "belief.revised", {"prior_revision": existing.revision, "confidence": confidence}
        )
        return BeliefResolution(True, "revised", (proposed, revised))
    direct = evidence.kind in {"object.condition_changed", "resource.confirmed", "world.weather"}
    if direct and proposal.confidence >= existing.confidence:
        corrected = effect(
            "belief.corrected",
            {"prior_revision": existing.revision, "confidence": proposal.confidence},
        )
        return BeliefResolution(True, "corrected", (proposed, corrected))
    contested = effect(
        "belief.contested",
        {
            "prior_revision": existing.revision,
            "confidence": max(0.1, existing.confidence - 0.15),
            "alternative_value": proposal.object_value,
        },
    )
    return BeliefResolution(True, "contested", (proposed, contested))


def project_beliefs(events: Sequence[DomainEvent]) -> BeliefState:
    state = BeliefState.empty()
    for event in events:
        state = state.apply(event)
    return state


def _visible_to(owner_id: str, evidence: DomainEvent) -> bool:
    if evidence.kind == "memory.recorded":
        evidence_owner = evidence.payload.get("owner", "pathos")
        return isinstance(evidence_owner, str) and evidence_owner == owner_id
    if evidence.kind == "perception.recorded":
        return evidence.payload.get("owner") == owner_id
    return owner_id == "pathos"


def _required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _confidence(payload: Mapping[str, object]) -> float:
    value = payload.get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("confidence must be between zero and one")
    return float(value)
