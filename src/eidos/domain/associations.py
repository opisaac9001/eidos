"""Typed, source-linked subjective associations kept separate from factual memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.folding import event_index, payload_candidates
from eidos.domain.proposals import ProposalRejected


@dataclass(frozen=True, slots=True)
class AssociationProposal:
    proposal_id: str
    actor_id: str
    source_memory_id: UUID
    cue: str
    text: str
    salience: float
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class AssociationResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "actor_id",
    "source_memory_id",
    "cue",
    "text",
    "salience",
    "expected_revision",
}


def parse_association_proposal(content: str) -> AssociationProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Association proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Association fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Association schema is not supported")
    for field in ("proposal_id", "actor_id", "cue", "text"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    salience = value["salience"]
    if (
        isinstance(salience, bool)
        or not isinstance(salience, (int, float))
        or not 0 <= salience <= 1
    ):
        raise ProposalRejected("invalid_salience", "salience must be between zero and one")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        source_memory_id = UUID(value["source_memory_id"])
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_source", "source_memory_id must be a UUID") from None
    return AssociationProposal(
        proposal_id=value["proposal_id"],
        actor_id=value["actor_id"],
        source_memory_id=source_memory_id,
        cue=value["cue"],
        text=value["text"],
        salience=float(salience),
        expected_revision=revision,
    )


def resolve_association(
    proposal: AssociationProposal,
    *,
    history: Sequence[DomainEvent],
    actual_revision: int,
    simulated_at: str,
) -> AssociationResolution:
    proposal_audit: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "actor_id": proposal.actor_id,
        "source_memory_id": str(proposal.source_memory_id),
        "salience": proposal.salience,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at,
    }
    accepted_payload: dict[str, object] = {
        **proposal_audit,
        "cue": proposal.cue,
        "text": proposal.text,
    }
    proposed = DomainEvent(
        "association.proposed",
        proposal.actor_id,
        proposal_audit,
        correlation_id=proposal.proposal_id,
    )

    def effect(
        kind: str, extra: Mapping[str, object], *, payload: Mapping[str, object] = proposal_audit
    ) -> DomainEvent:
        return DomainEvent(
            kind,
            proposal.actor_id,
            {**payload, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> AssociationResolution:
        return AssociationResolution(
            False,
            code,
            (proposed, effect("association.rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The associative context changed")
    if any(
        event.kind == "association.formed"
        and event.payload.get("proposal_id") == proposal.proposal_id
        for event in payload_candidates(history, "proposal_id", proposal.proposal_id)
    ):
        return reject("duplicate_proposal", "This association already exists")
    # The first event with an id is the one indexed under its string form.
    source = (
        event_index(history).get(str(proposal.source_memory_id))
        if isinstance(proposal.source_memory_id, UUID)
        else next((event for event in history if event.event_id == proposal.source_memory_id), None)
    )
    if source is None or source.kind != "memory.recorded":
        return reject("missing_source", "The cited autobiographical memory does not exist")
    if source.payload.get("owner", "pathos") != proposal.actor_id:
        return reject("private_source", "The actor does not own the cited memory")
    source_category = str(source.payload.get("category", "experience"))
    formed = effect(
        "association.formed",
        {
            "source_category": source_category,
            "derived_from_dream": source_category == "dream",
            "factual": False,
        },
        payload=accepted_payload,
    )
    events = [proposed, formed]
    if proposal.salience >= 0.65:
        events.extend(
            (
                DomainEvent(
                    "association.surfaced",
                    proposal.actor_id,
                    {
                        "proposal_id": proposal.proposal_id,
                        "association_id": str(formed.event_id),
                        "simulated_at": simulated_at,
                    },
                    causation_id=formed.event_id,
                    correlation_id=proposal.proposal_id,
                ),
                DomainEvent(
                    "thought.recorded",
                    proposal.actor_id,
                    {
                        "text": proposal.text,
                        "simulated_at": simulated_at,
                        "source": "association",
                        "source_association_id": str(formed.event_id),
                        "source_memory_id": str(source.event_id),
                        "source_category": source_category,
                        "factual": False,
                        "role": "murmur",
                    },
                    causation_id=formed.event_id,
                    correlation_id=proposal.proposal_id,
                ),
            )
        )
    return AssociationResolution(True, "accepted", tuple(events))
