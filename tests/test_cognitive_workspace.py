import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.cognitive_workspace import cognitive_workspace
from eidos.domain.events import DomainEvent


class CognitiveWorkspaceTests(unittest.TestCase):
    now = datetime(2026, 2, 3, 14, tzinfo=timezone.utc)

    def event(self, kind, text, *, hours_ago=0, aggregate="pathos", **payload):
        return DomainEvent(
            kind,
            aggregate,
            {
                "text": text,
                "simulated_at": (self.now - timedelta(hours=hours_ago)).isoformat(),
                **payload,
            },
        )

    def test_faculties_share_bounded_subjective_material_without_action_authority(self):
        history = [
            self.event("thought.recorded", "Maybe I should slow down.", role="murmur"),
            self.event("reflection.recorded", "I keep rushing the quiet parts."),
            self.event("dream.recalled", "A dream lingered after waking."),
            self.event("concern.opened", "I still owe Rowan an answer.", concern_id="rowan"),
            self.event(
                "reflection.reconsideration_raised",
                "Should I repair, renegotiate, or release this commitment?",
                target_type="commitment",
                target_id="help-rowan",
                action_authority=False,
            ),
            DomainEvent(
                "mind.layer_pulsed",
                "pathos",
                {
                    "pulse_id": "attention-now",
                    "layer": "attention",
                    "mode": "foreground",
                    "focus_type": "person",
                    "focus_id": "rowan",
                    "focus_text": "Keep Rowan in mind",
                    "activation": 0.9,
                    "simulated_at": self.now.isoformat(),
                },
            ),
        ]

        workspace = cognitive_workspace(history, self.now)

        self.assertGreaterEqual(len({item["from_faculty"] for item in workspace}), 4)
        self.assertTrue(all(item["action_authority"] is False for item in workspace))
        dream = next(item for item in workspace if item["kind"] == "dream.recalled")
        self.assertEqual(dream["epistemic_status"], "dream_fragment")
        question = next(item for item in workspace if item["kind"].endswith("raised"))
        self.assertEqual(
            (question["target_type"], question["target_id"]), ("commitment", "help-rowan")
        )

    def test_private_future_and_expired_material_cannot_enter_workspace(self):
        history = [
            self.event("thought.recorded", "expired", hours_ago=7),
            self.event("thought.recorded", "someone else's", aggregate="mara"),
            self.event("thought.recorded", "future", hours_ago=-1),
            self.event("thought.recorded", "available now"),
            self.event(
                "concern.opened",
                "Pathos's unresolved concern",
                concern_id="shared-name",
            ),
            self.event(
                "concern.resolved",
                "Mara resolved her own concern",
                aggregate="mara",
                concern_id="shared-name",
            ),
        ]

        workspace = cognitive_workspace(history, self.now)

        self.assertEqual(
            {item["content"] for item in workspace},
            {"available now", "Pathos's unresolved concern"},
        )

    def test_workspace_caps_each_faculty_and_total_size(self):
        history = [
            self.event("thought.recorded", f"thought {index}", hours_ago=index / 10)
            for index in range(8)
        ]

        workspace = cognitive_workspace(history, self.now, limit=5)

        self.assertEqual(len(workspace), 3)
        with self.assertRaises(ValueError):
            cognitive_workspace(history, self.now, limit=0)


if __name__ == "__main__":
    unittest.main()
