"""Replay-stable resident invitations with delayed, independent Pathos consent."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import AbstractSet, Mapping, Sequence

from eidos.application.planner import plan_accepted_work
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState
from eidos.domain.social import (
    SocialMove,
    SocialMoveProposal,
    choose_request_response,
    project_social,
    resolve_social_move,
)
from eidos.domain.world_catalog import WorldCatalog


def resident_invitation_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    *,
    known_person_ids: AbstractSet[str],
    npc_people: Mapping[str, NPCState],
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Allow at most one known resident to originate an ordinary invitation."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Invitation time must be timezone-aware")
    if simulated_at.hour != 11:
        return []
    recent_cutoff = simulated_at - timedelta(days=8)
    recent = [
        event
        for event in history
        if event.kind == "invitation.made"
        and event.payload.get("invitee_id") == "pathos"
        and _event_time(event) >= recent_cutoff
    ]
    if recent:
        return []
    inviter_cutoff = simulated_at - timedelta(days=24)
    recent_inviters = {
        str(event.payload["inviter_id"])
        for event in history
        if event.kind == "invitation.made"
        and event.payload.get("invitee_id") == "pathos"
        and isinstance(event.payload.get("inviter_id"), str)
        and _event_time(event) >= inviter_cutoff
    }
    candidates = sorted(
        person_id
        for person_id in known_person_ids
        if person_id in npc_people
        and person_id in catalog.people
        and person_id not in recent_inviters
        and _social_capacity(npc_people[person_id]) >= 0.35
    )
    if not candidates:
        return []
    person_id = max(
        candidates,
        key=lambda candidate: (
            0.6 * _sample(f"resident-inviter:{simulated_at.date()}:{candidate}")
            + 0.4 * _social_capacity(npc_people[candidate])
        ),
    )
    person = npc_people[person_id]
    if _sample(f"resident-invitation-day:{simulated_at.date()}") >= (
        0.15 + 0.4 * _social_capacity(person)
    ):
        return []
    location_id = _public_location(person, person_id, catalog)
    place = catalog.places[location_id]
    hour = min(max(11, place.opens_hour), place.closes_hour - 1)
    starts_at = (simulated_at + timedelta(days=2)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    ends_at = starts_at + timedelta(hours=1)
    invitation_id = f"resident-invitation-{person_id}-{simulated_at.date()}"
    request_id = f"request-{invitation_id}"
    response_due = simulated_at + timedelta(
        hours=1 + int(_sample(f"response-delay:{invitation_id}") * 5)
    )
    invitation = DomainEvent(
        "invitation.made",
        "pathos",
        {
            "invitation_id": invitation_id,
            "request_id": request_id,
            "inviter_id": person_id,
            "invitee_id": "pathos",
            "person_id": person_id,
            "location_id": location_id,
            "starts_at": starts_at.isoformat(),
            "response_due_at": response_due.isoformat(),
            "text": f"{catalog.people[person_id].name} invited Pathos to spend some time together.",
            "simulated_at": simulated_at.isoformat(),
        },
        correlation_id=invitation_id,
    )
    opened = DomainEvent(
        "social.request_opened",
        "pathos",
        {
            "request_id": request_id,
            "requester_id": person_id,
            "responder_id": "pathos",
            "action": "talk",
            "target_id": person_id,
            "title": f"Spend time with {catalog.people[person_id].name}",
            "due_at": ends_at.isoformat(),
            "earliest_start": starts_at.isoformat(),
            "location_id": location_id,
            "duration_hours": 1,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=invitation.event_id,
        correlation_id=invitation_id,
    )
    return [invitation, opened]


def pathos_invitation_response_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    pathos_awake: bool,
    pathos_available: bool,
    energy: float,
    rest: float,
    mastery: float,
    values: Mapping[str, float],
    affect_valence: float,
    affect_arousal: float,
    sustained_low_hours: int,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Let Pathos answer one due resident invitation from his own present capacity."""
    if not pathos_awake or not pathos_available:
        return []
    social = project_social(history)
    invitation = next(
        (
            event
            for event in history
            if event.kind == "invitation.made"
            and event.payload.get("invitee_id") == "pathos"
            and isinstance(event.payload.get("request_id"), str)
            and _aware_payload_time(event, "response_due_at") <= simulated_at
            and (request := social.requests.get(str(event.payload["request_id"]))) is not None
            and request.status == "pending"
            and request.awaiting_actor_id == "pathos"
        ),
        None,
    )
    if invitation is None:
        return []
    request_id = str(invitation.payload["request_id"])
    request = social.requests[request_id]
    choice = choose_request_response(
        request,
        actor_id="pathos",
        energy=energy,
        rest=rest,
        mastery=mastery,
        values=values,
        affect_valence=affect_valence,
        affect_arousal=affect_arousal,
        sustained_low_hours=sustained_low_hours,
        expected_revision=actual_revision,
    )
    if choice.move is SocialMove.ACCEPT:
        feasibility = plan_accepted_work(
            replace(request, status="accepted"),
            state=planning,
            actual_revision=0,
            simulated_at=simulated_at,
            preferred_start=datetime.fromisoformat(request.earliest_start),
            opening_hours=catalog.opening_hours,
            route_minutes=catalog.route_minutes,
        )
        if not feasibility.accepted:
            choice = SocialMoveProposal(
                choice.proposal_id,
                choice.request_id,
                choice.actor_id,
                SocialMove.DECLINE,
                f"The invitation does not fit my actual calendar: {feasibility.explanation}",
                choice.expected_revision,
            )
    resolution = resolve_social_move(
        choice,
        state=social,
        actual_revision=actual_revision,
        simulated_at=simulated_at,
    )
    if not resolution.accepted:
        return list(resolution.events)
    response_event = resolution.events[-1]
    accepted = choice.move is SocialMove.ACCEPT
    outcome = DomainEvent(
        "invitation.accepted" if accepted else "invitation.declined",
        "pathos",
        {
            "invitation_id": invitation.payload["invitation_id"],
            "request_id": request_id,
            "person_id": invitation.payload["inviter_id"],
            "reason": response_event.payload.get("reason", choice.reason),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=response_event.event_id,
        correlation_id=invitation.correlation_id,
    )
    output = [*resolution.events, outcome]
    if not accepted:
        return output
    accepted_request = project_social([*history, *output]).requests[request_id]
    plan = plan_accepted_work(
        accepted_request,
        state=planning,
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at,
        preferred_start=datetime.fromisoformat(accepted_request.earliest_start),
        opening_hours=catalog.opening_hours,
        route_minutes=catalog.route_minutes,
    )
    output.extend(plan.events)
    return output


def _public_location(person: NPCState, person_id: str, catalog: WorldCatalog) -> str:
    for candidate in (person.location_id, person.usual_location_id):
        if candidate in catalog.places and candidate != "home":
            return candidate
    public = sorted(place_id for place_id in catalog.places if place_id != "home")
    if not public:
        return next(iter(catalog.places))
    return public[int(_sample(f"invitation-place:{person_id}") * len(public)) % len(public)]


def _event_time(event: DomainEvent) -> datetime:
    return _aware_payload_time(event, "simulated_at")


def _aware_payload_time(event: DomainEvent, field: str) -> datetime:
    value = event.payload.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} is required")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _social_capacity(person: NPCState) -> float:
    return 0.45 * person.energy + 0.35 * person.connection + 0.2 * person.purpose
