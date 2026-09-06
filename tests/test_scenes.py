import unittest
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    SceneEndProposal,
    SceneEndReason,
    SceneInterruptProposal,
    ScenePrivacy,
    SceneResumeProposal,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_end,
    resolve_scene_interruption,
    resolve_scene_resume,
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

    def test_structured_claim_reaches_only_the_actual_turn_observers(self):
        started = self.start()
        turn = resolve_scene_turn(
            SceneTurnProposal(
                "claim-turn",
                "bench",
                "rowan",
                "I may be wrong, but the lamp switch seems available.",
                "testify",
                "lamp-switch",
                ScenePrivacy.PRIVATE,
                len(started.events),
                claim_subject_id="lamp",
                claim_predicate="switch",
                claim_value="available",
                claim_confidence=0.8,
            ),
            state=project_scenes(started.events),
            history=started.events,
            actor_locations=self.locations,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        perceptions = [event for event in turn.events if event.kind == "perception.recorded"]
        self.assertEqual([event.payload["owner"] for event in perceptions], ["pathos"])
        self.assertEqual(perceptions[0].payload["claim_subject_id"], "lamp")
        partial = resolve_scene_turn(
            SceneTurnProposal(
                "partial-claim",
                "bench",
                "rowan",
                "Something uncertain.",
                "testify",
                "lamp-switch",
                ScenePrivacy.PRIVATE,
                len(started.events),
                claim_subject_id="lamp",
            ),
            state=project_scenes(started.events),
            history=started.events,
            actor_locations=self.locations,
            actual_revision=len(started.events),
            simulated_at=self.at,
        )
        self.assertEqual(partial.code, "partial_claim")

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

    def test_a_live_visit_can_have_a_long_but_still_finite_turn_budget(self):
        self.assertTrue(self.start(40).accepted)
        self.assertEqual(self.start(41).code, "invalid_budget")

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

    def test_interrupted_scene_preserves_turn_and_topic_then_resumes(self):
        started = self.start(4)
        source = DomainEvent("world.incident_occurred", "pathos", {"text": "A delivery arrived"})
        history = [*started.events, source]
        interrupted = resolve_scene_interruption(
            SceneInterruptProposal("pause", "bench", "pathos", source.event_id, len(history)),
            state=project_scenes(history),
            history=history,
            actual_revision=len(history),
            simulated_at=self.at,
        )
        history.extend(interrupted.events)
        paused = project_scenes(history).scenes["bench"]
        self.assertEqual(
            (paused.status, paused.turn_count, paused.topic_id), ("paused", 0, "bench-care")
        )
        blocked_turn = resolve_scene_turn(
            SceneTurnProposal(
                "paused-turn",
                "bench",
                "rowan",
                "One more thing.",
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
        self.assertEqual(blocked_turn.code, "paused_scene")
        resumed = resolve_scene_resume(
            SceneResumeProposal("resume", "bench", "rowan", len(history)),
            state=project_scenes(history),
            actor_locations=self.locations,
            actual_revision=len(history),
            simulated_at=self.at,
        )
        history.extend(resumed.events)
        scene = project_scenes(history).scenes["bench"]
        self.assertEqual(
            (scene.status, scene.next_actor_id, scene.topic_id), ("active", "rowan", "bench-care")
        )

    def test_scene_cannot_resume_until_both_people_return(self):
        started = self.start()
        source = DomainEvent("world.incident_occurred", "pathos")
        history = [*started.events, source]
        interrupted = resolve_scene_interruption(
            SceneInterruptProposal("pause", "bench", "rowan", source.event_id, len(history)),
            state=project_scenes(history),
            history=history,
            actual_revision=len(history),
            simulated_at=self.at,
        )
        history.extend(interrupted.events)
        resumed = resolve_scene_resume(
            SceneResumeProposal("resume", "bench", "pathos", len(history)),
            state=project_scenes(history),
            actor_locations={**self.locations, "rowan": "home"},
            actual_revision=len(history),
            simulated_at=self.at,
        )
        self.assertEqual(resumed.code, "not_co_present")


if __name__ == "__main__":
    unittest.main()
