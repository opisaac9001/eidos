"""Consent-based substitute loans and delayed replacement after object loss."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState, WorldObject, project_planning
from eidos.domain.transfers import (
    TransferKind,
    TransferOfferProposal,
    TransferResponse,
    TransferResponseProposal,
    project_transfers,
    resolve_transfer_offer,
    resolve_transfer_response,
)


def object_recovery_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    planning: PlanningState,
    *,
    pathos_awake: bool,
    actor_locations: Mapping[str, str],
    npc_people: Mapping[str, NPCState],
    values: Mapping[str, float],
) -> list[DomainEvent]:
    """Return due loans, resolve replacement handoffs, or make one recovery choice."""
    returned = _return_due_loan(history, simulated_at, actual_revision, planning, actor_locations)
    if returned:
        return returned
    replacement = _pending_replacement(history)
    if (
        replacement is not None
        and datetime.fromisoformat(str(replacement.payload["due_at"])) <= simulated_at
    ):
        return _replacement_handoff(
            history, replacement, simulated_at, planning, actor_locations.get("pathos", "home")
        )
    if replacement is not None:
        return []
    if not pathos_awake or not 9 <= simulated_at.hour < 18:
        return []
    handled = {
        str(event.payload["source_event_id"])
        for event in history
        if event.kind == "object.recovery_decided"
    }
    source = next(
        (
            event
            for event in history
            if str(event.event_id) not in handled
            and (
                event.kind == "object.repair_failed"
                or (
                    event.kind == "object.maintenance_decided"
                    and event.payload.get("decision") == "retire"
                )
            )
        ),
        None,
    )
    if source is None:
        return []
    object_id = str(source.payload["object_id"])
    item = planning.objects.get(object_id)
    if item is None:
        return []
    substitute = _loan_candidate(item, planning, actor_locations, npc_people)
    reliability = _bounded(values.get("reliability", 0.5))
    autonomy = _bounded(values.get("autonomy", 0.5))
    seek_loan = substitute is not None and _sample(f"seek-loan-{object_id}") < 0.35 + 0.4 * (
        1 - autonomy
    )
    replace = not seek_loan and _sample(f"replace-{object_id}") < 0.25 + 0.55 * reliability
    decision_name = "seek_loan" if seek_loan else "replace" if replace else "live_without"
    correlation = f"recover-{source.event_id}"
    decision = DomainEvent(
        "object.recovery_decided",
        "pathos",
        {
            "object_id": object_id,
            "source_event_id": str(source.event_id),
            "decision": decision_name,
            "substitute_id": substitute.object_id if substitute else None,
            "reason": {
                "seek_loan": "A compatible object and its owner were present, so Pathos asked.",
                "replace": "Pathos chose a delayed replacement rather than rewriting the old object.",
                "live_without": "Pathos chose to live without the object for now.",
            }[decision_name],
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=source.event_id,
        correlation_id=correlation,
    )
    if seek_loan and substitute is not None:
        return _loan_events(
            history,
            [decision],
            substitute,
            simulated_at,
            actual_revision,
            npc_people[substitute.owner_id],
            correlation,
        )
    if not replace:
        return [decision]
    ordered = DomainEvent(
        "object.replacement_ordered",
        "pathos",
        {
            "replacement_id": f"replacement-{source.event_id}",
            "object_id": object_id,
            "attempt": 1,
            "due_at": (simulated_at + timedelta(days=2)).isoformat(),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=decision.event_id,
        correlation_id=correlation,
    )
    return [decision, ordered]


def _loan_candidate(
    original: WorldObject,
    planning: PlanningState,
    locations: Mapping[str, str],
    people: Mapping[str, NPCState],
) -> WorldObject | None:
    kind = original.name.casefold().split()[-1]
    pathos_location = locations.get("pathos")
    return next(
        (
            item
            for item in planning.objects.values()
            if item.object_id != original.object_id
            and kind in item.name.casefold().split()
            and item.condition in {"good", "usable", "repaired"}
            and item.quantity != 0
            and item.owner_id == item.custodian_id
            and item.owner_id in people
            and item.location_id == pathos_location
            and locations.get(item.owner_id) == pathos_location
        ),
        None,
    )


def _loan_events(
    history: Sequence[DomainEvent],
    output: list[DomainEvent],
    substitute: WorldObject,
    at: datetime,
    revision: int,
    owner: NPCState,
    correlation: str,
) -> list[DomainEvent]:
    requested = DomainEvent(
        "object.loan_requested",
        "pathos",
        {
            "object_id": substitute.object_id,
            "owner_id": substitute.owner_id,
            "simulated_at": at.isoformat(),
        },
        causation_id=output[0].event_id,
        correlation_id=correlation,
    )
    output.append(requested)
    capacity = max(
        0.05, min(0.95, 0.45 * owner.energy + 0.3 * owner.purpose + 0.25 * owner.connection)
    )
    accepts = _sample(f"loan-consent-{correlation}-{owner.actor_id}") < capacity
    answer = DomainEvent(
        "object.loan_request_accepted" if accepts else "object.loan_request_declined",
        "pathos",
        {
            "object_id": substitute.object_id,
            "owner_id": owner.actor_id,
            "reason": "The owner independently chose whether to offer the substitute.",
            "simulated_at": at.isoformat(),
        },
        causation_id=requested.event_id,
        correlation_id=correlation,
    )
    output.append(answer)
    if not accepts:
        return output
    base = [*history, *output]
    offer_id = f"loan-{correlation}"
    offered = resolve_transfer_offer(
        TransferOfferProposal(
            f"offer-{offer_id}",
            offer_id,
            owner.actor_id,
            "pathos",
            substitute.object_id,
            TransferKind.LEND,
            "A temporary substitute after the original object became unavailable.",
            revision + len(output),
        ),
        planning=project_planning(base),
        transfers=project_transfers(base),
        actor_location_id=substitute.location_id,
        counterparty_location_id=substitute.location_id,
        actual_revision=revision + len(output),
        simulated_at=at,
    )
    output.extend(offered.events)
    if not offered.accepted:
        return output
    base = [*history, *output]
    accepted = resolve_transfer_response(
        TransferResponseProposal(
            f"accept-{offer_id}",
            offer_id,
            "pathos",
            TransferResponse.ACCEPT,
            "Pathos explicitly accepted responsibility for the temporary object.",
            revision + len(output),
        ),
        planning=project_planning(base),
        transfers=project_transfers(base),
        actor_location_id=substitute.location_id,
        counterparty_location_id=substitute.location_id,
        actual_revision=revision + len(output),
        simulated_at=at,
    )
    output.extend(accepted.events)
    if accepted.accepted:
        custody = next(event for event in accepted.events if event.kind == "object.custody_changed")
        loaned = DomainEvent(
            "object.recovery_loaned",
            "pathos",
            {
                "offer_id": offer_id,
                "object_id": substitute.object_id,
                "owner_id": owner.actor_id,
                "due_at": (at + timedelta(days=2)).isoformat(),
                "simulated_at": at.isoformat(),
            },
            causation_id=custody.event_id,
            correlation_id=correlation,
        )
        output.extend(
            [
                loaned,
                DomainEvent(
                    "memory.recorded",
                    "pathos",
                    {
                        "text": f"{owner.actor_id.title()} lent me {substitute.name} temporarily.",
                        "owner": "pathos",
                        "category": "object-transfer",
                        "source": "deterministic-consequence",
                        "source_event_id": str(loaned.event_id),
                        "object_id": substitute.object_id,
                        "person_id": owner.actor_id,
                        "location_id": substitute.location_id,
                        "importance": 0.62,
                        "confidence": 1.0,
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=loaned.event_id,
                    correlation_id=correlation,
                ),
            ]
        )
    return output


def _return_due_loan(
    history: Sequence[DomainEvent],
    at: datetime,
    revision: int,
    planning: PlanningState,
    locations: Mapping[str, str],
) -> list[DomainEvent]:
    returned = {
        str(event.payload["object_id"])
        for event in history
        if event.kind == "object.recovery_loan_returned"
    }
    loan = next(
        (
            event
            for event in history
            if event.kind == "object.recovery_loaned"
            and str(event.payload["object_id"]) not in returned
            and datetime.fromisoformat(str(event.payload["due_at"])) <= at
        ),
        None,
    )
    if loan is None:
        return []
    object_id, owner_id = str(loan.payload["object_id"]), str(loan.payload["owner_id"])
    item = planning.objects.get(object_id)
    if (
        item is None
        or item.custodian_id != "pathos"
        or locations.get("pathos") != item.location_id
        or locations.get(owner_id) != item.location_id
    ):
        if any(
            event.kind == "object.loan_return_overdue"
            and event.payload.get("source_loan_id") == str(loan.event_id)
            for event in history
        ):
            return []
        overdue = DomainEvent(
            "object.loan_return_overdue",
            "pathos",
            {
                "source_loan_id": str(loan.event_id),
                "object_id": object_id,
                "owner_id": owner_id,
                "due_at": str(loan.payload["due_at"]),
                "reason": "The agreed return time passed before borrower and owner met again.",
                "simulated_at": at.isoformat(),
            },
            causation_id=loan.event_id,
            correlation_id=loan.correlation_id,
        )
        relationship = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": owner_id,
                "evidence_actor_id": "pathos",
                "trust_delta": -0.03,
                "tension_delta": 0.04,
                "reason": "Pathos still held a borrowed object after its agreed return time.",
                "simulated_at": at.isoformat(),
            },
            causation_id=overdue.event_id,
            correlation_id=loan.correlation_id,
        )
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": f"I still owe {owner_id.title()} the return of {item.name if item else object_id}.",
                "owner": "pathos",
                "category": "commitment",
                "source": "deterministic-consequence",
                "source_event_id": str(overdue.event_id),
                "object_id": object_id,
                "person_id": owner_id,
                "importance": 0.78,
                "confidence": 1.0,
                "simulated_at": at.isoformat(),
            },
            causation_id=overdue.event_id,
            correlation_id=loan.correlation_id,
        )
        return [overdue, relationship, memory]
    offer_id = f"return-{loan.payload['offer_id']}"
    offered = resolve_transfer_offer(
        TransferOfferProposal(
            f"offer-{offer_id}",
            offer_id,
            "pathos",
            owner_id,
            object_id,
            TransferKind.RETURN,
            "Return the temporary substitute after two days.",
            revision,
        ),
        planning=planning,
        transfers=project_transfers(history),
        actor_location_id=item.location_id,
        counterparty_location_id=item.location_id,
        actual_revision=revision,
        simulated_at=at,
    )
    output = list(offered.events)
    if not offered.accepted:
        return output
    base = [*history, *output]
    accepted = resolve_transfer_response(
        TransferResponseProposal(
            f"accept-{offer_id}",
            offer_id,
            owner_id,
            TransferResponse.ACCEPT,
            "The owner accepted the returned substitute.",
            revision + len(output),
        ),
        planning=project_planning(base),
        transfers=project_transfers(base),
        actor_location_id=item.location_id,
        counterparty_location_id=item.location_id,
        actual_revision=revision + len(output),
        simulated_at=at,
    )
    output.extend(accepted.events)
    if accepted.accepted:
        custody = next(event for event in accepted.events if event.kind == "object.custody_changed")
        returned_event = DomainEvent(
            "object.recovery_loan_returned",
            "pathos",
            {"object_id": object_id, "owner_id": owner_id, "simulated_at": at.isoformat()},
            causation_id=custody.event_id,
            correlation_id=loan.correlation_id,
        )
        output.extend(
            [
                returned_event,
                DomainEvent(
                    "memory.recorded",
                    "pathos",
                    {
                        "text": f"I returned the temporary {item.name} to {owner_id.title()}.",
                        "owner": "pathos",
                        "category": "object-transfer",
                        "source": "deterministic-consequence",
                        "source_event_id": str(returned_event.event_id),
                        "object_id": object_id,
                        "person_id": owner_id,
                        "location_id": item.location_id,
                        "importance": 0.5,
                        "confidence": 1.0,
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=returned_event.event_id,
                    correlation_id=loan.correlation_id,
                ),
            ]
        )
    return output


def _pending_replacement(history: Sequence[DomainEvent]) -> DomainEvent | None:
    terminal = {
        str(event.payload["replacement_id"])
        for event in history
        if event.kind in {"object.replacement_received", "object.replacement_cancelled"}
    }
    latest: dict[str, DomainEvent] = {}
    for event in history:
        if event.kind == "object.replacement_ordered":
            latest[str(event.payload["replacement_id"])] = event
    return next((event for key, event in latest.items() if key not in terminal), None)


def _replacement_handoff(
    history: Sequence[DomainEvent],
    order: DomainEvent,
    at: datetime,
    planning: PlanningState,
    pathos_location: str,
) -> list[DomainEvent]:
    replacement_id = str(order.payload["replacement_id"])
    original = planning.objects.get(str(order.payload["object_id"]))
    if original is None:
        return []
    attempt = int(order.payload["attempt"])
    if pathos_location != original.location_id:
        missed = DomainEvent(
            "object.replacement_missed",
            "pathos",
            {
                "replacement_id": replacement_id,
                "object_id": original.object_id,
                "attempt": attempt,
                "simulated_at": at.isoformat(),
            },
            causation_id=order.event_id,
            correlation_id=order.correlation_id,
        )
        if attempt >= 2:
            cancelled = DomainEvent(
                "object.replacement_cancelled",
                "pathos",
                {
                    "replacement_id": replacement_id,
                    "object_id": original.object_id,
                    "reason": "Both replacement handoffs were missed.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=missed.event_id,
                correlation_id=order.correlation_id,
            )
            return [missed, cancelled]
        retry = DomainEvent(
            "object.replacement_ordered",
            "pathos",
            {
                **dict(order.payload),
                "attempt": 2,
                "due_at": (at + timedelta(days=1)).isoformat(),
                "simulated_at": at.isoformat(),
            },
            causation_id=missed.event_id,
            correlation_id=order.correlation_id,
        )
        return [missed, retry]
    received = DomainEvent(
        "object.replacement_received",
        "pathos",
        {
            "replacement_id": replacement_id,
            "object_id": original.object_id,
            "new_object_id": replacement_id,
            "attempt": attempt,
            "simulated_at": at.isoformat(),
        },
        causation_id=order.event_id,
        correlation_id=order.correlation_id,
    )
    registered = DomainEvent(
        "object.registered",
        "pathos",
        {
            "object_id": replacement_id,
            "name": f"Replacement for {original.name}",
            "owner_id": original.owner_id,
            "custodian_id": original.custodian_id,
            "location_id": original.location_id,
            "condition": "good",
            "source": "replacement-lifecycle",
            "replacement_for": original.object_id,
            "simulated_at": at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=order.correlation_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": f"A distinct replacement for {original.name} arrived.",
            "owner": "pathos",
            "category": "object-transfer",
            "source": "deterministic-consequence",
            "source_event_id": str(received.event_id),
            "object_id": replacement_id,
            "location_id": original.location_id,
            "importance": 0.58,
            "confidence": 1.0,
            "simulated_at": at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=order.correlation_id,
    )
    return [received, registered, memory]


def _bounded(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.5
    return max(0.0, min(1.0, float(value)))


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
