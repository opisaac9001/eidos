from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class DomainEventTests(unittest.TestCase):
    def test_nested_mutable_payloads_and_nonfinite_numbers_are_rejected(self) -> None:
        for payload in ({"nested": {"x": 1}}, {"values": [1]}, {"number": float("nan")}):
            with self.assertRaises(ValueError):
                DomainEvent("test", "pathos", payload)

    def test_payload_is_copied_and_read_only(self) -> None:
        source = {"location_id": "library"}
        event = DomainEvent("pathos.moved", "pathos", source)
        source["location_id"] = "elsewhere"

        self.assertEqual(event.payload["location_id"], "library")
        with self.assertRaises(TypeError):
            event.payload["location_id"] = "park"  # type: ignore[index]

    def test_event_requires_aware_time(self) -> None:
        with self.assertRaises(ValueError):
            DomainEvent("pathos.moved", "pathos", occurred_at=datetime(2026, 1, 1))

    def test_event_trace_metadata_is_validated(self) -> None:
        for version in (0, 1.5, True):
            with self.subTest(version=version), self.assertRaises(ValueError):
                DomainEvent("test", "pathos", schema_version=version)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            DomainEvent("test", "pathos", correlation_id="")


class PathosStateTests(unittest.TestCase):
    def test_events_replay_deterministically(self) -> None:
        initial = PathosState()
        later = initial.simulated_at + timedelta(hours=2)
        events = [
            DomainEvent("time.advanced", "pathos", {"simulated_at": later}),
            DomainEvent("pathos.moved", "pathos", {"location_id": "library"}),
            DomainEvent("affect.changed", "pathos", {"energy": 0.6, "valence": 0.25}),
        ]

        first = initial
        second = initial
        for event in events:
            first = first.apply(event)
            second = second.apply(event)

        self.assertEqual(first, second)
        self.assertEqual(first.location_id, "library")
        self.assertEqual(first.simulated_at, later)

    def test_simulated_time_cannot_move_backwards(self) -> None:
        state = PathosState()
        earlier = state.simulated_at - timedelta(seconds=1)

        with self.assertRaises(ValueError):
            state.apply(DomainEvent("time.advanced", "pathos", {"simulated_at": earlier}))

    def test_affect_dimensions_are_bounded(self) -> None:
        state = PathosState()

        with self.assertRaises(ValueError):
            state.apply(DomainEvent("affect.changed", "pathos", {"energy": 1.1}))


if __name__ == "__main__":
    unittest.main()
