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
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent
from eidos.ports.event_store import MaterializedProjection, RevisionConflict, StateCheckpoint


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
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_materialized_projection_is_versioned_anchored_and_disposable(self) -> None:
        events = [DomainEvent("test", "pathos"), DomainEvent("test", "pathos")]
        self.store.append("pathos", events, 0)
        projection = MaterializedProjection(
            "pathos", "memory-index", 1, 2, str(events[-1].event_id), {"ids": ["one"]}
        )
        self.store.save_projection(projection)
        self.assertEqual(self.store.load_projection("pathos", "memory-index", 1, 2), projection)
        self.assertIsNone(self.store.load_projection("pathos", "memory-index", 2, 2))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE materialized_projections SET state_json = ? "
                "WHERE aggregate_id = ? AND name = ?",
                ('{"ids": ["corrupt"]}', "pathos", "memory-index"),
            )
        self.assertIsNone(self.store.load_projection("pathos", "memory-index", 1, 2))

    def test_materialized_projection_rejects_bad_or_backward_anchor(self) -> None:
        events = [DomainEvent("test", "pathos"), DomainEvent("test", "pathos")]
        self.store.append("pathos", events, 0)
        with self.assertRaises(ValueError):
            self.store.save_projection(
                MaterializedProjection("pathos", "memory-index", 1, 2, "wrong", {})
            )
        self.store.save_projection(
            MaterializedProjection("pathos", "memory-index", 1, 2, str(events[-1].event_id), {})
        )
        with self.assertRaises(ValueError):
            self.store.save_projection(
                MaterializedProjection("pathos", "memory-index", 1, 1, str(events[0].event_id), {})
            )

    def test_checkpoint_is_anchored_rebuildable_and_corruption_falls_back(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(8)
        history = life.history()
        checkpoint = self.store.load_checkpoint("pathos", len(history))
        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(checkpoint.last_event_id, str(history[-1].event_id))
        self.assertEqual(life._project_state(history), Life.project(history))

    def test_life_keeps_memory_projection_at_the_committed_revision(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(24)
        history = life.history()
        projection = self.store.load_projection("pathos", "memory-index", 1, len(history))
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(projection.revision, len(history))
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(restarted.snapshot()["indexes"]["memory_revision"], len(history))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE state_checkpoints SET state_json = ? WHERE aggregate_id = ?",
                ('{"energy": 999}', "pathos"),
            )
        self.assertIsNone(self.store.load_checkpoint("pathos", len(history)))
        self.assertEqual(life._project_state(history), Life.project(history))

    def test_life_materializes_planning_and_semantic_corruption_falls_back(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(24)
        history = life.history()
        projection = self.store.load_projection("pathos", "planning", 1, len(history))
        self.assertIsNotNone(projection)
        assert projection is not None
        expected = life._planning(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "planning",
                1,
                len(history),
                str(history[-1].event_id),
                {
                    **projection.state,
                    "goals": [
                        {**value, "progress": "invalid"} for value in projection.state["goals"]
                    ],
                },
            )
        )
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(restarted._planning(history), expected)

    def test_materialized_planning_applies_the_event_tail_after_its_anchor(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(8)
        history = life.history()
        tail = DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": "tail-goal",
                "title": "A goal added after the checkpoint",
                "motivation": "Prove incremental replay",
            },
        )
        self.store.append("pathos", [tail], len(history))
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        projected = restarted._planning(restarted.history())
        self.assertIn("tail-goal", projected.goals)

    def test_life_materializes_beliefs_at_the_committed_revision(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(24)
        history = life.history()
        projection = self.store.load_projection("pathos", "beliefs", 1, len(history))
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(projection.revision, len(history))
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(restarted._beliefs(history), project_beliefs(history))

    def test_life_materializes_relationships_at_the_committed_revision(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(24)
        history = life.history()
        projection = self.store.load_projection("pathos", "relationships", 1, len(history))
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(projection.revision, len(history))
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(restarted.snapshot()["people"], life.snapshot()["people"])

    def test_life_materializes_consolidation_sources_at_the_committed_revision(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(24)
        history = life.history()
        projection = self.store.load_projection("pathos", "consolidation-index", 1, len(history))
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(projection.revision, len(history))
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        self.assertEqual(
            restarted._consolidation_index(history).memory_ids,
            life._consolidation_index(history).memory_ids,
        )

    def test_checkpoint_refuses_an_unmatched_or_backward_anchor(self) -> None:
        events = [DomainEvent("test", "pathos"), DomainEvent("test", "pathos")]
        self.store.append("pathos", events, 0)
        with self.assertRaises(ValueError):
            self.store.save_checkpoint(StateCheckpoint("pathos", 2, "wrong", {}))
        self.store.save_checkpoint(StateCheckpoint("pathos", 2, str(events[1].event_id), {}))
        with self.assertRaises(ValueError):
            self.store.save_checkpoint(StateCheckpoint("pathos", 1, str(events[0].event_id), {}))

    def test_semantically_invalid_checkpoint_falls_back_to_full_replay(self) -> None:
        life = Life(self.store, StandInGateway())
        life.advance(8)
        history = life.history()
        self.store.save_checkpoint(
            StateCheckpoint(
                "pathos",
                len(history),
                str(history[-1].event_id),
                {
                    "pathos_id": "pathos",
                    "location_id": "home",
                    "simulated_at": history[-1].payload["simulated_at"].isoformat(),
                    "energy": 99,
                    "valence": 0,
                    "arousal": 0.5,
                    "rest": 0.5,
                    "connection": 0.5,
                    "curiosity": 0.5,
                    "mastery": 0.5,
                    "awake": True,
                },
            )
        )
        self.assertEqual(life._project_state(history), Life.project(history))

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
