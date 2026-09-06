"""A small consent-based loan supporting the first personal project."""

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.transfers import (
    TransferKind,
    TransferOfferProposal,
    TransferResponse,
    TransferResponseProposal,
    project_transfers,
    resolve_transfer_offer,
    resolve_transfer_response,
)

OBJECT_ID = "bookbinding-awl"
LOAN_ID = "ellis-lends-bookbinding-awl"
RETURN_ID = "pathos-returns-bookbinding-awl"


def object_story_events(
    current: datetime,
    existing: Sequence[DomainEvent],
    actor_location_id: str,
) -> list[DomainEvent]:
    """Loan the required tool before practice and return it after completion."""

    history = list(existing)
    day = (current.date() - datetime(2026, 1, 1).date()).days + 1
    planning = project_planning(history)
    if day == 2 and current.hour == 14 and OBJECT_ID not in planning.objects:
        registered = DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": OBJECT_ID,
                "name": "Ellis's bookbinding awl",
                "owner_id": "ellis",
                "custodian_id": "ellis",
                "location_id": "workshop",
                "condition": "usable",
                "simulated_at": current.isoformat(),
            },
            correlation_id=LOAN_ID,
        )
        history.append(registered)
        loan = _offer_and_accept(
            history,
            current,
            actor_location_id,
            offer_id=LOAN_ID,
            kind=TransferKind.LEND,
            offered_by="ellis",
            offered_to="pathos",
            reason="Ellis offered the awl for Pathos's notebook project.",
        )
        return [registered, *loan]
    item = planning.objects.get(OBJECT_ID)
    transfers = project_transfers(history)
    if (
        day == 5
        and current.hour == 17
        and item is not None
        and item.custodian_id == "pathos"
        and RETURN_ID not in transfers.offers
    ):
        return _offer_and_accept(
            history,
            current,
            actor_location_id,
            offer_id=RETURN_ID,
            kind=TransferKind.RETURN,
            offered_by="pathos",
            offered_to="ellis",
            reason="Pathos finished the project and returned Ellis's awl.",
        )
    return []


def _offer_and_accept(
    history: list[DomainEvent],
    current: datetime,
    actor_location_id: str,
    *,
    offer_id: str,
    kind: TransferKind,
    offered_by: str,
    offered_to: str,
    reason: str,
) -> list[DomainEvent]:
    offered = resolve_transfer_offer(
        TransferOfferProposal(
            proposal_id=f"offer-{offer_id}",
            offer_id=offer_id,
            actor_id=offered_by,
            counterparty_id=offered_to,
            object_id=OBJECT_ID,
            kind=kind,
            reason=reason,
            expected_revision=len(history),
        ),
        planning=project_planning(history),
        transfers=project_transfers(history),
        actor_location_id=actor_location_id,
        counterparty_location_id="workshop",
        actual_revision=len(history),
        simulated_at=current,
    )
    if not offered.accepted:
        return list(offered.events)
    pending = [*history, *offered.events]
    answered = resolve_transfer_response(
        TransferResponseProposal(
            proposal_id=f"accept-{offer_id}",
            offer_id=offer_id,
            actor_id=offered_to,
            response=TransferResponse.ACCEPT,
            reason="The recipient explicitly accepted the transfer.",
            expected_revision=len(pending),
        ),
        planning=project_planning(pending),
        transfers=project_transfers(pending),
        actor_location_id=actor_location_id,
        counterparty_location_id="workshop",
        actual_revision=len(pending),
        simulated_at=current,
    )
    if not answered.accepted:
        return [*offered.events, *answered.events]
    custody = next(event for event in answered.events if event.kind == "object.custody_changed")
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": (
                "Ellis lent me a bookbinding awl for the notebook project."
                if kind is TransferKind.LEND
                else "I returned Ellis's bookbinding awl after finishing the notebook."
            ),
            "owner": "pathos",
            "category": "object-transfer",
            "source": "authored-object-story",
            "source_event_id": str(custody.event_id),
            "object_id": OBJECT_ID,
            "person_id": "ellis",
            "location_id": "workshop",
            "importance": 0.65,
            "confidence": 1.0,
            "simulated_at": current.isoformat(),
        },
        causation_id=custody.event_id,
        correlation_id=offer_id,
    )
    return [*offered.events, *answered.events, memory]
