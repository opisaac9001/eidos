"""Replay-stable outbound invitations grounded in remembered social follow-ups."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.followups import project_followups
from eidos.application.planner import plan_accepted_work
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState
from eidos.domain.social import (
    SocialMove,
    SocialMoveProposal,
    SocialRequest,
    project_social,
    resolve_social_move,
)
from eidos.domain.world_catalog import WorldCatalog


def follow_up_invitation_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    pathos_awake: bool,
    pathos_energy: float,
    social_openness: float,
    npc_people: Mapping[str, NPCState],
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Let one ready reminder become a mutually decided, feasible invitation."""
    if (
        not pathos_awake
        or not 9 <= simulated_at.hour < 18
        or pathos_energy < 0.3
        or social_openness < 0.3
    ):
        return []
    handled = {
        str(event.payload["source_follow_up_id"])
        for event in history
        if event.kind == "invitation.made"
        and isinstance(event.payload.get("source_follow_up_id"), str)
    }
    follow_up = next(
        (
            item
            for item in project_followups(history).values()
            if item.status == "ready"
            and item.follow_up_id not in handled
            and item.person_id in npc_people
        ),
        None,
    )
    if follow_up is None:
        return []
    person = npc_people[follow_up.person_id]
    location_id = person.usual_location_id
    if location_id == "home" or location_id not in catalog.places:
        location_id = "park" if "park" in catalog.places else next(iter(catalog.places))
    request = _feasible_request(
        follow_up.follow_up_id,
        follow_up.person_id,
        location_id,
        simulated_at,
        planning,
        catalog,
    )
    if request is None:
        return []
    ready = next(
        event
        for event in reversed(history)
        if event.kind == "follow_up.ready"
        and event.payload.get("follow_up_id") == follow_up.follow_up_id
    )
    invitation_id = f"invitation-{follow_up.follow_up_id}"
    invitation = DomainEvent(
        "invitation.made",
        "pathos",
        {
            "invitation_id": invitation_id,
            "source_follow_up_id": follow_up.follow_up_id,
            "inviter_id": "pathos",
            "invitee_id": follow_up.person_id,
            "person_id": follow_up.person_id,
            "location_id": location_id,
            "starts_at": request.earliest_start,
            "text": (
                f"Pathos invited {follow_up.person_id.replace('-', ' ').title()} "
                "to spend some time together."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=ready.event_id,
        correlation_id=invitation_id,
    )
    opened = DomainEvent(
        "social.request_opened",
        "pathos",
        {
            "request_id": request.request_id,
            "requester_id": request.requester_id,
            "responder_id": request.responder_id,
            "action": request.action,
            "target_id": request.target_id,
            "title": request.title,
            "due_at": request.due_at,
            "earliest_start": request.earliest_start,
            "location_id": request.location_id,
            "duration_hours": request.duration_hours,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=invitation.event_id,
        correlation_id=invitation_id,
    )
    social = project_social([*history, invitation, opened])
    capacity = 0.45 * person.energy + 0.35 * person.connection + 0.2 * person.purpose
    accepts = _sample(invitation_id) < max(0.05, min(0.95, capacity))
    move = SocialMove.ACCEPT if accepts else SocialMove.DECLINE
    response = resolve_social_move(
        SocialMoveProposal(
            f"respond-{invitation_id}",
            request.request_id,
            follow_up.person_id,
            move,
            (
                "The invitation fits my current energy and desire for company."
                if accepts
                else "I do not have enough capacity to make this plan right now."
            ),
            actual_revision + 2,
        ),
        state=social,
        actual_revision=actual_revision + 2,
        simulated_at=simulated_at,
    )
    output = [invitation, opened, *response.events]
    response_event = response.events[-1]
    outcome = DomainEvent(
        "invitation.accepted" if accepts else "invitation.declined",
        "pathos",
        {
            "invitation_id": invitation_id,
            "person_id": follow_up.person_id,
            "request_id": request.request_id,
            "reason": str(response_event.payload["reason"]),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=response_event.event_id,
        correlation_id=invitation_id,
    )
    output.append(outcome)
    if not accepts:
        return output
    accepted_request = project_social([*history, *output]).requests[request.request_id]
    plan = plan_accepted_work(
        accepted_request,
        state=planning,
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at,
        preferred_start=datetime.fromisoformat(request.earliest_start),
        opening_hours=catalog.opening_hours,
        route_minutes=catalog.route_minutes,
    )
    output.extend(plan.events)
    return output


def _feasible_request(
    follow_up_id: str,
    person_id: str,
    location_id: str,
    simulated_at: datetime,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> SocialRequest | None:
    place = catalog.places[location_id]
    hour = min(max(13, place.opens_hour), place.closes_hour - 1)
    for offset in range(1, 6):
        start = (simulated_at + timedelta(days=offset)).replace(
            hour=hour, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=1)
        request = SocialRequest(
            request_id=f"reconnect-{follow_up_id}",
            requester_id="pathos",
            responder_id=person_id,
            action="talk",
            target_id=person_id,
            title=f"Spend time with {person_id.replace('-', ' ').title()}",
            due_at=end.isoformat(),
            earliest_start=start.isoformat(),
            location_id=location_id,
            duration_hours=1,
            awaiting_actor_id=person_id,
            status="accepted",
        )
        if plan_accepted_work(
            request,
            state=planning,
            actual_revision=0,
            simulated_at=simulated_at,
            preferred_start=start,
            opening_hours=catalog.opening_hours,
            route_minutes=catalog.route_minutes,
        ).accepted:
            return request
    return None


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
