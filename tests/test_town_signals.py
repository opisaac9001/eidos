import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.town_signals import active_town_signal_context, town_signal_events
from eidos.ports.town_signals import TownSignal


class Source:
    def __init__(self, signals=None, error=None):
        self.signals = signals or []
        self.error = error
        self.calls = 0

    def read(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.signals


class TownSignalTests(unittest.TestCase):
    now = datetime(2026, 9, 6, 6, tzinfo=timezone.utc)

    def signal(self, **changes):
        values = {
            "signal_id": "weather-1",
            "kind": "weather",
            "town": "Frome",
            "title": "Current weather",
            "summary": "Cloudy and 17.5°C.",
            "observed_at": self.now,
            "source_name": "Open-Meteo",
            "source_url": "https://api.open-meteo.com/v1/forecast",
        }
        values.update(changes)
        return TownSignal(**values)

    def test_morning_poll_records_attributed_inspiration_not_world_fact(self):
        source = Source([self.signal()])
        events = town_signal_events([], self.now, source)
        observed = next(event for event in events if event.kind == "external_signal.observed")
        inspiration = next(event for event in events if event.kind == "world.signal_inspiration")
        self.assertFalse(observed.payload["world_fact"])
        self.assertFalse(observed.payload["action_authority"])
        self.assertEqual(observed.payload["source_name"], "Open-Meteo")
        self.assertEqual(inspiration.causation_id, observed.event_id)
        self.assertEqual(
            active_town_signal_context(events, self.now),
            {"weather-1": "Current weather: Cloudy and 17.5°C."},
        )
        self.assertEqual(town_signal_events(events, self.now, source), [])
        self.assertEqual(source.calls, 1)

    def test_poll_is_only_at_six_and_context_expires(self):
        source = Source([self.signal()])
        self.assertEqual(town_signal_events([], self.now.replace(hour=7), source), [])
        events = town_signal_events([], self.now, source)
        self.assertEqual(active_town_signal_context(events, self.now + timedelta(hours=25)), {})

    def test_failure_is_visible_and_does_not_create_fiction(self):
        events = town_signal_events([], self.now, Source(error=RuntimeError("offline")))
        self.assertEqual(
            [event.kind for event in events],
            ["external_signal.poll_requested", "external_signal.poll_failed"],
        )
        self.assertFalse(any(event.kind.startswith("world_event.") for event in events))

    def test_invalid_external_material_is_rejected_as_a_failed_poll(self):
        events = town_signal_events(
            [], self.now, Source([self.signal(source_url="http://unsafe.example/report")])
        )
        self.assertEqual(events[-1].kind, "external_signal.poll_failed")


if __name__ == "__main__":
    unittest.main()
