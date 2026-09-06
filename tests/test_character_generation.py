import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.character_generation import generated_character_history_events
from eidos.domain.character_history import project_character_history
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelResponse


class FixedGateway:
    model = "fixed"

    def __init__(self, content):
        self.content = content
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return ModelResponse(self.content, "fixed", "test", "stop")


class CharacterGenerationTests(unittest.TestCase):
    now = datetime(2026, 1, 14, 17, tzinfo=timezone.utc)

    def registration(self):
        return DomainEvent(
            "world.person_registered",
            "pathos",
            {
                "proposal_id": "moira-world-expansion-2026-01-14",
                "entity_kind": "person",
                "entity_id": "sana-reed",
                "name": "Sana Reed",
                "description": "An instrument repairer who recently returned to the neighborhood.",
                "location_id": "cafe",
                "purpose": "Instrument repairer",
                "color": "#7896b2",
                "simulated_at": self.now.isoformat(),
            },
            correlation_id="moira-world-expansion-2026-01-14",
        )

    def generate(self, history, gateway, at=None):
        return asyncio.run(generated_character_history_events(history, at or self.now, gateway))

    def candidate(self, **changes):
        raw = {
            "fact_1_topic": "first craft",
            "fact_1_text": "I learned patient repair work while restoring discarded radios as a teenager.",
            "fact_2_topic": "private collection",
            "fact_2_text": "I've kept one handwritten tune from every town where I have lived.",
            "fact_3_topic": "turning point",
            "fact_3_text": "I left a promising apprenticeship when I realized praise was making me afraid to experiment.",
        }
        raw.update(changes)
        return json.dumps(raw)

    def test_invented_resident_receives_private_persistent_history(self):
        registration = self.registration()
        events = self.generate([registration], StandInGateway())
        facts = project_character_history([registration, *events]).facts
        self.assertEqual(len(facts), 3)
        self.assertEqual(
            {fact.reveal_after_familiarity for fact in facts.values()}, {0.2, 0.5, 0.8}
        )
        self.assertTrue(
            all(
                fact.person_id == "sana-reed" and fact.status == "private"
                for fact in facts.values()
            )
        )
        self.assertFalse(
            any(event.kind in {"memory.recorded", "perception.recorded"} for event in events)
        )
        self.assertEqual(
            self.generate([registration, *events], StandInGateway(), self.now + timedelta(hours=1)),
            [],
        )

    def test_request_contains_only_public_resident_context(self):
        registration = self.registration()
        other_secret = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": "mara-secret",
                "person_id": "mara",
                "topic": "private",
                "text": "I hid this sentence from everyone.",
                "reveal_after_familiarity": 0.9,
                "owner": "mara",
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )
        gateway = FixedGateway(self.candidate())
        self.generate([registration, other_secret], gateway)
        encoded = " ".join(message.content for message in gateway.requests[0].messages)
        self.assertIn("instrument repairer", encoded.lower())
        self.assertNotIn("hid this sentence", encoded)

    def test_invalid_candidate_is_audited_without_fallback_and_retries_are_bounded(self):
        registration = self.registration()
        history = [registration]
        for attempt in range(3):
            at = self.now + timedelta(days=attempt)
            events = self.generate(history, FixedGateway("not json"), at)
            history.extend(events)
            self.assertTrue(
                any(event.kind == "npc.biography_generation_failed" for event in events)
            )
            self.assertFalse(any(event.kind == "npc.biography_seeded" for event in events))
            self.assertEqual(self.generate(history, FixedGateway(self.candidate()), at), [])
        self.assertEqual(
            self.generate(history, FixedGateway(self.candidate()), self.now + timedelta(days=4)),
            [],
        )

    def test_candidate_cannot_claim_a_known_person(self):
        registration = self.registration()
        gateway = FixedGateway(
            self.candidate(fact_2_text="I've secretly worked with Mara for several years.")
        )
        events = self.generate([registration], gateway)
        failure = next(event for event in events if event.kind == "npc.biography_generation_failed")
        self.assertEqual(failure.payload["error_code"], "known_person_claim")

    def test_pack_seeded_people_do_not_receive_a_second_generated_history(self):
        registration = self.registration()
        pack_fact = DomainEvent(
            "npc.biography_seeded",
            "pathos",
            {
                "fact_id": "sana-pack-fact",
                "person_id": "sana-reed",
                "topic": "old workshop",
                "text": "I first learned repair work in a narrow upstairs room.",
                "reveal_after_familiarity": 0.2,
                "owner": "sana-reed",
                "visibility": "private",
                "simulated_at": self.now.isoformat(),
            },
        )
        gateway = FixedGateway(self.candidate())
        self.assertEqual(self.generate([registration, pack_fact], gateway), [])
        self.assertEqual(gateway.requests, [])


if __name__ == "__main__":
    unittest.main()
