import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.application.life import Life
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import DeferredModelResult, ModelRequest, ModelResponse


class DeferredFixtureGateway:
    model = "deferred-fixture"

    def __init__(self, results=()):
        self.results = list(results)
        self.submitted = []
        self.generated = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.generated.append(request.capability)
        return ModelResponse('{"text":"Clear"}', self.model, "fixture", "stop")

    def submit_deferred(self, request: ModelRequest):
        self.submitted.append(request)
        return request.correlation_id

    def deferred_results(self):
        return self.results


class DeferredCognitionTests(unittest.TestCase):
    def test_present_moment_thought_needs_no_fake_memory_and_applies_once(self):
        with tempfile.TemporaryDirectory() as directory:
            result = DeferredModelResult(
                uuid4(),
                "murmur",
                {"deferred_kind": "inner_thought"},
                "completed",
                "I might open the window.",
                None,
            )
            life = Life(
                SQLiteEventStore(Path(directory) / "thought.db"), DeferredFixtureGateway([result])
            )
            life.advance(1)
            thoughts = [event for event in life.history() if event.kind == "thought.recorded"]
            self.assertEqual(len(thoughts), 1)
            self.assertFalse(thoughts[0].payload["factual"])
            self.assertFalse(any(event.kind == "memory.recorded" for event in life.history()))
            life.advance(1)
            self.assertEqual(
                sum(event.kind == "cognition.result_applied" for event in life.history()), 1
            )

    def test_murmur_is_submitted_after_tick_instead_of_blocking_it(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = DeferredFixtureGateway()
            life = Life(SQLiteEventStore(Path(directory) / "world.db"), gateway)
            life.advance(8)
            self.assertNotIn("murmur", gateway.generated)
            self.assertGreater(len(gateway.submitted), 0)
            self.assertTrue(
                all(
                    '"deferred_kind": "inner_thought"' in request.messages[0].content
                    for request in gateway.submitted
                )
            )

    def test_completed_result_revalidates_once_against_its_source_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "world.db")
            source = DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": "A brass lamp waited on the bench.",
                    "owner": "pathos",
                    "importance": 0.7,
                    "confidence": 1.0,
                    "simulated_at": "2026-01-01T00:00:00+00:00",
                },
            )
            store.append("pathos", [source], 0)
            result = DeferredModelResult(
                uuid4(),
                "murmur",
                {
                    "deferred_kind": "association",
                    "source_memory_id": str(source.event_id),
                    "cue": "lamp",
                    "salience": 0.7,
                },
                "completed",
                "The brass catches a thin line of morning light.",
                None,
            )
            gateway = DeferredFixtureGateway([result])
            life = Life(store, gateway)
            life.advance(1)
            self.assertEqual(
                sum(event.kind == "cognition.result_applied" for event in life.history()), 1
            )
            self.assertEqual(sum(event.kind == "association.formed" for event in life.history()), 1)
            life.advance(1)
            self.assertEqual(
                sum(event.kind == "cognition.result_applied" for event in life.history()), 1
            )


if __name__ == "__main__":
    unittest.main()
