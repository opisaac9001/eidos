import json
import tempfile
import unittest
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


class ContinuousInnerStreamTests(unittest.TestCase):
    def test_waking_quarter_hour_pulse_is_varied_owned_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            life = Life(
                SQLiteEventStore(Path(directory) / "stream.sqlite3"),
                StandInGateway(),
            )
            life.advance(7)

            self.assertTrue(life.pulse_inner_stream())
            self.assertFalse(life.pulse_inner_stream())
            life.advance(0.25)
            self.assertTrue(life.pulse_inner_stream())

            pulses = [event for event in life.history() if event.kind == "mind.stream_pulsed"]
            thoughts = [
                event
                for event in life.history()
                if event.kind == "thought.recorded"
                and event.payload.get("source") == "continuous-inner-stream"
            ]
            self.assertEqual(len(pulses), 2)
            self.assertEqual(len(thoughts), 2)
            self.assertEqual(len({event.payload["text"] for event in thoughts}), 2)
            self.assertTrue(all(event.aggregate_id == "pathos" for event in thoughts))
            self.assertTrue(all(event.payload["factual"] is False for event in thoughts))
            self.assertTrue(
                all(
                    event.payload["stream_pulse_id"]
                    in {item.payload["pulse_id"] for item in pulses}
                    for event in thoughts
                )
            )

    def test_sleep_does_not_generate_waking_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            life = Life(
                SQLiteEventStore(Path(directory) / "sleeping.sqlite3"),
                StandInGateway(),
            )
            life.advance(23)

            self.assertFalse(life.pulse_inner_stream())
            self.assertFalse(any(event.kind == "mind.stream_pulsed" for event in life.history()))

    def test_inner_stream_reaches_the_next_spoken_response_as_subjective_context(self):
        class CapturingGateway(StandInGateway):
            def __init__(self):
                self.requests = []

            async def generate(self, request):
                self.requests.append(request)
                return await super().generate(request)

        with tempfile.TemporaryDirectory() as directory:
            gateway = CapturingGateway()
            life = Life(SQLiteEventStore(Path(directory) / "handoff.sqlite3"), gateway)
            life.advance(7)
            self.assertTrue(life.pulse_inner_stream())
            life.request_visit("workspace-visit")
            self.assertTrue(life.snapshot()["communication"]["live_scene_id"])

            life.chat("Hey, what are you thinking about?", "workspace-turn")

            pathos_request = next(
                request for request in reversed(gateway.requests) if request.capability == "pathos"
            )
            context = json.loads(pathos_request.messages[0].content)
            handoff = next(
                item for item in context["cognitive_workspace"] if item["from_faculty"] == "murmur"
            )
            self.assertEqual(handoff["epistemic_status"], "inner_monologue")
            self.assertFalse(handoff["action_authority"])


if __name__ == "__main__":
    unittest.main()
