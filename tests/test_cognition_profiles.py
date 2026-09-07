import asyncio
import json
import unittest

from eidos.application.cognition import (
    ROLE_MODEL_PROFILES,
    perform,
    perform_pathos_reply,
    request_for,
)
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse


class AssistantLikeGateway:
    model = "assistant-like-fixture"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            '{"text":"It is good to hear from you. What is on your mind?"}',
            self.model,
            "fixture",
            "stop",
        )


class RevisingGateway:
    model = "revising-fixture"

    def __init__(self):
        self.calls = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        text = (
            "It's good to hear from you. What's on your mind?"
            if self.calls == 1
            else "Yeah, hey. I've just been taking it easy."
        )
        return ModelResponse(
            json.dumps({"text": text}),
            self.model,
            "fixture",
            "stop",
        )


class StubbornContradictionGateway:
    model = "stubborn-fixture"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            json.dumps({"text": "Good morning, Pathos! I've been working on a new project."}),
            self.model,
            "fixture",
            "stop",
        )


class CognitionProfileTests(unittest.TestCase):
    def test_every_text_performer_has_an_explicit_bounded_profile(self):
        self.assertEqual(
            set(ROLE_MODEL_PROFILES),
            {
                "pathos",
                "murmur",
                "firmament",
                "moira",
                "mnemosyne",
                "reflection",
                "oneiros",
                "chronicler",
            },
        )
        requests = {
            role: request_for(role, {"time": "2026-01-01T12:00:00+00:00"})
            for role in ROLE_MODEL_PROFILES
        }
        self.assertTrue(all(1 <= request.max_output_tokens <= 384 for request in requests.values()))
        self.assertTrue(all(0 <= request.temperature <= 1 for request in requests.values()))
        self.assertLess(requests["moira"].max_output_tokens, requests["oneiros"].max_output_tokens)
        self.assertLess(requests["chronicler"].temperature, requests["oneiros"].temperature)
        self.assertEqual(requests["pathos"].task_version, "5")
        self.assertEqual(requests["murmur"].task_version, "5")
        self.assertEqual(requests["firmament"].task_version, "4")
        self.assertEqual(requests["reflection"].task_version, "4")
        self.assertEqual(requests["oneiros"].task_version, "4")

    def test_unknown_role_cannot_inherit_an_accidental_generic_profile(self):
        with self.assertRaisesRegex(ValueError, "Unknown cognition role"):
            request_for("intruder", {})

    def test_runtime_trace_preserves_nonblocking_semantic_warnings(self):
        pending: list[DomainEvent] = []
        text = asyncio.run(
            perform(
                AssistantLikeGateway(),
                "pathos",
                {"message": "hey", "time": "2026-01-01T12:00:00+00:00"},
                "2026-01-01T12:00:00+00:00",
                pending,
            )
        )

        self.assertIsNotNone(text)
        pathos = next(
            event
            for event in pending
            if event.kind == "role.completed" and event.payload["role"] == "pathos"
        )
        critic = next(
            event
            for event in pending
            if event.kind == "role.completed" and event.payload["role"] == "critic"
        )
        self.assertEqual(pathos.payload["semantic_status"], "warning")
        self.assertIn("assistant_like_register", str(pathos.payload["semantic_findings"]))
        self.assertEqual(critic.payload["status"], "warning")

    def test_pathos_reply_gets_one_audited_quality_revision(self):
        gateway = RevisingGateway()
        pending: list[DomainEvent] = []
        text = asyncio.run(
            perform_pathos_reply(
                gateway,
                {"message": "hey", "time": "2026-01-01T12:00:00+00:00"},
                "2026-01-01T12:00:00+00:00",
                pending,
            )
        )

        self.assertEqual(text, "Yeah, hey. I've just been taking it easy.")
        self.assertEqual(gateway.calls, 2)
        selected = next(event for event in pending if event.kind == "role.revision_selected")
        self.assertEqual(selected.payload["selected"], "revision")

    def test_unrepaired_known_contradiction_is_not_delivered(self):
        pending: list[DomainEvent] = []
        text = asyncio.run(
            perform_pathos_reply(
                StubbornContradictionGateway(),
                {"message": "hey", "time": "2026-01-01T16:00:00+00:00"},
                "2026-01-01T16:00:00+00:00",
                pending,
            )
        )

        self.assertIsNone(text)
        selected = next(event for event in pending if event.kind == "role.revision_selected")
        self.assertEqual(selected.payload["selected"], "rejected")


if __name__ == "__main__":
    unittest.main()
