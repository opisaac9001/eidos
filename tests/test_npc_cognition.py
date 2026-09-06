import unittest
from uuid import uuid4

from eidos.application.npc_cognition import npc_belief_events
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent


class NPCCognitionTests(unittest.TestCase):
    def test_npc_forms_private_belief_only_from_owned_perception(self):
        perception = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "source_kind": "world_event",
                "source_event_id": str(uuid4()),
                "location_id": "park",
                "text": "Neighbors swap seeds.",
            },
        )
        events = npc_belief_events([perception], "2026-01-02T13:00:00+00:00")
        belief = next(iter(project_beliefs([perception, *events]).beliefs.values()))
        self.assertEqual(belief.owner_id, "rowan")
        self.assertEqual(belief.subject_id, "park")
        self.assertEqual(belief.last_evidence_id, str(perception.event_id))
        self.assertEqual(npc_belief_events([perception, *events], "2026-01-03T13:00:00+00:00"), [])

    def test_pathos_perception_is_left_to_pathos_belief_policy(self):
        perception = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source_kind": "world_event",
                "location_id": "park",
            },
        )
        self.assertEqual(npc_belief_events([perception], "2026-01-02T13:00:00+00:00"), [])


if __name__ == "__main__":
    unittest.main()
