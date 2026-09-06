"""Typed relational acts with consent-safe, evidence-linked consequences."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class RelationalMove(StrEnum):
    DISAGREE = "disagree"
    BOUNDARY = "boundary"
    APOLOGIZE = "apologize"


@dataclass(frozen=True, slots=True)
class RelationalProposal:
    proposal_id: str
    actor_id: str
    target_id: str
    move: RelationalMove
    text: str
    topic_id: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class RelationalResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "actor_id",
    "target_id",
    "move",
    "text",
    "topic_id",
    "expected_revision",
}


def parse_relational_proposal(content: str) -> RelationalProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Relational proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Relational fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Relational schema is not supported")
    for field in ("proposal_id", "actor_id", "target_id", "text", "topic_id"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    if len(value["text"]) > 500:
        raise ProposalRejected("text_too_long", "Relational text must be at most 500 characters")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        move = RelationalMove(value["move"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_move", "Relational move is not supported") from None
    return RelationalProposal(
        value["proposal_id"],
        value["actor_id"],
        value["target_id"],
        move,
        value["text"],
        value["topic_id"],
        revision,
    )


def resolve_relational_move(
    proposal: RelationalProposal,
    *,
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    known_actor_ids: set[str],
    actual_revision: int,
    simulated_at: str,
) -> RelationalResolution:
    common: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "actor_id": proposal.actor_id,
        "target_id": proposal.target_id,
        "move": proposal.move.value,
        "text": proposal.text,
        "topic_id": proposal.topic_id,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at,
    }
    proposed = DomainEvent(
        "relational.proposed", "pathos", common, correlation_id=proposal.proposal_id
    )

    def reject(code: str, explanation: str) -> RelationalResolution:
        return RelationalResolution(
            False,
            code,
            (
                proposed,
                DomainEvent(
                    "relational.rejected",
                    "pathos",
                    {**common, "code": code, "explanation": explanation},
                    causation_id=proposed.event_id,
                    correlation_id=proposal.proposal_id,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The relationship changed before this act")
    if proposal.actor_id != "pathos":
        return reject("wrong_actor", "This resolver currently owns Pathos's relational acts")
    if proposal.actor_id == proposal.target_id:
        return reject("same_actor", "A relational act needs another person")
    if {proposal.actor_id, proposal.target_id} - known_actor_ids:
        return reject("unknown_actor", "The actor or target is outside this world")
    if actor_locations.get(proposal.actor_id) != actor_locations.get(proposal.target_id):
        return reject("not_co_present", "Relational acts require co-presence")
    if any(
        event.kind in {"disagreement.expressed", "boundary.stated", "apology.offered"}
        and event.payload.get("proposal_id") == proposal.proposal_id
        for event in history
    ):
        return reject("duplicate_proposal", "This relational act already happened")
    if proposal.move is RelationalMove.APOLOGIZE and not _has_unrepaired_tension(proposal, history):
        return reject("nothing_to_repair", "An apology needs an unresolved prior rupture")

    kind, tension_delta, trust_delta = {
        RelationalMove.DISAGREE: ("disagreement.expressed", 0.08, -0.01),
        RelationalMove.BOUNDARY: ("boundary.stated", 0.02, 0.0),
        RelationalMove.APOLOGIZE: ("apology.offered", -0.03, 0.0),
    }[proposal.move]
    act = DomainEvent(
        kind,
        "pathos",
        {**common, "location_id": actor_locations[proposal.actor_id]},
        causation_id=proposed.event_id,
        correlation_id=proposal.proposal_id,
    )
    relationship = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": proposal.target_id,
            "evidence_actor_id": proposal.actor_id,
            "trust_delta": trust_delta,
            "tension_delta": tension_delta,
            "reason": f"Relational evidence: {proposal.move.value}.",
            "simulated_at": simulated_at,
        },
        causation_id=act.event_id,
        correlation_id=proposal.proposal_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": proposal.text,
            "owner": proposal.actor_id,
            "category": "relationship",
            "source": "direct-relational-act",
            "source_event_id": str(act.event_id),
            "person_id": proposal.target_id,
            "location_id": actor_locations[proposal.actor_id],
            "importance": 0.7,
            "confidence": 1.0,
            "simulated_at": simulated_at,
        },
        causation_id=act.event_id,
        correlation_id=proposal.proposal_id,
    )
    return RelationalResolution(True, "accepted", (proposed, act, relationship, memory))


def _has_unrepaired_tension(proposal: RelationalProposal, history: Sequence[DomainEvent]) -> bool:
    rupture = False
    for event in history:
        if event.kind == "disagreement.expressed" and {
            event.payload.get("actor_id"),
            event.payload.get("target_id"),
        } == {proposal.actor_id, proposal.target_id}:
            rupture = True
        if event.kind == "apology.offered" and event.payload.get("actor_id") == proposal.actor_id:
            if event.payload.get("target_id") == proposal.target_id:
                rupture = False
    return rupture
