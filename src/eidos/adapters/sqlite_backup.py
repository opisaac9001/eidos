"""Consistent SQLite backups and read-only integrity verification."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackupReport:
    path: Path
    integrity: str
    schema_version: int
    event_count: int
    job_count: int


def create_backup(source: Path, destination: Path) -> BackupReport:
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if source.resolve() == destination.resolve():
        raise ValueError("Backup destination must differ from the live database")
    if destination.exists():
        raise ValueError("Backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(source) as live, sqlite3.connect(destination) as backup:
            live.backup(backup)
        return verify_backup(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def verify_backup(path: Path) -> BackupReport:
    if not path.is_file():
        raise ValueError("Backup database does not exist")
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "events" not in tables:
            raise ValueError("Backup does not contain an event log")
        event_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        job_count = (
            int(connection.execute("SELECT COUNT(*) FROM cognition_jobs").fetchone()[0])
            if "cognition_jobs" in tables
            else 0
        )
    return BackupReport(path, integrity, schema_version, event_count, job_count)
