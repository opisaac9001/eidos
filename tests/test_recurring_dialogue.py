import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.followups import follow_up_events
from eidos.application.recurring_dialogue import recurring_dialogue_events
from eidos.application.relationship_repairs import relationship_repair_events
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.scenes import project_scenes


class RecurringDialogueTests(unittest.IsolatedAsyncioTestCase):
    now = datetime(2026, 1, 12, 13, tzinfo=timezone.utc)
    locations = {"pathos": "park", "rowan": "park", "mara": "cafe"}
    names = {"rowan": "Rowan", "mara": "Mara"}

    async def test_new_acquaintance_has_a_short_complete_grounded_conversation(self):
        events = await recurring_dialogue_events(
            [],
            self.locations,
            self.names,
            {"rowan": Relationship("rowan")},
            self.now,
            0,
            StandInGateway(),
        )
        scene = next(iter(project_scenes(events).scenes.values()))
        self.assertEqual(
            (scene.turn_count, scene.status, scene.end_reason), (2, "ended", "turn_budget")
        )
        self.assertTrue(any(event.kind == "relationship.changed" for event in events))
        memories = [event for event in events if event.kind == "memory.recorded"]
        self.assertEqual({event.payload["owner"] for event in memories}, {"pathos", "rowan"})

    async def test_repeated_meetings_do_not_replay_the_same_conversation(self):
        history: list[DomainEvent] = []
        for day_offset in range(0, 30, 5):
            events = await recurring_dialogue_events(
                history,
                self.locations,
                self.names,
                {"rowan": Relationship("rowan")},
                self.now + timedelta(days=day_offset),
                len(history),
                StandInGateway(),
            )
            history.extend(events)

        turns = [
            str(event.payload["text"]) for event in history if event.kind == "scene.turn_taken"
        ]
        self.assertEqual(len(turns), 12)
        self.assertEqual(len(set(turns)), len(turns))

    async def test_familiar_conversation_continues_across_hours_and_changes_topic(self):
        perceptions = [
            DomainEvent(
                "perception.recorded",
                "pathos",
                {
                    "owner": "pathos",
                    "location_id": "park",
                    "topic_id": topic,
                },
            )
            for topic in ("winter-trees", "missing-sign")
        ]
        relationship = {"rowan": Relationship("rowan", encounters=20, familiarity=0.9)}
        history = list(perceptions)
        for offset in range(3):
            events = await recurring_dialogue_events(
                history,
                self.locations,
                self.names,
                relationship,
                self.now + timedelta(hours=offset),
                len(history),
                StandInGateway(),
            )
            history.extend(events)
        scene = next(iter(project_scenes(history).scenes.values()))
        self.assertEqual((scene.turn_count, scene.status), (6, "ended"))
        topics = {
            event.payload["topic_id"] for event in history if event.kind == "scene.turn_taken"
        }
        self.assertEqual(topics, {"winter-trees", "missing-sign"})

    async def test_tension_allows_the_other_person_to_leave_before_the_budget(self):
        events = await recurring_dialogue_events(
            [],
            self.locations,
            self.names,
            {"rowan": Relationship("rowan", encounters=20, familiarity=0.9, tension=0.8)},
            self.now,
            0,
            StandInGateway(),
        )
        scene = next(iter(project_scenes(events).scenes.values()))
        self.assertEqual((scene.turn_count, scene.status, scene.end_reason), (2, "ended", "left"))
        self.assertFalse(any(event.kind == "relationship.changed" for event in events))

    async def test_a_ready_follow_up_prioritizes_that_person_and_becomes_the_topic(self):
        source = DomainEvent(
            "social.activity_completed",
            "pathos",
            {"person_id": "rowan", "simulated_at": (self.now - timedelta(days=3)).isoformat()},
        )
        scheduled = follow_up_events([source], self.now - timedelta(days=3))
        ready = follow_up_events([source, *scheduled], self.now - timedelta(days=1))
        history = [source, *scheduled, *ready]
        locations = {"pathos": "park", "mara": "park", "rowan": "park"}
        events = await recurring_dialogue_events(
            history,
            locations,
            self.names,
            {
                "mara": Relationship("mara"),
                "rowan": Relationship("rowan"),
            },
            self.now,
            len(history),
            StandInGateway(),
        )
        started = next(event for event in events if event.kind == "scene.started")
        self.assertEqual(started.payload["partner_id"], "rowan")
        self.assertEqual(started.payload["topic_id"], "following-up-with-rowan")
        followup_events = follow_up_events([*history, *events], self.now)
        completed = next(event for event in followup_events if event.kind == "follow_up.completed")
        self.assertEqual(completed.payload["person_id"], "rowan")

    async def test_apology_follow_up_keeps_forgiveness_unknown_in_the_topic(self):
        rupture_at = self.now - timedelta(days=4)
        apology_at = self.now - timedelta(days=3)
        rupture = DomainEvent(
            "disagreement.expressed",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": rupture_at.isoformat(),
            },
        )
        apology = DomainEvent(
            "apology.offered",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": apology_at.isoformat(),
            },
        )
        history = [rupture, apology]
        history.extend(relationship_repair_events(history, apology_at))
        history.extend(follow_up_events(history, apology_at))
        history.extend(follow_up_events(history, self.now - timedelta(days=1)))
        events = await recurring_dialogue_events(
            history,
            self.locations,
            self.names,
            {"rowan": Relationship("rowan")},
            self.now,
            len(history),
            StandInGateway(),
        )
        started = next(event for event in events if event.kind == "scene.started")
        self.assertEqual(
            started.payload["topic_id"],
            "cautious-repair-park-bench-forgiveness-unknown",
        )


if __name__ == "__main__":
    unittest.main()
