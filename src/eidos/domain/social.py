"""Bounded social requests with explicit consent and negotiated terms."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold
from eidos.domain.proposals import ProposalRejected


class SocialMove(StrEnum):
    ACCEPT = "accept"
    DECLINE = "decline"
    NEGOTIATE = "negotiate"


@dataclass(frozen=True, slots=True)
class SocialRequest:
    request_id: str
    requester_id: str
    responder_id: str
    action: str
    target_id: str
    title: str
    due_at: str
    earliest_start: str
    location_id: str
    duration_hours: float
    awaiting_actor_id: str
    status: str = "pending"
    rounds: int = 0


@dataclass(frozen=True, slots=True)
class SocialState:
    requests: Mapping[str, SocialRequest]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requests", MappingProxyType(dict(self.requests)))

    @classmethod
    def empty(cls) -> SocialState:
        return cls({})

    def apply(self, event: DomainEvent) -> SocialState:
        requests = dict(self.requests)
        payload = event.payload
        if event.kind == "social.request_opened":
            request_id = _required(payload, "request_id")
            if request_id in requests:
                raise ValueError("Social request already exists")
            duration = payload.get("duration_hours")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or duration <= 0
            ):
                raise ValueError("Request duration must be positive")
            requester = _required(payload, "requester_id")
            due_at = _aware_time(payload, "due_at")
            earliest_start = _aware_time(payload, "earliest_start")
            if due_at <= earliest_start:
                raise ValueError("Request deadline must follow its earliest start")
            requests[request_id] = SocialRequest(
                request_id=request_id,
                requester_id=requester,
                responder_id=_required(payload, "responder_id"),
                action=_required(payload, "action"),
                target_id=_required(payload, "target_id"),
                title=_required(payload, "title"),
                due_at=due_at.isoformat(),
                earliest_start=earliest_start.isoformat(),
                location_id=_required(payload, "location_id"),
                duration_hours=float(duration),
                awaiting_actor_id=_required(payload, "responder_id"),
            )
        elif event.kind == "social.request_negotiated":
            request = _existing(requests, payload)
            if request.status != "pending":
                raise ValueError("Only pending requests can be negotiated")
            actor_id = _required(payload, "actor_id")
            if actor_id != request.awaiting_actor_id:
                raise ValueError("Only the awaited actor can negotiate")
            if request.rounds >= 3:
                raise ValueError("Negotiation round limit reached")
            counter_due = _aware_time(payload, "counter_due_at")
            if counter_due <= datetime.fromisoformat(request.due_at):
                raise ValueError("Counter deadline must allow more time")
            awaiting = (
                request.requester_id if actor_id == request.responder_id else request.responder_id
            )
            requests[request.request_id] = replace(
                request,
                due_at=counter_due.isoformat(),
                awaiting_actor_id=awaiting,
                rounds=request.rounds + 1,
            )
        elif event.kind in {"social.request_accepted", "social.request_declined"}:
            request = _existing(requests, payload)
            if request.status != "pending":
                raise ValueError("Only pending requests can receive a response")
            if _required(payload, "actor_id") != request.awaiting_actor_id:
                raise ValueError("Only the awaited actor can respond")
            if (
                event.kind == "social.request_accepted"
                and _required(payload, "agreed_due_at") != request.due_at
            ):
                raise ValueError("Acceptance must preserve the current negotiated deadline")
            status = "accepted" if event.kind.endswith("accepted") else "declined"
            requests[request.request_id] = replace(request, status=status)
        return SocialState(requests)


@dataclass(frozen=True, slots=True)
class SocialMoveProposal:
    proposal_id: str
    request_id: str
    actor_id: str
    move: SocialMove
    reason: str
    expected_revision: int
    counter_due_at: datetime | None = None
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class SocialResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "request_id",
    "actor_id",
    "move",
    "reason",
    "expected_revision",
    "counter_due_at",
}


def parse_social_move(content: str) -> SocialMoveProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Social move was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Social move fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Social move schema is not supported")
    for field in ("proposal_id", "request_id", "actor_id", "reason"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        move = SocialMove(value["move"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_social_move", "Social move is not supported") from None
    counter = None
    if value["counter_due_at"] is not None:
        try:
            counter = datetime.fromisoformat(value["counter_due_at"])
        except (TypeError, ValueError):
            raise ProposalRejected(
                "invalid_deadline", "Counter deadline must be ISO time"
            ) from None
        if counter.utcoffset() is None:
            raise ProposalRejected("invalid_deadline", "Counter deadline needs a timezone")
    if (move is SocialMove.NEGOTIATE) != (counter is not None):
        raise ProposalRejected("invalid_counter", "Only negotiation requires a counter deadline")
    return SocialMoveProposal(
        proposal_id=value["proposal_id"],
        request_id=value["request_id"],
        actor_id=value["actor_id"],
        move=move,
        reason=value["reason"],
        expected_revision=revision,
        counter_due_at=counter,
    )


def resolve_social_move(
    proposal: SocialMoveProposal,
    *,
    state: SocialState,
    actual_revision: int,
    simulated_at: datetime,
) -> SocialResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "request_id": proposal.request_id,
        "actor_id": proposal.actor_id,
        "move": proposal.move.value,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "social.move_proposed", "pathos", common, correlation_id=proposal.proposal_id
    )

    def effect(kind: str, extra: Mapping[str, str]) -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            {**common, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> SocialResolution:
        return SocialResolution(
            False,
            code,
            (proposed, effect("social.move_rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The conversation changed before this response")
    request = state.requests.get(proposal.request_id)
    if request is None:
        return reject("unknown_request", "The request does not exist")
    if request.status != "pending":
        return reject("closed_request", "The request is already closed")
    if proposal.actor_id != request.awaiting_actor_id:
        return reject("wrong_turn", "This actor is not awaited")
    if proposal.move is SocialMove.NEGOTIATE:
        assert proposal.counter_due_at is not None
        if request.rounds >= 3:
            return reject("round_limit", "The bounded negotiation has reached its limit")
        if proposal.counter_due_at <= datetime.fromisoformat(request.due_at):
            return reject("invalid_counter", "A deadline counteroffer must allow more time")
        resolved = effect(
            "social.request_negotiated", {"counter_due_at": proposal.counter_due_at.isoformat()}
        )
    elif proposal.move is SocialMove.ACCEPT:
        resolved = effect("social.request_accepted", {"agreed_due_at": request.due_at})
    else:
        resolved = effect("social.request_declined", {})
    return SocialResolution(True, "accepted", (proposed, resolved))


_SOCIAL_FOLD: IncrementalFold[SocialState] = IncrementalFold(
    lambda: SocialState.empty(), lambda state, event: state.apply(event)
)


def project_social(events: Sequence[DomainEvent]) -> SocialState:
    return _SOCIAL_FOLD(events)


def choose_request_response(
    request: SocialRequest,
    *,
    actor_id: str,
    energy: float,
    expected_revision: int,
    rest: float = 0.5,
    mastery: float = 0.5,
    values: Mapping[str, float] | None = None,
    affect_valence: float = 0.0,
    affect_arousal: float = 0.35,
    sustained_low_hours: int = 0,
) -> SocialMoveProposal:
    """A deterministic baseline policy; models may later propose the same envelope."""
    if actor_id != request.awaiting_actor_id:
        raise ValueError("Only the awaited actor can choose a response")
    if any(not 0 <= value <= 1 for value in (energy, rest, mastery)):
        raise ValueError("Choice dimensions must be between zero and one")
    if (
        isinstance(affect_valence, bool)
        or not isinstance(affect_valence, (int, float))
        or isinstance(affect_arousal, bool)
        or not isinstance(affect_arousal, (int, float))
        or not -1 <= affect_valence <= 1
        or not 0 <= affect_arousal <= 1
    ):
        raise ValueError("Affect dimensions are outside their bounds")
    if (
        isinstance(sustained_low_hours, bool)
        or not isinstance(sustained_low_hours, int)
        or sustained_low_hours < 0
    ):
        raise ValueError("Sustained low mood duration must be non-negative")
    proposal_id = f"respond-{request.request_id}-r{request.rounds}-{actor_id}"
    emotional_adjustment = (
        0.12 * affect_valence
        - 0.12 * max(0.0, affect_arousal - 0.65)
        - min(0.18, sustained_low_hours / 400)
    )
    capacity = 0.5 * energy + 0.3 * rest + 0.2 * mastery + emotional_adjustment
    alignment = _request_value_alignment(request.action, values)
    if capacity < 0.35:
        return SocialMoveProposal(
            proposal_id,
            request.request_id,
            actor_id,
            SocialMove.DECLINE,
            "My current energy, rest, confidence, and emotional capacity do not support this promise.",
            expected_revision,
        )
    if values is not None and alignment < 0.4:
        return SocialMoveProposal(
            proposal_id,
            request.request_id,
            actor_id,
            SocialMove.DECLINE,
            f"This request has low alignment ({alignment:.2f}) with my established values.",
            expected_revision,
        )
    earliest = datetime.fromisoformat(request.earliest_start)
    due = datetime.fromisoformat(request.due_at)
    needed_until = earliest + timedelta(hours=request.duration_hours)
    if needed_until > due:
        return SocialMoveProposal(
            proposal_id,
            request.request_id,
            actor_id,
            SocialMove.NEGOTIATE,
            "The requested window is too short for the work.",
            expected_revision,
            counter_due_at=needed_until + timedelta(hours=3),
        )
    return SocialMoveProposal(
        proposal_id,
        request.request_id,
        actor_id,
        SocialMove.ACCEPT,
        (
            "The request fits my current capacity and available window"
            + (f", with value alignment {alignment:.2f}." if values is not None else ".")
        ),
        expected_revision,
    )


def _request_value_alignment(action: str, values: Mapping[str, float] | None) -> float:
    if values is None:
        return 0.5
    keys = ("care", "reliability", "craft") if action == "repair" else ("care", "curiosity")
    selected = []
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Decision values must contain bounded numeric dimensions")
        selected.append(float(value))
    return sum(selected) / len(selected)


def _required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _existing(requests: dict[str, SocialRequest], payload: Mapping[str, object]) -> SocialRequest:
    request_id = _required(payload, "request_id")
    if request_id not in requests:
        raise ValueError("Unknown social request")
    return requests[request_id]


def _aware_time(payload: Mapping[str, object], key: str) -> datetime:
    value = _required(payload, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{key} must be an ISO timestamp") from None
    if parsed.utcoffset() is None:
        raise ValueError(f"{key} must include a timezone")
    return parsed
