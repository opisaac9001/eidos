import ast
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.application.simulation import Simulation
from eidos.domain.events import DomainEvent
from eidos.ports.event_store import RevisionConflict


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "world.sqlite3"
        self.store = SQLiteEventStore(self.path)

    def test_day_survives_restart_without_repeating_memories(self) -> None:
        first = Simulation(self.store)
        first.advance(9)
        restarted = Simulation(SQLiteEventStore(self.path))
        self.assertEqual(first.state(), restarted.state())
        restarted.advance(15)
        whole = Simulation(SQLiteEventStore(Path(self.directory.name) / "whole.sqlite3"))
        whole.advance(24)
        self.assertEqual(restarted.state(), whole.state())
        self.assertEqual([dict(e.payload) for e in restarted.journal()],
                         [dict(e.payload) for e in whole.journal()])
        self.assertEqual(len(restarted.journal()), 7)

    def test_stale_writer_cannot_overwrite_events(self) -> None:
        other = SQLiteEventStore(self.path)
        self.store.append("pathos", [DomainEvent("test", "pathos")], 0)
        with self.assertRaises(RevisionConflict):
            other.append("pathos", [DomainEvent("test", "pathos")], 0)
        self.assertEqual(len(other.read("pathos")), 1)

    def test_batch_failure_rolls_back_every_event(self) -> None:
        event = DomainEvent("test", "pathos")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append("pathos", [event, event], 0)
        self.assertEqual(self.store.read("pathos"), [])

    def test_invalid_advance_never_writes(self) -> None:
        simulation = Simulation(self.store)
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
                            self.assertFalse(name.startswith(("eidos.application", "eidos.ports")),
                                             str(path))
