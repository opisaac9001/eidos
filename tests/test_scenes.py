import unittest
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    SceneEndProposal,
    SceneEndReason,
    ScenePrivacy,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_end,
    resolve_scene_start,
    resolve_scene_turn,
)


class SceneTests(unittest.TestCase):
    locations = {"pathos": "park", "rowan": "park", "mara": "park", "ellis": "workshop"}
    at = "2026-01-04T13:00:00+00:00"

    def start(self, maximum: int = 3):
        return resolve_scene_start(
            SceneStartProposal("start", "bench", "pathos", "rowan", "bench-care", maximum, 0),
            state=project_scenes([]),
            actor_locations=self.locations,
            known_actor_ids=set(self.locations),
            actual_revision=0,
            simulated_at=self.at,
        )

    def test_private_turn_is_owned_only_by_audience_and_advances_topic(self):
        started = self.start()
        state = project_scenes(started.events)
        turn = resolve_scene_turn(
            SceneTurnProposal(
                "rowan-turn",
                "bench",
                "rowan",
                "The grain still shows through.",
                "explain",
                "wood-grain",
                ScenePrivacy.PRIVATE,
                len(started.events),
            ),
            state=state,
            history=started.events,
            actor_locations=self.locations,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        self.assertTrue(turn.accepted)
        self.assertEqual(
            {event.payload["owner"] for event in turn.events if event.kind == "memory.recorded"},
            {"pathos"},
        )
        projected = project_scenes([*started.events, *turn.events]).scenes["bench"]
        self.assertEqual(
            (projected.turn_count, projected.next_actor_id, projected.topic_id),
            (1, "pathos", "wood-grain"),
        )

    def test_public_turn_reaches_only_co_present_observers(self):
        started = self.start()
        turn = resolve_scene_turn(
            SceneTurnProposal(
                "public-turn",
                "bench",
                "rowan",
                "Look at this join.",
                "show",
                "join",
                ScenePrivacy.PUBLIC,
                len(started.events),
            ),
            state=project_scenes(started.events),
            history=started.events,
            actor_locations=self.locations,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        owners = {
            event.payload["owner"] for event in turn.events if event.kind == "memory.recorded"
        }
        self.assertEqual(owners, {"pathos", "mara"})
        self.assertNotIn("ellis", owners)

    def test_turn_budget_ends_scene_and_rejects_later_speech(self):
        started = self.start(1)
        turn = resolve_scene_turn(
            SceneTurnProposal(
                "last-turn",
                "bench",
                "rowan",
                "That is enough for now.",
                "close",
                "bench-care",
                ScenePrivacy.PRIVATE,
                len(started.events),
            ),
            state=project_scenes(started.events),
            history=started.events,
            actor_locations=self.locations,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        history = [*started.events, *turn.events]
        self.assertEqual(project_scenes(history).scenes["bench"].end_reason, "turn_budget")
        rejected = resolve_scene_turn(
            SceneTurnProposal(
                "too-late",
                "bench",
                "pathos",
                "Wait.",
                "continue",
                "bench-care",
                ScenePrivacy.PRIVATE,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actor_locations=self.locations,
            actual_revision=len(history),
            simulated_at=self.at,
        )
        self.assertEqual(rejected.code, "closed_scene")

    def test_exit_is_voluntary_and_interruption_requires_evidence(self):
        started = self.start()
        left = resolve_scene_end(
            SceneEndProposal("leave", "bench", "rowan", SceneEndReason.LEFT, len(started.events)),
            state=project_scenes(started.events),
            history=started.events,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        self.assertTrue(left.accepted)
        interruption = SceneEndProposal(
            "interrupt", "bench", "rowan", SceneEndReason.INTERRUPTED, len(started.events), uuid4()
        )
        rejected = resolve_scene_end(
            interruption,
            state=project_scenes(started.events),
            history=started.events,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        self.assertEqual(rejected.code, "missing_interruption")
        source = DomainEvent("world_event.occurred", "pathos", {"text": "A storm begins"})
        accepted = resolve_scene_end(
            SceneEndProposal(
                "interrupt-2",
                "bench",
                "rowan",
                SceneEndReason.INTERRUPTED,
                len(started.events) + 1,
                source.event_id,
            ),
            state=project_scenes(started.events),
            history=[*started.events, source],
            actual_revision=len(started.events) + 1,
            simulated_at=self.at,
        )
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.events[-1].causation_id, source.event_id)


if __name__ == "__main__":
    unittest.main()
