import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.world_packs import import_world_pack
from eidos.domain.world_catalog import project_world_catalog


class WorldPackTests(unittest.TestCase):
    now = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = SQLiteEventStore(Path(self.directory.name) / "world.sqlite3")

    def entity(self, kind, entity_id, name, location="home", **changes):
        value = {
            "entity_kind": kind,
            "entity_id": entity_id,
            "name": name,
            "description": f"A grounded description of {name}.",
            "location_id": location,
            "purpose": "Add another ordinary strand to neighborhood life",
            "color": "#6f8fa3",
            "label": name,
            "x": 48,
            "y": 48,
            "opens_hour": 8,
            "closes_hour": 20,
            "travel_minutes": 18,
        }
        value.update(changes)
        return value

    def write_pack(self, version=1, entities=None, **changes):
        manifest = {
            "schema_version": 1,
            "pack_id": "canal-quarter",
            "version": version,
            "name": "The Canal Quarter",
            "description": "A small connected neighborhood extension.",
            "entities": entities
            or [
                self.entity("place", "reading-room", "The Reading Room"),
                self.entity("person", "imani-cole", "Imani Cole", "reading-room", color="#b37aa5"),
                self.entity("object", "community-radio", "Community radio", "reading-room"),
            ],
        }
        manifest.update(changes)
        path = Path(self.directory.name) / f"pack-{version}.json"
        path.write_text(json.dumps(manifest))
        return path

    def test_pack_is_an_atomic_replayable_addition_using_normal_world_rules(self):
        report = import_world_pack(self.store, self.write_pack(), simulated_at=self.now)
        self.assertEqual(report.status, "imported")
        self.assertEqual(report.entity_count, 3)
        self.assertEqual(report.entity_ids, ("reading-room", "imani-cole", "community-radio"))
        self.assertEqual(report.events_appended, 13)
        history = self.store.read("pathos")
        catalog = project_world_catalog(history)
        self.assertIn("reading-room", catalog.places)
        self.assertIn("imani-cole", catalog.people)
        self.assertIn("community-radio", catalog.object_ids)
        imported = history[-1]
        self.assertEqual(imported.kind, "world.pack_imported")
        self.assertEqual(imported.payload["checksum"], report.checksum)
        self.assertEqual(
            project_world_catalog(SQLiteEventStore(self.store.path).read("pathos")), catalog
        )
        visible = Life(self.store, StandInGateway()).snapshot()["world_packs"]
        self.assertEqual(visible[0]["pack_id"], "canal-quarter")
        self.assertEqual(
            visible[0]["entity_ids"], ["reading-room", "imani-cole", "community-radio"]
        )

    def test_invalid_entity_rejects_the_entire_pack_without_partial_registration(self):
        entities = [
            self.entity("place", "reading-room", "The Reading Room"),
            self.entity("person", "bad-person", "Mara", "reading-room"),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate_name"):
            import_world_pack(self.store, self.write_pack(entities=entities), simulated_at=self.now)
        self.assertEqual(self.store.read("pathos"), [])

    def test_exact_reimport_is_idempotent_but_rewrite_and_version_gaps_fail(self):
        path = self.write_pack()
        first = import_world_pack(self.store, path, simulated_at=self.now)
        revision = len(self.store.read("pathos"))
        second = import_world_pack(self.store, path, simulated_at=self.now)
        self.assertEqual(second.status, "already_imported")
        self.assertEqual(second.entity_ids, first.entity_ids)
        self.assertEqual(len(self.store.read("pathos")), revision)

        rewritten = self.write_pack(description="A rewritten release.")
        with self.assertRaisesRegex(ValueError, "cannot be rewritten"):
            import_world_pack(self.store, rewritten, simulated_at=self.now)
        with self.assertRaisesRegex(ValueError, "version order"):
            import_world_pack(
                self.store,
                self.write_pack(
                    version=3,
                    entities=[self.entity("object", "notice-board", "Notice board")],
                ),
                simulated_at=self.now,
            )

    def test_additive_next_release_can_build_on_the_prior_catalog(self):
        import_world_pack(self.store, self.write_pack(), simulated_at=self.now)
        second = self.write_pack(
            version=2,
            entities=[self.entity("person", "tomas-reed", "Tomas Reed", "reading-room")],
        )
        report = import_world_pack(self.store, second, simulated_at=self.now)
        self.assertEqual((report.version, report.entity_ids), (2, ("tomas-reed",)))
        self.assertIn("tomas-reed", project_world_catalog(self.store.read("pathos")).people)

    def test_manifest_shape_time_and_initial_version_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "begin at version 1"):
            import_world_pack(
                self.store,
                self.write_pack(
                    version=2,
                    entities=[self.entity("object", "notice-board", "Notice board")],
                ),
                simulated_at=self.now,
            )
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            import_world_pack(
                self.store,
                self.write_pack(),
                simulated_at=datetime(2026, 2, 1, 12),
            )
        with self.assertRaisesRegex(ValueError, "schema version 1"):
            import_world_pack(
                self.store,
                self.write_pack(unexpected=True),
                simulated_at=self.now,
            )
        oversized = Path(self.directory.name) / "oversized.json"
        oversized.write_text(" " * 1_000_001)
        with self.assertRaisesRegex(ValueError, "one megabyte"):
            import_world_pack(self.store, oversized, simulated_at=self.now)

    def test_bundled_canal_quarter_release_is_valid(self):
        path = Path(__file__).resolve().parents[1] / "world_packs" / "canal-quarter-v1.json"
        report = import_world_pack(self.store, path, simulated_at=self.now)
        self.assertEqual(report.entity_ids, ("reading-room", "imani-cole", "community-radio"))


if __name__ == "__main__":
    unittest.main()
