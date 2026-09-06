"""Consent-based object lending, gifting, and returning."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected


class TransferKind(StrEnum):
    GIVE = "give"
    LEND = "lend"
    RETURN = "return"


class TransferResponse(StrEnum):
    ACCEPT = "accept"
    DECLINE = "decline"


@dataclass(frozen=True, slots=True)
class TransferOffer:
    offer_id: str
    kind: str
    offered_by_id: str
    offered_to_id: str
    object_id: str
    reason: str
    status: str = "pending"


@dataclass(frozen=True, slots=True)
class TransferState:
    offers: Mapping[str, TransferOffer]

    def __post_init__(self) -> None:
        object.__setattr__(self, "offers", MappingProxyType(dict(self.offers)))

    def apply(self, event: DomainEvent) -> TransferState:
        offers = dict(self.offers)
        payload = event.payload
        if event.kind == "transfer.offered":
            offer_id = _required(payload, "offer_id")
            if offer_id in offers:
                raise ValueError("Transfer offer already exists")
            offers[offer_id] = TransferOffer(
                offer_id,
                _required(payload, "transfer_kind"),
                _required(payload, "offered_by_id"),
                _required(payload, "offered_to_id"),
                _required(payload, "object_id"),
                _required(payload, "reason"),
            )
        elif event.kind in {"transfer.accepted", "transfer.declined"}:
            offer = offers.get(_required(payload, "offer_id"))
            if offer is None:
                raise ValueError("Transfer offer does not exist")
            if offer.status != "pending":
                raise ValueError("Transfer offer is already closed")
            if _required(payload, "actor_id") != offer.offered_to_id:
                raise ValueError("Only the recipient can answer a transfer offer")
            offers[offer.offer_id] = replace(
                offer, status="accepted" if event.kind.endswith("accepted") else "declined"
            )
        return TransferState(offers)


@dataclass(frozen=True, slots=True)
class TransferOfferProposal:
    proposal_id: str
    offer_id: str
    actor_id: str
    counterparty_id: str
    object_id: str
    kind: TransferKind
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class TransferResponseProposal:
    proposal_id: str
    offer_id: str
    actor_id: str
    response: TransferResponse
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class TransferResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_OFFER_FIELDS = {
    "schema_version",
    "proposal_id",
    "offer_id",
    "actor_id",
    "counterparty_id",
    "object_id",
    "kind",
    "reason",
    "expected_revision",
}
_RESPONSE_FIELDS = {
    "schema_version",
    "proposal_id",
    "offer_id",
    "actor_id",
    "response",
    "reason",
    "expected_revision",
}


def parse_transfer_offer(content: str) -> TransferOfferProposal:
    value = _object(content, _OFFER_FIELDS, "Transfer offer")
    _text_fields(
        value,
        "proposal_id",
        "offer_id",
        "actor_id",
        "counterparty_id",
        "object_id",
        "reason",
    )
    _version_and_revision(value)
    try:
        kind = TransferKind(value["kind"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_transfer", "Transfer kind is not supported") from None
    return TransferOfferProposal(
        value["proposal_id"],
        value["offer_id"],
        value["actor_id"],
        value["counterparty_id"],
        value["object_id"],
        kind,
        value["reason"],
        value["expected_revision"],
    )


def parse_transfer_response(content: str) -> TransferResponseProposal:
    value = _object(content, _RESPONSE_FIELDS, "Transfer response")
    _text_fields(value, "proposal_id", "offer_id", "actor_id", "reason")
    _version_and_revision(value)
    try:
        response = TransferResponse(value["response"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_response", "Transfer response is not supported") from None
    return TransferResponseProposal(
        value["proposal_id"],
        value["offer_id"],
        value["actor_id"],
        response,
        value["reason"],
        value["expected_revision"],
    )


def resolve_transfer_offer(
    proposal: TransferOfferProposal,
    *,
    planning: PlanningState,
    transfers: TransferState,
    actor_location_id: str,
    counterparty_location_id: str,
    actual_revision: int,
    simulated_at: datetime,
) -> TransferResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "offer_id": proposal.offer_id,
        "transfer_kind": proposal.kind.value,
        "offered_by_id": proposal.actor_id,
        "offered_to_id": proposal.counterparty_id,
        "object_id": proposal.object_id,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "transfer.offer_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> TransferResolution:
        return TransferResolution(
            False,
            code,
            (
                proposed,
                _event(
                    "transfer.offer_rejected",
                    "pathos",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed after this offer was proposed")
    if proposal.offer_id in transfers.offers:
        return reject("duplicate_offer", "That transfer offer already exists")
    if proposal.actor_id == proposal.counterparty_id:
        return reject("same_actor", "An object transfer requires two different actors")
    item = planning.objects.get(proposal.object_id)
    if item is None:
        return reject("unknown_object", "The object does not exist")
    if actor_location_id != counterparty_location_id or item.location_id != actor_location_id:
        return reject("not_co_present", "Both actors and the object must be together")
    if proposal.kind in {TransferKind.GIVE, TransferKind.LEND} and (
        item.owner_id != proposal.actor_id or item.custodian_id != proposal.actor_id
    ):
        return reject("no_authority", "Only an owner holding the object can offer it")
    if proposal.kind is TransferKind.RETURN and (
        item.custodian_id != proposal.actor_id or item.owner_id != proposal.counterparty_id
    ):
        return reject("invalid_return", "Only the current borrower can return it to its owner")
    return TransferResolution(
        True,
        "accepted",
        (proposed, _event("transfer.offered", "pathos", common, proposed)),
    )


def resolve_transfer_response(
    proposal: TransferResponseProposal,
    *,
    planning: PlanningState,
    transfers: TransferState,
    actor_location_id: str,
    counterparty_location_id: str,
    actual_revision: int,
    simulated_at: datetime,
) -> TransferResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "offer_id": proposal.offer_id,
        "actor_id": proposal.actor_id,
        "response": proposal.response.value,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "transfer.response_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> TransferResolution:
        return TransferResolution(
            False,
            code,
            (
                proposed,
                _event(
                    "transfer.response_rejected",
                    "pathos",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed before the response")
    offer = transfers.offers.get(proposal.offer_id)
    if offer is None:
        return reject("unknown_offer", "The transfer offer does not exist")
    if offer.status != "pending":
        return reject("closed_offer", "The transfer offer is already closed")
    if proposal.actor_id != offer.offered_to_id:
        return reject("wrong_actor", "Only the recipient can answer the offer")
    item = planning.objects.get(offer.object_id)
    if item is None:
        return reject("unknown_object", "The offered object no longer exists")
    if actor_location_id != counterparty_location_id or item.location_id != actor_location_id:
        return reject("not_co_present", "Both actors and the object must still be together")
    kind = TransferKind(offer.kind)
    if kind in {TransferKind.GIVE, TransferKind.LEND} and (
        item.owner_id != offer.offered_by_id or item.custodian_id != offer.offered_by_id
    ):
        return reject("object_changed", "The offerer no longer owns and holds the object")
    if kind is TransferKind.RETURN and (
        item.custodian_id != offer.offered_by_id or item.owner_id != offer.offered_to_id
    ):
        return reject("object_changed", "The return no longer matches current custody")
    resolved_kind = (
        "transfer.accepted" if proposal.response is TransferResponse.ACCEPT else "transfer.declined"
    )
    resolved = _event(resolved_kind, "pathos", common, proposed)
    if proposal.response is TransferResponse.DECLINE:
        return TransferResolution(True, "declined", (proposed, resolved))
    custody = _event(
        "object.custody_changed",
        "pathos",
        {
            "object_id": offer.object_id,
            "from_custodian_id": offer.offered_by_id,
            "to_custodian_id": offer.offered_to_id,
            "simulated_at": simulated_at.isoformat(),
        },
        resolved,
    )
    effects = [custody]
    if kind is TransferKind.GIVE:
        effects.append(
            _event(
                "object.ownership_changed",
                "pathos",
                {
                    "object_id": offer.object_id,
                    "from_owner_id": offer.offered_by_id,
                    "to_owner_id": offer.offered_to_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                resolved,
            )
        )
    return TransferResolution(True, "accepted", (proposed, resolved, *effects))


def project_transfers(events: Sequence[DomainEvent]) -> TransferState:
    state = TransferState({})
    for event in events:
        state = state.apply(event)
    return state


def _event(
    kind: str, aggregate_id: str, payload: Mapping[str, Any], cause: DomainEvent
) -> DomainEvent:
    return DomainEvent(
        kind,
        aggregate_id,
        payload,
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def _object(content: str, fields: set[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", f"{label} was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != fields:
        raise ProposalRejected("invalid_shape", f"{label} fields did not match schema v1")
    return value


def _text_fields(value: Mapping[str, Any], *fields: str) -> None:
    for field in fields:
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")


def _version_and_revision(value: Mapping[str, Any]) -> None:
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Transfer schema is not supported")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value
