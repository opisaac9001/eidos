import unittest
from datetime import datetime, timezone

from eidos.application.object_story import OBJECT_ID, object_story_events
from eidos.domain.planning import project_planning
from eidos.domain.transfers import project_transfers


class ObjectStoryTests(unittest.TestCase):
    def test_project_tool_is_explicitly_lent_and_returned(self):
        history = object_story_events(datetime(2026, 1, 2, 14, tzinfo=timezone.utc), [], "workshop")
        borrowed = project_planning(history).objects[OBJECT_ID]
        self.assertEqual((borrowed.owner_id, borrowed.custodian_id), ("ellis", "pathos"))
        self.assertEqual(next(iter(project_transfers(history).offers.values())).status, "accepted")
        loan_memory = next(event for event in history if event.kind == "memory.recorded")
        custody = next(event for event in history if event.kind == "object.custody_changed")
        self.assertEqual(loan_memory.payload["source_event_id"], str(custody.event_id))
        returned = object_story_events(
            datetime(2026, 1, 5, 17, tzinfo=timezone.utc), history, "workshop"
        )
        history.extend(returned)
        item = project_planning(history).objects[OBJECT_ID]
        self.assertEqual((item.owner_id, item.custodian_id), ("ellis", "ellis"))
        self.assertEqual(len(project_transfers(history).offers), 2)

    def test_absence_cannot_transfer_the_tool(self):
        events = object_story_events(datetime(2026, 1, 2, 14, tzinfo=timezone.utc), [], "park")
        self.assertEqual(events[-1].kind, "transfer.offer_rejected")
        self.assertEqual(events[-1].payload["code"], "not_co_present")


if __name__ == "__main__":
    unittest.main()
