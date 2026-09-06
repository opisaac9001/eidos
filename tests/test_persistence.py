import ast
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.events import DomainEvent
from eidos.ports.event_store import RevisionConflict


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "world.sqlite3"
        self.store = SQLiteEventStore(self.path)

    def test_event_roundtrip_preserves_types_and_identity(self) -> None:
        event = DomainEvent(
            "test",
            "pathos",
            {"at": datetime.now(timezone.utc), "number": 0.25, "enabled": True, "empty": None},
            schema_version=2,
            causation_id=uuid4(),
            correlation_id="proposal-17",
        )
        self.store.append("pathos", [event], 0)
        self.assertEqual(self.store.read("pathos"), [event])

    def test_v1_database_migrates_without_rewriting_events(self) -> None:
        legacy_path = Path(self.directory.name) / "legacy.sqlite3"
        event = DomainEvent("legacy", "pathos", {"value": "kept"})
        with sqlite3.connect(legacy_path) as connection:
            connection.execute(
                "CREATE TABLE events (aggregate_id TEXT NOT NULL, revision INTEGER NOT NULL, "
                "event_id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, occurred_at TEXT NOT NULL, "
                "payload TEXT NOT NULL, PRIMARY KEY (aggregate_id, revision))"
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "pathos",
                    1,
                    str(event.event_id),
                    event.kind,
                    event.occurred_at.isoformat(),
                    '{"value": "kept"}',
                ),
            )
            connection.execute("PRAGMA user_version = 1")

        migrated = SQLiteEventStore(legacy_path)
        self.assertEqual(migrated.read("pathos"), [event])
        with sqlite3.connect(legacy_path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_day_survives_restart_without_repeating_memories(self) -> None:
        first = Life(self.store, StandInGateway())
        first.advance(9)
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(first.snapshot(), restarted.snapshot())
        restarted.advance(15)
        whole = Life(
            SQLiteEventStore(Path(self.directory.name) / "whole.sqlite3"), StandInGateway()
        )
        whole.advance(24)
        self.assertEqual(restarted.snapshot()["pathos"], whole.snapshot()["pathos"])
        self.assertEqual(
            [m["text"] for m in restarted.snapshot()["memories"]],
            [m["text"] for m in whole.snapshot()["memories"]],
        )
        self.assertGreaterEqual(len(restarted.snapshot()["memories"]), 7)

    def test_stale_writer_cannot_overwrite_events(self) -> None:
        other = SQLiteEventStore(self.path)
        self.store.append("pathos", [DomainEvent("test", "pathos")], 0)
        with self.assertRaises(RevisionConflict):
            other.append("pathos", [DomainEvent("test", "pathos")], 0)
        self.assertEqual(len(other.read("pathos")), 1)

    def test_history_pages_use_stable_exclusive_revision_cursors(self) -> None:
        events = [DomainEvent(f"event.{index}", "pathos", {"index": index}) for index in range(7)]
        self.store.append("pathos", events, 0)
        first = self.store.read_page("pathos", limit=3)
        self.assertEqual([item.revision for item in first.records], [7, 6, 5])
        self.assertEqual(first.next_before_revision, 5)
        second = self.store.read_page("pathos", before_revision=first.next_before_revision, limit=3)
        self.assertEqual([item.revision for item in second.records], [4, 3, 2])
        final = self.store.read_page("pathos", before_revision=second.next_before_revision, limit=3)
        self.assertEqual([item.revision for item in final.records], [1])
        self.assertIsNone(final.next_before_revision)
        self.assertEqual(
            [item.event for item in (*first.records, *second.records, *final.records)],
            list(reversed(events)),
        )

    def test_batch_failure_rolls_back_every_event(self) -> None:
        event = DomainEvent("test", "pathos")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append("pathos", [event, event], 0)
        self.assertEqual(self.store.read("pathos"), [])

    def test_invalid_advance_never_writes(self) -> None:
        simulation = Life(self.store, StandInGateway())
        for hours in (0, -1, 169, float("nan"), float("inf"), True):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                simulation.advance(hours)
        self.assertEqual(self.store.read("pathos"), [])

    def test_unknown_database_version_is_rejected(self) -> None:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA user_version = 999")
        connection.close()
        with self.assertRaises(ValueError):
            SQLiteEventStore(self.path)


class ArchitectureTests(unittest.TestCase):
    def test_domain_and_application_do_not_depend_on_adapters(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src/eidos"
        for layer in ("domain", "application", "ports"):
            for path in (root / layer).glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text())):
                    imports = []
                    if isinstance(node, ast.Import):
                        imports = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        imports = [node.module or ""]
                    for name in imports:
                        self.assertFalse(name.startswith("eidos.adapters"), str(path))
                        if layer == "domain":
                            self.assertFalse(
                                name.startswith(("eidos.application", "eidos.ports")), str(path)
                            )
