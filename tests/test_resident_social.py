import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.belief_review import testimony_belief_events
from eidos.application.resident_social import resident_social_events
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.resident_relationships import project_resident_relationships
from eidos.domain.scenes import project_scenes


class ResidentSocialTests(unittest.IsolatedAsyncioTestCase):
    names = {"mara": "Mara", "rowan": "Rowan", "ellis": "Ellis"}
    locations = {"pathos": "park", "mara": "cafe", "rowan": "cafe", "ellis": "workshop"}

    async def run_scene(self, history, at, locations=None):
        return await resident_social_events(
            history,
            locations or self.locations,
            self.names,
            at,
            len(history),
            StandInGateway(),
        )

    async def test_private_resident_encounter_changes_both_lives_without_informing_pathos(self):
        at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        events = await self.run_scene([], at)
        scene = next(iter(project_scenes(events).scenes.values()))
        self.assertEqual((scene.status, scene.turn_count), ("ended", 2))
        memories = [event for event in events if event.kind == "memory.recorded"]
        self.assertEqual({event.payload["owner"] for event in memories}, {"mara", "rowan"})
        relationships = project_resident_relationships(events)
        self.assertEqual(relationships.between("mara", "rowan").encounters, 1)
        self.assertAlmostEqual(relationships.between("rowan", "mara").familiarity, 0.17)
        needs = project_npcs(events, at)
        self.assertGreater(needs.people["mara"].connection, 0.5)
        self.assertGreater(needs.people["rowan"].connection, 0.5)

    async def test_public_exchange_can_be_perceived_by_a_co_present_pathos(self):
        at = datetime(2026, 1, 3, 9, tzinfo=timezone.utc)
        locations = {**self.locations, "pathos": "cafe"}
        events = await self.run_scene([], at, locations)
        turns = [event for event in events if event.kind == "scene.turn_taken"]
        self.assertTrue(all(event.payload["privacy"] == "public" for event in turns))
        memories = [event for event in events if event.kind == "memory.recorded"]
        self.assertIn("pathos", {event.payload["owner"] for event in memories})

    async def test_one_residents_belief_becomes_discounted_testimony_for_the_listener(self):
        at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        evidence = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "source_kind": "world_event",
                "location_id": "cafe",
                "text": "A neighborhood gathering began at the café.",
            },
        )
        belief = DomainEvent(
            "belief.formed",
            "pathos",
            {
                "belief_id": "rowan-cafe-community_activity",
                "owner_id": "rowan",
                "subject_id": "cafe",
                "predicate": "community_activity",
                "object_value": "neighbors gather here",
                "confidence": 0.85,
                "evidence_event_id": str(evidence.event_id),
            },
        )
        history = [evidence, belief]
        scene_events = await self.run_scene(history, at)
        claim_turn = next(
            event
            for event in scene_events
            if event.kind == "scene.turn_taken" and event.payload.get("claim_subject_id") == "cafe"
        )
        self.assertEqual(
            (claim_turn.payload["actor_id"], claim_turn.payload["audience_id"]),
            ("rowan", "mara"),
        )
        combined = [*history, *scene_events]
        reviews = testimony_belief_events(combined, at.isoformat())
        beliefs = project_beliefs([*combined, *reviews]).beliefs
        received = beliefs["mara-cafe-community_activity"]
        self.assertEqual((received.owner_id, received.status), ("mara", "held"))
        self.assertAlmostEqual(received.confidence, 0.51)
        self.assertNotIn("pathos-cafe-community_activity", beliefs)

    async def test_pair_has_a_five_day_cooldown_and_only_one_scene_per_day(self):
        at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        first = await self.run_scene([], at)
        self.assertEqual(await self.run_scene(first, at + timedelta(hours=1)), [])
        self.assertEqual(await self.run_scene(first, at + timedelta(days=1)), [])
        self.assertEqual(await self.run_scene(first, at + timedelta(days=2)), [])
        self.assertEqual(await self.run_scene(first, at + timedelta(days=3)), [])
        self.assertEqual(await self.run_scene(first, at + timedelta(days=4)), [])
        later = await self.run_scene(first, at + timedelta(days=5))
        self.assertTrue(any(event.kind == "scene.started" for event in later))

    async def test_listener_does_not_echo_latest_testimony_back_to_its_speaker(self):
        at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        heard = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "mara",
                "speaker_id": "ellis",
                "claim_subject_id": "workshop",
                "claim_predicate": "opening_status",
                "claim_value": "open",
                "claim_confidence": 0.8,
            },
        )
        history = [heard]
        history.extend(testimony_belief_events(history, at.isoformat()))
        locations = {"pathos": "park", "mara": "cafe", "ellis": "cafe", "rowan": "park"}
        events = await self.run_scene(history, at, locations)
        self.assertFalse(
            any(
                event.kind == "scene.turn_taken"
                and event.payload.get("claim_subject_id") is not None
                for event in events
            )
        )

    async def test_busy_resident_is_not_silently_double_booked(self):
        started = DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "ordinary-existing-rowan",
                "initiator_id": "pathos",
                "partner_id": "rowan",
                "location_id": "cafe",
                "topic_id": "existing-conversation",
                "max_turns": 4,
                "simulated_at": "2026-01-01T09:00:00+00:00",
            },
        )
        at = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        self.assertEqual(await self.run_scene([started], at), [])

    def test_relationship_change_requires_the_cited_shared_scene(self):
        forged = DomainEvent(
            "npc.relationship_changed",
            "pathos",
            {
                "owner": "mara",
                "person_id": "rowan",
                "scene_id": "missing",
                "source_turn_event_id": "not-real",
                "familiarity_delta": 0.02,
                "visibility": "private",
            },
        )
        with self.assertRaisesRegex(ValueError, "prior spoken turn"):
            project_resident_relationships([forged])


if __name__ == "__main__":
    unittest.main()
