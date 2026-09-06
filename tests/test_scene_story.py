import asyncio
import unittest
from datetime import datetime, timezone

from eidos.application.scene_story import bounded_scene_events, continuing_scene_events
from eidos.domain.scenes import project_scenes
from eidos.ports.model_gateway import ModelRequest, ModelResponse


class InvalidDialogueGateway:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse('{"text":""}', "invalid-fixture", "test", "stop")


class SceneStoryTests(unittest.TestCase):
    def test_invalid_dialogue_is_audited_and_uses_bounded_authored_fallback(self):
        events = asyncio.run(
            bounded_scene_events(
                [],
                {"pathos": "park", "rowan": "park", "mara": "cafe", "ellis": "workshop"},
                datetime(2026, 1, 4, 13, tzinfo=timezone.utc),
                0,
                InvalidDialogueGateway(),
            )
        )
        self.assertEqual(sum(event.kind == "role.failed" for event in events), 2)
        self.assertEqual(sum(event.kind == "scene.turn_fallback_used" for event in events), 2)
        self.assertEqual(sum(event.kind == "scene.turn_taken" for event in events), 2)
        scene = project_scenes(events).scenes["rowan-weathered-bench-scene"]
        self.assertEqual((scene.status, scene.end_reason), ("ended", "turn_budget"))

    def test_longer_scene_resumes_with_topic_and_turn_order_intact(self):
        locations = {
            "pathos": "workshop",
            "ellis": "workshop",
            "mara": "cafe",
            "rowan": "park",
        }
        first = asyncio.run(
            continuing_scene_events(
                [],
                locations,
                datetime(2026, 1, 8, 12, tzinfo=timezone.utc),
                0,
                InvalidDialogueGateway(),
            )
        )
        paused = project_scenes(first).scenes["ellis-shared-tools-scene"]
        self.assertEqual(
            (paused.status, paused.turn_count, paused.next_actor_id, paused.topic_id),
            ("paused", 2, "ellis", "tool-care"),
        )
        interruption = next(event for event in first if event.kind == "scene.interrupted")
        source = next(event for event in first if event.kind == "world.incident_occurred")
        self.assertEqual(interruption.causation_id, source.event_id)

        second = asyncio.run(
            continuing_scene_events(
                first,
                locations,
                datetime(2026, 1, 9, 12, tzinfo=timezone.utc),
                len(first),
                InvalidDialogueGateway(),
            )
        )
        scene = project_scenes([*first, *second]).scenes["ellis-shared-tools-scene"]
        self.assertEqual(
            (scene.status, scene.turn_count, scene.topic_id, scene.end_reason),
            ("ended", 4, "earned-trust", "turn_budget"),
        )
        self.assertEqual(sum(event.kind == "scene.resumed" for event in second), 1)


if __name__ == "__main__":
    unittest.main()
