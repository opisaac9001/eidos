"""A small authored causal fixture that exercises planning across two days."""

from datetime import datetime, timedelta

from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import project_planning


def story_events(
    current: datetime, existing: list[DomainEvent], actor_location_id: str
) -> list[DomainEvent]:
    day = (current.date() - datetime(2026, 1, 1).date()).days + 1
    kinds = {event.kind for event in existing}
    at = current.isoformat()
    if day == 1 and current.hour == 9 and "commitment.created" not in kinds:
        due = (current + timedelta(days=1)).replace(hour=17).isoformat()
        work = (current + timedelta(days=1)).replace(hour=10).isoformat()
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
                "goal.activated",
                "pathos",
                {
                    "goal_id": "repair-mara-lamp",
                    "title": "Repair Mara's brass lamp",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "commitment.created",
                "pathos",
                {
                    "commitment_id": "promise-mara-lamp",
                    "title": "Repair Mara's lamp by tomorrow evening",
                    "debtor_id": "pathos",
                    "creditor_id": "mara",
                    "due_at": due,
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "repair-mara-lamp-slot",
                    "title": "Work on Mara's lamp",
                    "starts_at": work,
                    "location_id": "workshop",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "concern.opened",
                "pathos",
                {
                    "concern_id": "finish-mara-lamp",
                    "text": "I promised Mara I would repair her lamp by tomorrow evening.",
                    "simulated_at": at,
                    "source_event_id": str(request.event_id),
                },
            ),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "Mara asked me to repair her small brass lamp, and I promised it by tomorrow evening.",
                    "simulated_at": at,
                    "source": "authored-first-story",
                    "source_event_id": str(request.event_id),
                    "category": "commitment",
                    "location_id": "cafe",
                    "person_id": "mara",
                    "object_id": "mara-lamp",
                    "goal_id": "repair-mara-lamp",
                    "owner": "pathos",
                    "importance": 0.9,
                    "confidence": 1.0,
                },
            ),
        ]
        intention = resolve_intention(
            IntentionProposal(
                proposal_id="choose-repair-mara-lamp",
                intention_id="repair-mara-lamp-next",
                actor_id="pathos",
                action=ActionKind.REPAIR,
                motivation="Keep my promise to Mara and restore something she values.",
                priority=0.9,
                expected_revision=len(existing) + len(foundation),
                goal_id="repair-mara-lamp",
                target_id="mara-lamp",
            ),
            state=project_planning(existing + foundation),
            actual_revision=len(existing) + len(foundation),
            simulated_at=current,
        )
        return [*foundation, *intention.events]
    if day == 2 and current.hour == 10 and "schedule.interrupted" not in kinds:
        return [
            DomainEvent(
                "schedule.interrupted",
                "pathos",
                {
                    "schedule_id": "repair-mara-lamp-slot",
                    "reason": "The lamp needs a replacement switch.",
                    "simulated_at": at,
                },
            ),
            DomainEvent(
                "schedule.rescheduled",
                "pathos",
                {
                    "schedule_id": "repair-mara-lamp-slot",
                    "starts_at": current.replace(hour=14).isoformat(),
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
                    "goal_id": "repair-mara-lamp",
                    "owner": "pathos",
                    "importance": 0.75,
                    "confidence": 1.0,
                },
            ),
        ]
    if day == 2 and current.hour == 14 and "commitment.fulfilled" not in kinds:
        proposal = ActionProposal(
            proposal_id="repair-mara-lamp-at-rescheduled-time",
            actor_id="pathos",
            action=ActionKind.REPAIR,
            expected_revision=len(existing),
            target_id="mara-lamp",
            schedule_id="repair-mara-lamp-slot",
            intention_id="repair-mara-lamp-next",
        )
        resolution = resolve_action(
            proposal,
            state=project_planning(existing),
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
                {"commitment_id": "promise-mara-lamp", "simulated_at": at},
            ),
            DomainEvent(
                "goal.achieved", "pathos", {"goal_id": "repair-mara-lamp", "simulated_at": at}
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
                    "goal_id": "repair-mara-lamp",
                    "owner": "pathos",
                    "importance": 0.9,
                    "confidence": 1.0,
                },
            ),
        ]
    return []
