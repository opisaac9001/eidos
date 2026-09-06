"""Typed speech delivery with presence, audience, and privacy boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class Privacy(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


@dataclass(frozen=True, slots=True)
class SpeechProposal:
    proposal_id: str
    speaker_id: str
    audience_id: str
    text: str
    privacy: Privacy
    expected_revision: int
    topic_id: str | None = None
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class SpeechResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "speaker_id",
    "audience_id",
    "text",
    "privacy",
    "expected_revision",
    "topic_id",
}


def parse_speech_proposal(content: str) -> SpeechProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Speech proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Speech fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Speech schema is not supported")
    for field in ("proposal_id", "speaker_id", "audience_id", "text"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    if len(value["text"]) > 500:
        raise ProposalRejected("speech_too_long", "Speech must be at most 500 characters")
    if value["topic_id"] is not None and (
        not isinstance(value["topic_id"], str) or not value["topic_id"].strip()
    ):
        raise ProposalRejected("invalid_topic", "topic_id must be null or non-empty")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        privacy = Privacy(value["privacy"])
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_privacy", "privacy must be private or public") from None
    return SpeechProposal(
        proposal_id=value["proposal_id"],
        speaker_id=value["speaker_id"],
        audience_id=value["audience_id"],
        text=value["text"],
        privacy=privacy,
        expected_revision=revision,
        topic_id=value["topic_id"],
    )


def resolve_speech(
    proposal: SpeechProposal,
    *,
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    known_actor_ids: set[str],
    actual_revision: int,
    simulated_at: str,
) -> SpeechResolution:
    common: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "speaker_id": proposal.speaker_id,
        "audience_id": proposal.audience_id,
        "text": proposal.text,
        "privacy": proposal.privacy.value,
        "topic_id": proposal.topic_id,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at,
    }
    proposed = DomainEvent("speech.proposed", "pathos", common, correlation_id=proposal.proposal_id)

    def effect(kind: str, extra: Mapping[str, object]) -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            {**common, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> SpeechResolution:
        return SpeechResolution(
            False,
            code,
            (proposed, effect("speech.rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The scene changed before the speech was delivered")
    if proposal.speaker_id == proposal.audience_id:
        return reject("same_actor", "Speech needs a distinct audience")
    if {proposal.speaker_id, proposal.audience_id} - known_actor_ids:
        return reject("unknown_actor", "The speaker or audience is outside the scene world")
    speaker_location = actor_locations.get(proposal.speaker_id)
    audience_location = actor_locations.get(proposal.audience_id)
    if speaker_location is None or speaker_location != audience_location:
        return reject("not_co_present", "Speaker and audience must share a location")
    if any(
        event.kind == "speech.delivered"
        and event.payload.get("proposal_id") == proposal.proposal_id
        for event in history
    ):
        return reject("duplicate_proposal", "This speech was already delivered")
    delivered = effect("speech.delivered", {"location_id": speaker_location})
    perceived = DomainEvent(
        "perception.recorded",
        "pathos",
        {
            "owner": proposal.audience_id,
            "source_event_id": str(delivered.event_id),
            "source_kind": "speech",
            "speaker_id": proposal.speaker_id,
            "person_id": proposal.speaker_id,
            "text": proposal.text,
            "privacy": proposal.privacy.value,
            "location_id": speaker_location,
            "reported": True,
            "simulated_at": simulated_at,
        },
        causation_id=delivered.event_id,
        correlation_id=proposal.proposal_id,
    )
    return SpeechResolution(True, "accepted", (proposed, delivered, perceived))
