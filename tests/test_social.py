import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.domain.social import (
    SocialMove,
    SocialMoveProposal,
    choose_request_response,
    parse_social_move,
    project_social,
    resolve_social_move,
)


class SocialTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def opened(self):
        return DomainEvent(
            "social.request_opened",
            "pathos",
            {
                "request_id": "lamp-request",
                "requester_id": "mara",
                "responder_id": "pathos",
                "action": "repair",
                "target_id": "lamp",
                "title": "Repair the lamp",
                "due_at": (self.now + timedelta(days=1)).isoformat(),
                "earliest_start": (self.now + timedelta(hours=1)).isoformat(),
                "location_id": "workshop",
                "duration_hours": 4,
            },
        )

    def proposal(self, actor, move, revision, counter=None):
        return SocialMoveProposal(
            proposal_id=f"{actor}-{move}",
            request_id="lamp-request",
            actor_id=actor,
            move=move,
            reason="Explicit choice",
            expected_revision=revision,
            counter_due_at=counter,
        )

    def test_negotiate_then_accept_is_bounded_and_explicit(self):
        events = [self.opened()]
        counter = self.now + timedelta(days=2)
        negotiated = resolve_social_move(
            self.proposal("pathos", SocialMove.NEGOTIATE, 1, counter),
            state=project_social(events),
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertTrue(negotiated.accepted)
        events.extend(negotiated.events)
        state = project_social(events)
        self.assertEqual(state.requests["lamp-request"].awaiting_actor_id, "mara")
        accepted = resolve_social_move(
            self.proposal("mara", SocialMove.ACCEPT, 3),
            state=state,
            actual_revision=3,
            simulated_at=self.now,
        )
        events.extend(accepted.events)
        self.assertEqual(project_social(events).requests["lamp-request"].status, "accepted")
        forged = DomainEvent(
            "social.request_accepted",
            "pathos",
            {
                "request_id": "lamp-request",
                "actor_id": "mara",
                "agreed_due_at": (counter + timedelta(days=1)).isoformat(),
            },
        )
        with self.assertRaises(ValueError):
            project_social(events[:-2] + [forged])

    def test_wrong_actor_stale_and_implicit_counter_are_rejected(self):
        state = project_social([self.opened()])
        wrong = resolve_social_move(
            self.proposal("mara", SocialMove.ACCEPT, 1),
            state=state,
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(wrong.code, "wrong_turn")
        stale = resolve_social_move(
            self.proposal("pathos", SocialMove.ACCEPT, 0),
            state=state,
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(stale.code, "stale_revision")

    def test_json_contract_requires_counter_only_for_negotiation(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "p",
            "request_id": "lamp-request",
            "actor_id": "pathos",
            "move": "accept",
            "reason": "I can do it",
            "expected_revision": 1,
            "counter_due_at": None,
        }
        self.assertEqual(parse_social_move(json.dumps(raw)).move, SocialMove.ACCEPT)
        with self.assertRaises(ProposalRejected):
            parse_social_move(json.dumps({**raw, "counter_due_at": self.now.isoformat()}))

    def test_baseline_choice_can_accept_negotiate_or_decline(self):
        request = project_social([self.opened()]).requests["lamp-request"]
        self.assertEqual(
            choose_request_response(
                request, actor_id="pathos", energy=0.1, expected_revision=1
            ).move,
            SocialMove.DECLINE,
        )
        cramped = replace(request, due_at=(self.now + timedelta(hours=2)).isoformat())
        self.assertEqual(
            choose_request_response(
                cramped, actor_id="pathos", energy=0.8, expected_revision=1
            ).move,
            SocialMove.NEGOTIATE,
        )
        roomy = replace(request, due_at=(self.now + timedelta(days=3)).isoformat())
        self.assertEqual(
            choose_request_response(roomy, actor_id="pathos", energy=0.8, expected_revision=1).move,
            SocialMove.ACCEPT,
        )
        self.assertEqual(
            choose_request_response(
                roomy,
                actor_id="pathos",
                energy=0.8,
                expected_revision=1,
                values={"care": 0.2, "reliability": 0.2, "craft": 0.2},
            ).move,
            SocialMove.DECLINE,
        )
        aligned = choose_request_response(
            roomy,
            actor_id="pathos",
            energy=0.8,
            expected_revision=1,
            values={"care": 0.8, "reliability": 0.8, "craft": 0.8},
        )
        self.assertEqual(aligned.move, SocialMove.ACCEPT)
        self.assertIn("0.80", aligned.reason)
        self.assertEqual(
            choose_request_response(
                roomy,
                actor_id="pathos",
                energy=0.4,
                rest=0.1,
                mastery=0.1,
                expected_revision=1,
            ).move,
            SocialMove.DECLINE,
        )


if __name__ == "__main__":
    unittest.main()
