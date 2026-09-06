import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.scenes import project_scenes


class InterruptionRecoveryTests(unittest.TestCase):
    now = datetime(2026, 1, 8, 16, tzinfo=timezone.utc)
    locations = {"pathos": "home", "user": "home"}

    def history(self, extra=()):
        interruption = DomainEvent(
            "phone.call_received",
            "pathos",
            {"call_id": "call", "simulated_at": (self.now - timedelta(hours=1)).isoformat()},
        )
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
                "simulated_at": (self.now - timedelta(hours=2)).isoformat(),
            },
        )
        paused = DomainEvent(
            "scene.interrupted",
            "pathos",
            {
                "scene_id": "user-visit",
                "actor_id": "pathos",
                "source_event_id": str(interruption.event_id),
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
            causation_id=interruption.event_id,
            correlation_id="user-visit",
        )
        completed = DomainEvent(
            "phone.call_completed",
            "pathos",
            {"call_id": "call", "caller_id": "mara", "simulated_at": self.now.isoformat()},
            causation_id=interruption.event_id,
        )
        return [scene, interruption, paused, *extra, completed], completed

    def recover(self, history, completed, *, energy=0.8, key="recovery", locations=None):
        return recover_user_scene(
            history,
            "user-visit",
            self.now,
            len(history),
            actor_locations=locations or self.locations,
            pathos_energy=energy,
            source_event=completed,
            decision_key=key,
        )

    def test_an_imminent_commitment_ends_instead_of_resetting_the_conversation(self):
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "leave-soon",
                "title": "A promised appointment",
                "starts_at": (self.now + timedelta(minutes=45)).isoformat(),
                "ends_at": (self.now + timedelta(hours=2)).isoformat(),
                "location_id": "cafe",
                "actor_id": "pathos",
            },
        )
        history, completed = self.history((schedule,))
        events = self.recover(history, completed, energy=1.0)
        decision = next(event for event in events if event.kind == "scene.resumption_decided")
        self.assertEqual(
            (decision.payload["decision"], decision.payload["upcoming_schedule_id"]),
            ("end", "leave-soon"),
        )
        self.assertEqual(project_scenes([*history, *events]).scenes["user-visit"].status, "ended")
        self.assertTrue(any(event.kind == "conversation.message" for event in events))

    def test_exhaustion_or_lost_presence_ends_the_visit_with_a_reason(self):
        history, completed = self.history()
        exhausted = self.recover(history, completed, energy=0.1)
        self.assertEqual(
            next(event for event in exhausted if event.kind == "scene.resumption_decided").payload[
                "decision"
            ],
            "end",
        )
        absent = self.recover(
            history,
            completed,
            energy=1.0,
            key="absent",
            locations={"pathos": "home", "user": "park"},
        )
        decision = next(event for event in absent if event.kind == "scene.resumption_decided")
        self.assertFalse(decision.payload["decision_co_present"])

    def test_available_recovery_retains_replay_stable_personal_variability(self):
        history, completed = self.history()
        outcomes = {}
        for index in range(200):
            events = self.recover(history, completed, energy=0.6, key=f"choice-{index}")
            decision = next(event for event in events if event.kind == "scene.resumption_decided")
            outcomes.setdefault(str(decision.payload["decision"]), events)
            if set(outcomes) == {"resume", "end"}:
                break
        self.assertEqual(set(outcomes), {"resume", "end"})
        resumed = outcomes["resume"]
        self.assertTrue(any(event.kind == "scene.resumed" for event in resumed))
        repeated = [
            next(
                event
                for event in self.recover(history, completed, energy=0.6, key="same")
                if event.kind == "scene.resumption_decided"
            ).payload["decision"]
            for _ in range(2)
        ]
        self.assertEqual(repeated[0], repeated[1])


if __name__ == "__main__":
    unittest.main()
