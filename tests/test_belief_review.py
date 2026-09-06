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

    def test_private_testimony_forms_only_the_listeners_owned_discounted_belief(self):
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
        history = [private]
        history.extend(testimony_belief_events(history, "now"))
        belief = project_beliefs(history).beliefs["mara-lamp-switch"]
        self.assertEqual((belief.owner_id, belief.object_value), ("mara", "available"))
        self.assertAlmostEqual(belief.confidence, 0.48)
        self.assertNotIn("pathos-lamp-switch", project_beliefs(history).beliefs)

    def test_unstructured_perception_does_not_create_a_claim(self):
        unstructured = DomainEvent(
            "perception.recorded",
            "pathos",
            {"owner": "pathos", "speaker_id": "ellis", "text": "Maybe."},
        )
        self.assertEqual(testimony_belief_events([unstructured], "now"), [])

    def test_testimony_loses_confidence_at_each_listener_and_conflict_contests_it(self):
        rowan_to_mara = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "mara",
                "speaker_id": "rowan",
                "claim_subject_id": "glasshouse",
                "claim_predicate": "opening_status",
                "claim_value": "open",
                "claim_confidence": 0.8,
            },
        )
        history = [rowan_to_mara]
        history.extend(testimony_belief_events(history, "first"))
        mara = project_beliefs(history).beliefs["mara-glasshouse-opening_status"]
        self.assertAlmostEqual(mara.confidence, 0.48)
        mara_to_ellis = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "ellis",
                "speaker_id": "mara",
                "claim_subject_id": "glasshouse",
                "claim_predicate": "opening_status",
                "claim_value": "open",
                "claim_confidence": mara.confidence,
            },
        )
        history.append(mara_to_ellis)
        history.extend(testimony_belief_events(history, "second"))
        ellis = project_beliefs(history).beliefs["ellis-glasshouse-opening_status"]
        self.assertAlmostEqual(ellis.confidence, 0.288)
        contradiction = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "ellis",
                "speaker_id": "rowan",
                "claim_subject_id": "glasshouse",
                "claim_predicate": "opening_status",
                "claim_value": "closed",
                "claim_confidence": 0.9,
            },
        )
        history.append(contradiction)
        history.extend(testimony_belief_events(history, "third"))
        contested = project_beliefs(history).beliefs["ellis-glasshouse-opening_status"]
        self.assertEqual((contested.status, contested.alternative_value), ("contested", "closed"))


if __name__ == "__main__":
    unittest.main()
