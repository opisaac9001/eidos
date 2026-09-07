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


if __name__ == "__main__":
    unittest.main()
