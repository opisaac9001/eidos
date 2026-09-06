import unittest
from datetime import datetime, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.recurring_dialogue import recurring_dialogue_events
from eidos.domain.character_history import eligible_character_fact, project_character_history
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.ports.model_gateway import ModelResponse


class RecordingGateway:
    model = "recording"

    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return ModelResponse("An ordinary remark about the square.", "recording", "test", "stop")


class CharacterHistoryTests(unittest.IsolatedAsyncioTestCase):
    now = datetime(2026, 2, 12, 13, tzinfo=timezone.utc)
    locations = {"pathos": "park", "rowan": "park"}
    names = {"rowan": "Rowan"}

    def seed(self, threshold=0.5):
        return DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": "rowan-left-coast",
                "person_id": "rowan",
                "topic": "old-home",
                "text": "I left the coast after my father's boat was sold.",
                "reveal_after_familiarity": threshold,
                "owner": "rowan",
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )

    async def test_private_fact_is_not_sent_to_dialogue_model_before_threshold(self):
        seed = self.seed(0.8)
        gateway = RecordingGateway()
        events = await recurring_dialogue_events(
            [seed],
            self.locations,
            self.names,
            {"rowan": Relationship("rowan", familiarity=0.4)},
            self.now,
            1,
            gateway,
        )
        encoded_context = " ".join(
            message.content for request in gateway.requests for message in request.messages
        )
        self.assertNotIn("father's boat", encoded_context)
        self.assertFalse(any(event.kind == "npc.biography_disclosed" for event in events))
        self.assertEqual(
            project_character_history([seed, *events]).facts["rowan-left-coast"].status, "private"
        )

    async def test_actual_spoken_turn_discloses_and_gives_pathos_direct_memory(self):
        seed = self.seed(0.5)
        events = await recurring_dialogue_events(
            [seed],
            self.locations,
            self.names,
            {"rowan": Relationship("rowan", encounters=8, familiarity=0.6)},
            self.now,
            1,
            StandInGateway(),
        )
        disclosure = next(event for event in events if event.kind == "npc.biography_disclosed")
        turn = next(
            event
            for event in events
            if event.kind == "scene.turn_taken"
            and str(event.event_id) == disclosure.payload["source_turn_event_id"]
        )
        self.assertEqual(disclosure.causation_id, turn.event_id)
        self.assertIn("father's boat", turn.payload["text"])
        memory = next(
            event
            for event in events
            if event.kind == "memory.recorded"
            and event.payload.get("owner") == "pathos"
            and event.payload.get("source_event_id")
            == str(
                next(
                    perceived.event_id
                    for perceived in events
                    if perceived.kind == "perception.recorded"
                    and perceived.payload.get("source_event_id") == str(turn.event_id)
                    and perceived.payload.get("owner") == "pathos"
                )
            )
        )
        self.assertEqual(memory.payload["text"], turn.payload["text"])
        fact = project_character_history([seed, *events]).facts["rowan-left-coast"]
        self.assertEqual((fact.status, fact.scene_id), ("disclosed", turn.payload["scene_id"]))
        self.assertIsNone(
            eligible_character_fact([seed, *events], "rowan", 1.0, str(turn.payload["scene_id"]))
        )

    def test_seed_ownership_threshold_and_disclosure_identity_are_enforced(self):
        seed = self.seed()
        bad_seed = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {**dict(seed.payload), "fact_id": "bad-owner", "owner": "pathos"},
        )
        with self.assertRaisesRegex(ValueError, "private"):
            project_character_history([bad_seed])
        bad_disclosure = DomainEvent(
            "npc.biography_disclosed",
            "pathos",
            {
                "fact_id": "rowan-left-coast",
                "person_id": "mara",
                "audience_id": "pathos",
                "scene_id": "scene-1",
                "simulated_at": self.now.isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "owner"):
            project_character_history([seed]).apply(bad_disclosure)
        forged = DomainEvent(
            "npc.biography_disclosed",
            "pathos",
            {
                "fact_id": "rowan-left-coast",
                "person_id": "rowan",
                "audience_id": "pathos",
                "scene_id": "scene-1",
                "source_turn_event_id": str(seed.event_id),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=seed.event_id,
        )
        with self.assertRaisesRegex(ValueError, "spoken scene turn"):
            project_character_history([seed, forged])


if __name__ == "__main__":
    unittest.main()
