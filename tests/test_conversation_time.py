import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.conversation_time import exchange_minutes, project_conversation_clocks
from eidos.domain.events import DomainEvent


class ConversationTimeTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)

    def history(self) -> tuple[list[DomainEvent], DomainEvent, DomainEvent]:
        scene = DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "user-visit",
                "initiator_id": "pathos",
                "partner_id": "user",
                "location_id": "home",
                "topic_id": "open-conversation",
                "max_turns": 40,
                "simulated_at": self.now.isoformat(),
            },
        )
        user_turn = DomainEvent(
            "scene.turn_taken",
            "pathos",
            {
                "scene_id": "user-visit",
                "actor_id": "user",
                "turn_number": 1,
                "text": "How are you?",
                "simulated_at": self.now.isoformat(),
            },
        )
        pathos_turn = DomainEvent(
            "scene.turn_taken",
            "pathos",
            {
                "scene_id": "user-visit",
                "actor_id": "pathos",
                "turn_number": 2,
                "text": "I am taking the morning slowly.",
                "simulated_at": self.now.isoformat(),
            },
        )
        return [scene, user_turn, pathos_turn], user_turn, pathos_turn

    def elapsed(
        self, user_turn: DomainEvent, pathos_turn: DomainEvent, *, minutes: int = 5
    ) -> DomainEvent:
        return DomainEvent(
            "conversation.time_elapsed",
            "pathos",
            {
                "scene_id": "user-visit",
                "user_turn_event_id": str(user_turn.event_id),
                "pathos_turn_event_id": str(pathos_turn.event_id),
                "minutes": minutes,
                "started_at": self.now.isoformat(),
                "ends_at": (self.now + timedelta(minutes=minutes)).isoformat(),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=pathos_turn.event_id,
        )

    def test_an_accepted_exchange_adds_bounded_replayable_time(self):
        history, user_turn, pathos_turn = self.history()
        elapsed = self.elapsed(user_turn, pathos_turn)
        clock = project_conversation_clocks([*history, elapsed])["user-visit"]
        self.assertEqual((clock.elapsed_minutes, clock.exchanges), (5, 1))
        self.assertEqual(exchange_minutes("one " * 50, "two " * 50), 15)

    def test_wrong_duration_or_reused_turns_are_rejected(self):
        history, user_turn, pathos_turn = self.history()
        bad = self.elapsed(user_turn, pathos_turn, minutes=10)
        with self.assertRaises(ValueError):
            project_conversation_clocks([*history, bad])
        elapsed = self.elapsed(user_turn, pathos_turn)
        duplicate = self.elapsed(user_turn, pathos_turn)
        with self.assertRaises(ValueError):
            project_conversation_clocks([*history, elapsed, duplicate])


if __name__ == "__main__":
    unittest.main()
