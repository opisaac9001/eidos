import unittest
from datetime import datetime, timezone

from eidos.application.belief_review import relationship_belief_events, testimony_belief_events
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent


class BeliefReviewTests(unittest.TestCase):
    def test_relationship_evidence_forms_once_and_opposition_contests(self):
        at = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        positive = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": "pathos",
                "evidence_actor_id": "mara",
                "trust_delta": 0.08,
                "simulated_at": at,
            },
        )
        events = [positive]
        formed = relationship_belief_events(events, at)
        events.extend(formed)
        self.assertEqual(relationship_belief_events(events, at), [])
        self.assertEqual(
            project_beliefs(events).beliefs["pathos-mara-commitment-reliability"].object_value,
            "reliable",
        )
        negative = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": "pathos",
                "evidence_actor_id": "mara",
                "trust_delta": -0.1,
                "simulated_at": at,
            },
        )
        events.append(negative)
        events.extend(relationship_belief_events(events, at))
        belief = project_beliefs(events).beliefs["pathos-mara-commitment-reliability"]
        self.assertEqual(belief.status, "contested")
        self.assertEqual(belief.alternative_value, "unreliable")

    def test_relationship_delta_without_behavior_actor_does_not_invent_a_belief(self):
        legacy = DomainEvent(
            "relationship.changed",
            "pathos",
            {"person_id": "mara", "trust_delta": 0.08, "simulated_at": "legacy"},
        )
        self.assertEqual(relationship_belief_events([legacy], "now"), [])

    def test_neutral_trust_change_is_not_evidence_of_unreliability(self):
        neutral = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": "rowan",
                "evidence_actor_id": "pathos",
                "trust_delta": 0.0,
                "familiarity_delta": 0.02,
                "simulated_at": "2026-01-02T13:00:00+00:00",
            },
        )
        self.assertEqual(relationship_belief_events([neutral], "now"), [])

    def test_heard_claim_is_discounted_then_direct_evidence_strengthens_it(self):
        perceived = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "speaker_id": "ellis",
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "available",
                "claim_confidence": 0.8,
            },
        )
        history = [perceived]
        history.extend(testimony_belief_events(history, "heard"))
        heard = project_beliefs(history).beliefs["pathos-lamp-switch"]
        self.assertAlmostEqual(heard.confidence, 0.48)
        confirmed = DomainEvent(
            "resource.confirmed",
            "pathos",
            {
                "subject_id": "lamp",
                "predicate": "switch",
                "object_value": "available",
                "confidence": 0.95,
            },
        )
        history.append(confirmed)
        history.extend(testimony_belief_events(history, "confirmed"))
        final = project_beliefs(history).beliefs["pathos-lamp-switch"]
        self.assertEqual(final.evidence_count, 2)
        self.assertAlmostEqual(final.confidence, 0.98)
        self.assertEqual(testimony_belief_events(history, "again"), [])

    def test_private_or_unstructured_perception_does_not_create_a_claim(self):
        private = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "mara",
                "speaker_id": "ellis",
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "available",
                "claim_confidence": 0.8,
            },
        )
        unstructured = DomainEvent(
            "perception.recorded",
            "pathos",
            {"owner": "pathos", "speaker_id": "ellis", "text": "Maybe."},
        )
        self.assertEqual(testimony_belief_events([private, unstructured], "now"), [])


if __name__ == "__main__":
    unittest.main()
