"""Install a checked source snapshot with rollback; preserve routes and world time.

Server-only operator script. Requires a verified staging directory, a paused API,
and an existing sudo credential. It never resumes the clock or restores a database
over a newer one. Previous code and the final pre-change database are retained.
"""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from eidos.adapters.sqlite_backup import create_backup

ROOT = Path("/srv/eidos")
LIVE = Path("/var/lib/eidos/observatory.sqlite3")
ROUTES = Path("/etc/eidos/model-routes.json")


def api_state():
    with urllib.request.urlopen("http://127.0.0.1:8767/api/state", timeout=15) as response:
        return json.load(response)


def service(action):
    subprocess.run(["sudo", "-n", "systemctl", action, "eidos"], check=True, timeout=150)


def event_fingerprint(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT * FROM events ORDER BY aggregate_id, revision").fetchall()
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def run(stage, release):
    stage = stage.resolve()
    if stage.parent != ROOT or not stage.name.startswith("staging-"):
        raise ValueError("Expected a staging directory immediately under /srv/eidos")
    if not release.isalnum():
        raise ValueError("Use an alphanumeric release identifier")
    prepared = ROOT / f"src-next-{release}"
    previous = ROOT / f"src-before-{release}"
    failed = ROOT / f"src-failed-{release}"
    backup = Path(f"/srv/eidos-data/eidos/backups/pre-install-{release}.sqlite3")
    if any(path.exists() for path in (prepared, previous, failed, backup)):
        raise ValueError("Release paths already exist; do not overwrite a previous attempt")
    before = api_state()
    if before["config"]["running"]:
        raise ValueError("Pause the live simulation before installing")
    route_hash = hashlib.sha256(ROUTES.read_bytes()).hexdigest()
    shutil.copytree(stage / "src", prepared, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    service("stop")
    swapped = False
    try:
        report = create_backup(LIVE, backup)
        fingerprint = event_fingerprint(backup)
        (ROOT / "src").rename(previous)
        swapped = True
        prepared.rename(ROOT / "src")
        service("start")
        after = None
        for _ in range(20):
            try:
                after = api_state()
                break
            except (OSError, ValueError):
                time.sleep(1)
        if after is None:
            raise RuntimeError("The updated API did not become healthy")
        if after["config"]["running"] or after["time"] != before["time"]:
            raise RuntimeError("Unexpected live clock/config change")
        if after["revision"] != report.event_count or event_fingerprint(LIVE) != fingerprint:
            raise RuntimeError("Canonical event history changed during installation")
        if hashlib.sha256(ROUTES.read_bytes()).hexdigest() != route_hash:
            raise RuntimeError("Model routing changed unexpectedly")
        if not {"activity_execution", "time_budget"}.issubset(after):
            raise RuntimeError("Expected new snapshot fields are missing")
        print(
            json.dumps(
                {
                    "installed": True,
                    "backup": str(backup),
                    "previous_source": str(previous),
                    "revision": after["revision"],
                    "time": after["time"],
                    "running": after["config"]["running"],
                    "history_identical": True,
                    "routing_identical": True,
                },
                indent=2,
            ),
            flush=True,
        )
    except Exception:
        service("stop")
        if swapped:
            if (ROOT / "src").exists():
                (ROOT / "src").rename(failed)
            previous.rename(ROOT / "src")
        service("start")
        print(
            "Previous code restored. Database was not overwritten; inspect before further changes.",
            flush=True,
        )
        raise


if __name__ == "__main__":
    run(Path(sys.argv[1]), sys.argv[2])
