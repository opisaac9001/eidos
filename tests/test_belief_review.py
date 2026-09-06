import unittest
from datetime import datetime, timezone

from eidos.application.belief_review import relationship_belief_events
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent


class BeliefReviewTests(unittest.TestCase):
    def test_relationship_evidence_forms_once_and_opposition_contests(self):
        at = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        positive = DomainEvent(
            "relationship.changed",
            "pathos",
            {"person_id": "mara", "trust_delta": 0.08, "simulated_at": at},
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
            {"person_id": "mara", "trust_delta": -0.1, "simulated_at": at},
        )
        events.append(negative)
        events.extend(relationship_belief_events(events, at))
        belief = project_beliefs(events).beliefs["pathos-mara-commitment-reliability"]
        self.assertEqual(belief.status, "contested")
        self.assertEqual(belief.alternative_value, "unreliable")


if __name__ == "__main__":
    unittest.main()
