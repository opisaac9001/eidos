import tempfile
import unittest
from pathlib import Path

from eidos.adapters.sqlite_backup import create_backup, verify_backup
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


class BackupTests(unittest.TestCase):
    def test_online_backup_passes_integrity_and_replays_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.sqlite3"
            destination = Path(directory) / "backups" / "day-one.sqlite3"
            life = Life(SQLiteEventStore(source), StandInGateway())
            life.advance(24)
            report = create_backup(source, destination)
            self.assertEqual(report.integrity, "ok")
            self.assertEqual(report.schema_version, 2)
            self.assertEqual(report.event_count, len(life.history()))
            restored = Life(SQLiteEventStore(destination), StandInGateway())
            self.assertEqual(restored.snapshot(), life.snapshot())
            self.assertEqual(verify_backup(destination), report)

    def test_backup_never_silently_overwrites_or_accepts_a_non_database(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "live.sqlite3"
            destination = Path(directory) / "backup.sqlite3"
            SQLiteEventStore(source)
            destination.write_text("keep me")
            with self.assertRaisesRegex(ValueError, "already exists"):
                create_backup(source, destination)
            self.assertEqual(destination.read_text(), "keep me")
            with self.assertRaises(Exception):
                verify_backup(destination)


if __name__ == "__main__":
    unittest.main()
