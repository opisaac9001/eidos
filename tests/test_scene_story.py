import asyncio
import unittest
from datetime import datetime, timezone

from eidos.application.scene_story import bounded_scene_events
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


if __name__ == "__main__":
    unittest.main()
