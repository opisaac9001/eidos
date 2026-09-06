import unittest
from datetime import datetime, timezone

from eidos.application.messaging import communication_availability, reply_due_at
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class MessagingTests(unittest.TestCase):
    def test_sleep_defers_a_message_until_the_next_waking_window(self):
        state = PathosState(simulated_at=datetime(2026, 1, 1, 23, tzinfo=timezone.utc), awake=False)
        availability = communication_availability([], state)
        self.assertEqual(availability.status, "asleep")
        self.assertFalse(availability.can_visit)
        self.assertEqual(
            reply_due_at([], state, "late-message"),
            datetime(2026, 1, 2, 7, tzinfo=timezone.utc),
        )

    def test_an_active_conversation_makes_him_unavailable_and_slows_texting(self):
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        state = PathosState(simulated_at=now, awake=True)
        scene = DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "lunch-talk",
                "initiator_id": "pathos",
                "partner_id": "rowan",
                "location_id": "park",
                "topic_id": "ordinary-things",
                "max_turns": 4,
            },
        )
        availability = communication_availability([scene], state)
        self.assertEqual(availability.status, "occupied")
        self.assertFalse(availability.can_visit)
        self.assertGreaterEqual(
            (reply_due_at([scene], state, "during-talk") - now).total_seconds(), 3600
        )

    def test_response_variability_is_stable_for_the_same_message(self):
        state = PathosState(simulated_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc), awake=True)
        first = reply_due_at([], state, "same-id")
        self.assertEqual(first, reply_due_at([], state, "same-id"))
        self.assertGreater(first, state.simulated_at)
        self.assertLessEqual((first - state.simulated_at).total_seconds(), 3600)


if __name__ == "__main__":
    unittest.main()
