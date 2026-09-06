"""A small authored causal fixture that exercises planning across two days."""

from datetime import datetime, timedelta

from eidos.application.planner import plan_accepted_work
from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.social import (
    SocialMove,
    SocialMoveProposal,
    choose_request_response,
    project_social,
    resolve_social_move,
)


def story_events(
    current: datetime,
    existing: list[DomainEvent],
    actor_location_id: str,
    actor_energy: float,
) -> list[DomainEvent]:
    day = (current.date() - datetime(2026, 1, 1).date()).days + 1
    kinds = {event.kind for event in existing}
    at = current.isoformat()
    if day == 1 and current.hour == 9 and "commitment.created" not in kinds:
        requested_due = (current + timedelta(days=1)).replace(hour=13)
        work = (current + timedelta(days=1)).replace(hour=10)
        request = DomainEvent(
            "request.made",
            "pathos",
            {
                "person_id": "mara",
                "text": "Mara asked Pathos to repair her small brass lamp.",
                "simulated_at": at,
            },
        )
        foundation = [
            request,
            DomainEvent(
                "object.registered",
                "pathos",
                {
                    "object_id": "mara-lamp",
                    "name": "Mara's brass lamp",
                    "owner_id": "mara",
                    "custodian_id": "pathos",
                    "location_id": "workshop",
                    "condition": "broken",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "social.request_opened",
                "pathos",
                {
                    "request_id": "repair-mara-lamp",
                    "requester_id": "mara",
                    "responder_id": "pathos",
                    "action": "repair",
                    "target_id": "mara-lamp",
                    "title": "Repair Mara's brass lamp",
                    "due_at": requested_due.isoformat(),
                    "earliest_start": work.isoformat(),
                    "location_id": "workshop",
                    "duration_hours": 4,
                    "simulated_at": at,
                },
            ),
        ]
        social = project_social(existing + foundation)
        open_request = social.requests["repair-mara-lamp"]
        choice = choose_request_response(
            open_request,
            actor_id="pathos",
            energy=actor_energy,
            expected_revision=len(existing) + len(foundation),
        )
        response = resolve_social_move(
            choice,
            state=social,
            actual_revision=len(existing) + len(foundation),
            simulated_at=current,
        )
        if not response.accepted:
            return [*foundation, *response.events]
        exchange = [*foundation, *response.events]
        social = project_social(existing + exchange)
        if choice.move is SocialMove.NEGOTIATE:
            acceptance = resolve_social_move(
                SocialMoveProposal(
                    proposal_id="mara-accepts-later-lamp-deadline",
                    request_id="repair-mara-lamp",
                    actor_id="mara",
                    move=SocialMove.ACCEPT,
                    reason="The later deadline still meets Mara's need.",
                    expected_revision=len(existing) + len(exchange),
                ),
                state=social,
                actual_revision=len(existing) + len(exchange),
                simulated_at=current,
            )
            exchange.extend(acceptance.events)
            social = project_social(existing + exchange)
        accepted_request = social.requests["repair-mara-lamp"]
        plan = plan_accepted_work(
            accepted_request,
            state=project_planning(existing + exchange),
            actual_revision=len(existing) + len(exchange),
            simulated_at=current,
            preferred_start=work,
        )
        if not plan.accepted:
            return [*exchange, *plan.events]
        goal_id = "repair-mara-lamp-goal"
        return [
            *exchange,
            *plan.events,
            DomainEvent(
                "concern.opened",
                "pathos",
                {
                    "concern_id": "finish-mara-lamp",
                    "text": "I explicitly agreed with Mara to repair her lamp by tomorrow evening.",
                    "simulated_at": at,
                    "source_event_id": str(request.event_id),
                },
            ),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "Mara and I negotiated the timing, then I explicitly promised to repair her small brass lamp by tomorrow evening.",
                    "simulated_at": at,
                    "source": "authored-first-story",
                    "source_event_id": str(request.event_id),
                    "category": "commitment",
                    "location_id": "cafe",
                    "person_id": "mara",
                    "object_id": "mara-lamp",
                    "goal_id": goal_id,
                    "owner": "pathos",
                    "importance": 0.9,
                    "confidence": 1.0,
                },
            ),
        ]
    if day == 2 and current.hour == 10 and "schedule.interrupted" not in kinds:
        planning = project_planning(existing)
        legacy = "repair-mara-lamp-slot" in planning.calendar
        schedule_id = "repair-mara-lamp-slot" if legacy else "repair-mara-lamp-schedule"
        goal_id = "repair-mara-lamp" if legacy else "repair-mara-lamp-goal"
        return [
            DomainEvent(
                "schedule.interrupted",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "reason": "The lamp needs a replacement switch.",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "schedule.rescheduled",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "starts_at": current.replace(hour=14).isoformat(),
                    "ends_at": current.replace(hour=17).isoformat(),
                    "reason": "Ellis found a spare switch.",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "The lamp repair was interrupted because it needed a replacement switch; Ellis found one for this afternoon.",
                    "simulated_at": at,
                    "source": "authored-first-story",
                    "category": "plan-change",
                    "location_id": "workshop",
                    "object_id": "mara-lamp",
                    "goal_id": goal_id,
                    "owner": "pathos",
                    "importance": 0.75,
                    "confidence": 1.0,
                },
            ),
        ]
    if day == 2 and current.hour == 17 and "commitment.fulfilled" not in kinds:
        planning = project_planning(existing)
        legacy = "repair-mara-lamp-slot" in planning.calendar
        schedule_id = "repair-mara-lamp-slot" if legacy else "repair-mara-lamp-schedule"
        intention_id = "repair-mara-lamp-next" if legacy else "repair-mara-lamp-intention"
        commitment_id = "promise-mara-lamp" if legacy else "repair-mara-lamp-commitment"
        goal_id = "repair-mara-lamp" if legacy else "repair-mara-lamp-goal"
        proposal = ActionProposal(
            proposal_id="repair-mara-lamp-at-rescheduled-time",
            actor_id="pathos",
            action=ActionKind.REPAIR,
            expected_revision=len(existing),
            target_id="mara-lamp",
            schedule_id=schedule_id,
            intention_id=intention_id,
        )
        resolution = resolve_action(
            proposal,
            state=planning,
            actor_location_id=actor_location_id,
            actual_revision=len(existing),
            simulated_at=current,
        )
        if not resolution.accepted:
            return list(resolution.events)
        return [
            *resolution.events,
            DomainEvent(
                "commitment.fulfilled",
                "pathos",
                {"commitment_id": commitment_id, "simulated_at": at},
            ),
            DomainEvent(
                "goal.achieved",
                "pathos",
                {"goal_id": goal_id, "simulated_at": at},
            ),
            DomainEvent(
                "concern.resolved", "pathos", {"concern_id": "finish-mara-lamp", "simulated_at": at}
            ),
            DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": "mara",
                    "trust_delta": 0.08,
                    "familiarity_delta": 0.04,
                    "reason": "Pathos kept the lamp-repair promise.",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "I repaired Mara's brass lamp after Ellis found a replacement switch, keeping my promise before the deadline.",
                    "simulated_at": at,
                    "source": "authored-first-story",
                    "category": "accomplishment",
                    "location_id": "workshop",
                    "person_id": "mara",
                    "object_id": "mara-lamp",
                    "goal_id": goal_id,
                    "owner": "pathos",
                    "importance": 0.9,
                    "confidence": 1.0,
                },
            ),
        ]
    return []
