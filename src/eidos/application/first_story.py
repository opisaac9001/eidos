"""A small authored causal fixture that exercises planning across two days."""

from datetime import datetime, timedelta
from typing import Mapping

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
from eidos.domain.speech import Privacy, SpeechProposal, resolve_speech


def story_events(
    current: datetime,
    existing: list[DomainEvent],
    actor_location_id: str,
    actor_energy: float,
    actor_rest: float = 0.5,
    actor_mastery: float = 0.5,
    actor_valence: float = 0.0,
    actor_arousal: float = 0.35,
    sustained_low_hours: int = 0,
    actor_values: Mapping[str, float] | None = None,
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
            rest=actor_rest,
            mastery=actor_mastery,
            values=actor_values,
            affect_valence=actor_valence,
            affect_arousal=actor_arousal,
            sustained_low_hours=sustained_low_hours,
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
        interrupted = [
            DomainEvent(
                "schedule.interrupted",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "reason": "The lamp needs a replacement switch.",
                    "simulated_at": at,
                },
            ),
        ]
        speech = resolve_speech(
            SpeechProposal(
                proposal_id="ellis-found-lamp-switch",
                speaker_id="ellis",
                audience_id="pathos",
                text="I found a replacement switch for Mara's lamp. You can use it this afternoon.",
                privacy=Privacy.PRIVATE,
                topic_id="mara-lamp",
                claim_subject_id="mara-lamp",
                claim_predicate="replacement_switch",
                claim_value="available",
                claim_confidence=0.8,
                expected_revision=len(existing) + len(interrupted),
            ),
            history=existing + interrupted,
            actor_locations={"pathos": actor_location_id, "ellis": "workshop"},
            known_actor_ids={"pathos", "mara", "ellis", "rowan"},
            actual_revision=len(existing) + len(interrupted),
            simulated_at=at,
        )
        if not speech.accepted:
            return [*interrupted, *speech.events]
        delivered = next(event for event in speech.events if event.kind == "speech.delivered")
        perceived = next(event for event in speech.events if event.kind == "perception.recorded")
        rescheduled = DomainEvent(
            "schedule.rescheduled",
            "pathos",
            {
                "schedule_id": schedule_id,
                "starts_at": current.replace(hour=14).isoformat(),
                "ends_at": current.replace(hour=17).isoformat(),
                "reason": "Ellis reported an available replacement switch.",
                "simulated_at": at,
            },
            causation_id=delivered.event_id,
            correlation_id=delivered.correlation_id,
        )
        return [
            *interrupted,
            *speech.events,
            rescheduled,
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "The lamp repair was interrupted because it needed a replacement switch; Ellis told me he found one for this afternoon.",
                    "simulated_at": at,
                    "source": "perceived-speech",
                    "source_event_id": str(perceived.event_id),
                    "category": "plan-change",
                    "location_id": "workshop",
                    "person_id": "ellis",
                    "object_id": "mara-lamp",
                    "goal_id": goal_id,
                    "owner": "pathos",
                    "importance": 0.75,
                    "confidence": 0.85,
                },
                causation_id=perceived.event_id,
                correlation_id=delivered.correlation_id,
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
        accepted_action = next(
            event for event in resolution.events if event.kind == "action.accepted"
        )
        return [
            *resolution.events,
            DomainEvent(
                "resource.confirmed",
                "pathos",
                {
                    "subject_id": "mara-lamp",
                    "predicate": "replacement_switch",
                    "object_value": "available",
                    "confidence": 0.95,
                    "simulated_at": at,
                },
                causation_id=accepted_action.event_id,
                correlation_id=accepted_action.correlation_id,
            ),
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
                    "evidence_actor_id": "pathos",
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
    social = project_social(existing)
    if day == 3 and current.hour == 9 and "coffee-with-mara" not in social.requests:
        meeting = (current + timedelta(days=1)).replace(hour=9)
        due = meeting.replace(hour=11)
        request = DomainEvent(
            "social.request_opened",
            "pathos",
            {
                "request_id": "coffee-with-mara",
                "requester_id": "mara",
                "responder_id": "pathos",
                "action": "talk",
                "target_id": "mara",
                "title": "Coffee with Mara",
                "due_at": due.isoformat(),
                "earliest_start": meeting.isoformat(),
                "location_id": "cafe",
                "duration_hours": 1,
                "simulated_at": at,
            },
        )
        opened = [
            DomainEvent(
                "invitation.made",
                "pathos",
                {
                    "person_id": "mara",
                    "text": "Mara invited Pathos to sit for coffee the next morning.",
                    "simulated_at": at,
                },
            ),
            request,
        ]
        pending_social = project_social(existing + opened)
        choice = choose_request_response(
            pending_social.requests["coffee-with-mara"],
            actor_id="pathos",
            energy=actor_energy,
            rest=actor_rest,
            mastery=actor_mastery,
            values=actor_values,
            affect_valence=actor_valence,
            affect_arousal=actor_arousal,
            sustained_low_hours=sustained_low_hours,
            expected_revision=len(existing) + len(opened),
        )
        response = resolve_social_move(
            choice,
            state=pending_social,
            actual_revision=len(existing) + len(opened),
            simulated_at=current,
        )
        exchange = [*opened, *response.events]
        accepted = project_social(existing + exchange).requests["coffee-with-mara"]
        if accepted.status != "accepted":
            return exchange
        plan = plan_accepted_work(
            accepted,
            state=project_planning(existing + exchange),
            actual_revision=len(existing) + len(exchange),
            simulated_at=current,
            preferred_start=meeting,
        )
        return [
            *exchange,
            *plan.events,
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "Mara invited me to coffee tomorrow, and I chose to make time for it.",
                    "simulated_at": at,
                    "source": "authored-first-story",
                    "source_event_id": str(request.event_id),
                    "category": "commitment",
                    "location_id": "cafe",
                    "person_id": "mara",
                    "goal_id": "coffee-with-mara-goal",
                    "owner": "pathos",
                    "importance": 0.7,
                    "confidence": 1.0,
                },
            ),
        ]
    return []
