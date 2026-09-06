import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.phone_calls import phone_call_events
from eidos.domain.events import DomainEvent


class PhoneCallTests(unittest.TestCase):
    now = datetime(2026, 1, 10, 19, tzinfo=timezone.utc)
    locations = {"pathos": "home", "user": "home", "mara": "cafe"}

    def goal(self, suffix="one"):
        return DomainEvent(
            "npc.goal_formed",
            "pathos",
            {
                "actor_id": "mara",
                "goal_id": f"mara-connection-{suffix}",
                "title": "Speak with someone familiar",
                "motivation_need": "connection",
                "simulated_at": self.now.isoformat(),
            },
        )

    def scene(self):
        return DomainEvent(
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

    def test_connection_goal_can_cause_a_source_linked_completed_call(self):
        goal = self.goal()
        events = phone_call_events(
            [goal],
            self.now,
            1,
            actor_locations=self.locations,
            pathos_awake=True,
        )
        self.assertEqual(
            [event.kind for event in events],
            ["phone.call_received", "phone.call_answered", "phone.call_completed"],
        )
        self.assertEqual(events[0].causation_id, goal.event_id)
        self.assertEqual(events[2].causation_id, events[1].event_id)

    def test_call_can_be_declined_during_visit_then_returned_when_free(self):
        scene = self.scene()
        goal, first = self._find_visit_decision("phone.call_declined", scene)
        callback = next(event for event in first if event.kind == "phone.callback_scheduled")
        history = [goal, scene, *first]
        self.assertEqual(
            phone_call_events(
                history,
                self.now + timedelta(hours=2),
                len(history),
                actor_locations=self.locations,
                pathos_awake=True,
            ),
            [],
        )
        history.append(
            DomainEvent(
                "scene.ended",
                "pathos",
                {
                    "scene_id": "user-visit",
                    "actor_id": "user",
                    "reason": "left",
                },
            )
        )
        returned = phone_call_events(
            history,
            datetime.fromisoformat(callback.payload["due_at"]),
            len(history),
            actor_locations=self.locations,
            pathos_awake=True,
        )
        self.assertEqual([event.kind for event in returned], ["phone.callback_completed"])
        self.assertEqual(returned[0].causation_id, callback.event_id)

    def test_answered_call_pauses_then_resumes_the_live_visit(self):
        scene = self.scene()
        goal, first = self._find_visit_decision("phone.call_answered", scene)
        self.assertTrue(any(event.kind == "scene.interrupted" for event in first))
        history = [goal, scene, *first]
        second = phone_call_events(
            history,
            self.now + timedelta(hours=1),
            len(history),
            actor_locations=self.locations,
            pathos_awake=True,
        )
        self.assertTrue(any(event.kind == "phone.call_completed" for event in second))
        self.assertTrue(any(event.kind == "scene.resumed" for event in second))

    def _find_visit_decision(self, kind, scene):
        for index in range(100):
            goal = self.goal(str(index))
            events = phone_call_events(
                [goal, scene],
                self.now,
                2,
                actor_locations=self.locations,
                pathos_awake=True,
            )
            if any(event.kind == kind for event in events):
                return goal, events
        self.fail(f"No deterministic fixture produced {kind}")


if __name__ == "__main__":
    unittest.main()
