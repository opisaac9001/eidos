"""Verified, non-merging experiment branches of a persistent Eidos life."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping
from uuid import UUID, uuid4

from eidos.adapters.sqlite_backup import BackupReport, create_backup, verify_backup


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    path: Path
    experiment_id: str
    name: str
    purpose: str
    model_profile: str | None
    created_at: str
    source_path: str
    fork_event_count: int
    fork_revision: int
    fork_last_event_id: str | None
    prefix_checksum: str
    discarded_jobs: int
    backup: BackupReport


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    experiment_id: str
    name: str
    fork_event_count: int
    canonical_event_count: int
    experiment_event_count: int
    canonical_events_since_fork: int
    experiment_events_since_fork: int
    canonical_kinds_since_fork: Mapping[str, int]
    experiment_kinds_since_fork: Mapping[str, int]
    canonical_review: LifeEvidenceReview
    experiment_review: LifeEvidenceReview
    histories_diverged: bool


@dataclass(frozen=True, slots=True)
class LifeEvidenceReview:
    event_count: int
    simulated_hours: float
    distinct_event_kinds: int
    activities: tuple[str, ...]
    conversation_scenes: int
    conversation_turns: int
    conversation_partners: tuple[str, ...]
    conversation_topics: tuple[str, ...]
    relationship_contacts: int
    memories: int
    thoughts: int
    dreams: int
    dream_motifs: tuple[str, ...]
    emotion_labels: tuple[str, ...]
    minimum_valence: float | None
    maximum_valence: float | None
    intentions_adopted: int
    intentions_completed: int
    plans_created: int
    plans_completed: int
    independent_npc_actions: int
    active_npc_actors: tuple[str, ...]
    world_events: int
    model_calls: int
    model_failures: int
    narrative_lines: int
    repeated_narrative_lines: int
    narrative_repetition_rate: float
    narrative_repetitions_by_kind: Mapping[str, int]


_EVENT_COLUMNS = (
    "aggregate_id, revision, event_id, kind, occurred_at, payload, "
    "schema_version, causation_id, correlation_id"
)


def _require_text(value: str, label: str, maximum: int) -> str:
    clean = value.strip()
    if not clean:
        raise ValueError(f"Experiment {label} is required")
    if len(clean) > maximum:
        raise ValueError(f"Experiment {label} must be at most {maximum} characters")
    return clean


def _event_rows(
    connection: sqlite3.Connection, limit: int | None = None
) -> list[tuple[object, ...]]:
    suffix = " LIMIT ?" if limit is not None else ""
    parameters: tuple[object, ...] = (limit,) if limit is not None else ()
    return list(
        connection.execute(
            f"SELECT {_EVENT_COLUMNS} FROM events ORDER BY rowid{suffix}", parameters
        ).fetchall()
    )


def _checksum(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded.encode())
    return digest.hexdigest()


def _history_anchor(path: Path, limit: int | None = None) -> tuple[int, int, str | None, str]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = _event_rows(connection, limit)
    revision = max((int(str(row[1])) for row in rows if row[0] == "pathos"), default=0)
    last_event_id = str(rows[-1][2]) if rows else None
    return len(rows), revision, last_event_id, _checksum(rows)


def create_experiment(
    source: Path,
    destination: Path,
    *,
    name: str,
    purpose: str,
    model_profile: str | None = None,
) -> ExperimentReport:
    """Fork a consistent life snapshot without changing or later merging the source."""

    clean_name = _require_text(name, "name", 120)
    clean_purpose = _require_text(purpose, "purpose", 1000)
    clean_profile = (
        _require_text(model_profile, "model profile", 200) if model_profile is not None else None
    )
    create_backup(source, destination)
    try:
        event_count, revision, last_event_id, prefix_checksum = _history_anchor(destination)
        experiment_id = str(uuid4())
        created_at = datetime.now().astimezone().isoformat()
        with sqlite3.connect(destination) as connection:
            tables = {
                str(row[0])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            discarded_jobs = (
                int(connection.execute("SELECT COUNT(*) FROM cognition_jobs").fetchone()[0])
                if "cognition_jobs" in tables
                else 0
            )
            if "cognition_jobs" in tables:
                connection.execute("DELETE FROM cognition_jobs")
            connection.execute("""
                CREATE TABLE experiment_provenance (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    experiment_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    model_profile TEXT,
                    created_at TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    fork_event_count INTEGER NOT NULL,
                    fork_revision INTEGER NOT NULL,
                    fork_last_event_id TEXT,
                    prefix_checksum TEXT NOT NULL,
                    discarded_jobs INTEGER NOT NULL
                )
            """)
            connection.execute(
                "INSERT INTO experiment_provenance VALUES (1,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    experiment_id,
                    clean_name,
                    clean_purpose,
                    clean_profile,
                    created_at,
                    str(source.resolve()),
                    event_count,
                    revision,
                    last_event_id,
                    prefix_checksum,
                    discarded_jobs,
                ),
            )
        return inspect_experiment(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def inspect_experiment(path: Path) -> ExperimentReport:
    backup = verify_backup(path)
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_provenance'"
        ).fetchone()
        if table is None:
            raise ValueError("Database is not an Eidos experiment branch")
        rows = connection.execute(
            "SELECT experiment_id,name,purpose,model_profile,created_at,source_path,"
            "fork_event_count,fork_revision,fork_last_event_id,prefix_checksum,discarded_jobs "
            "FROM experiment_provenance"
        ).fetchall()
    if len(rows) != 1:
        raise ValueError("Experiment provenance must contain exactly one record")
    row = rows[0]
    try:
        UUID(str(row[0]))
    except ValueError as error:
        raise ValueError("Experiment ID is invalid") from error
    created_at = datetime.fromisoformat(str(row[4]))
    if created_at.utcoffset() is None:
        raise ValueError("Experiment creation time must be timezone-aware")
    source_path = _require_text(str(row[5]), "source path", 4096)
    fork_event_count = int(row[6])
    discarded_jobs = int(row[10])
    if fork_event_count < 0 or fork_event_count > backup.event_count:
        raise ValueError("Experiment fork event count is invalid")
    if discarded_jobs < 0:
        raise ValueError("Experiment discarded job count is invalid")
    count, revision, last_event_id, prefix_checksum = _history_anchor(path, fork_event_count)
    if (
        count != fork_event_count
        or revision != int(row[7])
        or last_event_id != row[8]
        or prefix_checksum != row[9]
    ):
        raise ValueError("Experiment history no longer matches its immutable fork anchor")
    return ExperimentReport(
        path,
        str(row[0]),
        _require_text(str(row[1]), "name", 120),
        _require_text(str(row[2]), "purpose", 1000),
        _require_text(str(row[3]), "model profile", 200) if row[3] is not None else None,
        created_at.isoformat(),
        source_path,
        fork_event_count,
        int(row[7]),
        str(row[8]) if row[8] is not None else None,
        str(row[9]),
        discarded_jobs,
        backup,
    )


def _kind_counts(path: Path, offset: int) -> dict[str, int]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT kind, COUNT(*) FROM (SELECT kind FROM events ORDER BY rowid LIMIT -1 OFFSET ?) "
            "GROUP BY kind ORDER BY kind",
            (offset,),
        ).fetchall()
    return {str(kind): int(count) for kind, count in rows}


def _payload(row: tuple[object, ...]) -> dict[str, object]:
    value = json.loads(str(row[5]))
    return value if isinstance(value, dict) else {}


def _payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, dict) and set(value) == {"$datetime"}:
        value = value["$datetime"]
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _simulated_time(row: tuple[object, ...]) -> datetime | None:
    raw_time = _payload_text(_payload(row), "simulated_at")
    if not raw_time:
        return None
    try:
        parsed = datetime.fromisoformat(raw_time)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def review_life_evidence(path: Path, offset: int = 0) -> LifeEvidenceReview:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        all_rows = _event_rows(connection)
    rows = all_rows[offset:]
    fork_times: list[datetime] = []
    for prefix_row in all_rows[:offset]:
        prefix_time = _simulated_time(prefix_row)
        if prefix_time is not None:
            fork_times.append(prefix_time)
    kinds = Counter(str(row[3]) for row in rows)
    activities: set[str] = set()
    partners: set[str] = set()
    topics: set[str] = set()
    motifs: set[str] = set()
    emotion_labels: set[str] = set()
    npc_actors: set[str] = set()
    valences: list[float] = []
    simulated_times: list[datetime] = []
    narrative: list[str] = []
    narrative_by_kind: dict[str, list[str]] = {}
    model_failures = 0
    relationship_contacts = 0
    for row in rows:
        kind = str(row[3])
        payload = _payload(row)
        if simulated_time := _simulated_time(row):
            simulated_times.append(simulated_time)
        if kind in {"activity.completed", "memory.recorded"}:
            activity = _payload_text(payload, "activity")
            if activity:
                activities.add(activity)
        if kind == "scene.started":
            relationship_contacts += 1
            partner = _payload_text(payload, "partner_id")
            if partner:
                partners.add(partner)
        if kind == "scene.turn_taken":
            topic = _payload_text(payload, "topic_id")
            if topic:
                topics.add(topic)
        if kind == "dream.recorded":
            motif = _payload_text(payload, "motif")
            if motif:
                motifs.add(motif)
        if kind == "emotion.sampled":
            label = _payload_text(payload, "label")
            if label:
                emotion_labels.add(label)
            value = payload.get("valence")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                valences.append(float(value))
        if kind == "npc.activity_recorded":
            actor = _payload_text(payload, "actor_id")
            if actor:
                npc_actors.add(actor)
        if kind == "role.completed" and payload.get("status") != "ok":
            model_failures += 1
        if kind == "phone.call_received":
            relationship_contacts += 1
        if kind == "conversation.message" and payload.get("speaker") == "you":
            relationship_contacts += 1
        source_narrative = kind in {
            "conversation.message",
            "thought.recorded",
            "dream.recorded",
            "scene.turn_taken",
            "speech.delivered",
            "npc.encountered",
            "reflection.recorded",
            "day.summarized",
        } or (
            kind == "memory.recorded"
            and payload.get("source") in {"authored-routine", "lived-activity"}
        )
        if source_narrative:
            text = (
                None
                if kind == "conversation.message" and payload.get("speaker") == "you"
                else _payload_text(payload, "text")
            )
            if text:
                normalized = " ".join(text.casefold().split())
                narrative.append(normalized)
                narrative_by_kind.setdefault(kind, []).append(normalized)
    repeated = sum(count - 1 for count in Counter(narrative).values() if count > 1)
    repetitions_by_kind = {
        kind: sum(count - 1 for count in Counter(lines).values() if count > 1)
        for kind, lines in sorted(narrative_by_kind.items())
    }
    simulated_hours = 0.0
    if simulated_times and fork_times:
        simulated_hours = max(0.0, (max(simulated_times) - max(fork_times)).total_seconds() / 3600)
    elif len(simulated_times) > 1:
        simulated_hours = max(
            0.0, (max(simulated_times) - min(simulated_times)).total_seconds() / 3600
        )
    return LifeEvidenceReview(
        event_count=len(rows),
        simulated_hours=round(simulated_hours, 2),
        distinct_event_kinds=len(kinds),
        activities=tuple(sorted(activities)),
        conversation_scenes=kinds["scene.started"],
        conversation_turns=kinds["scene.turn_taken"],
        conversation_partners=tuple(sorted(partners)),
        conversation_topics=tuple(sorted(topics)),
        relationship_contacts=relationship_contacts,
        memories=kinds["memory.recorded"],
        thoughts=kinds["thought.recorded"],
        dreams=kinds["dream.recorded"],
        dream_motifs=tuple(sorted(motifs)),
        emotion_labels=tuple(sorted(emotion_labels)),
        minimum_valence=round(min(valences), 3) if valences else None,
        maximum_valence=round(max(valences), 3) if valences else None,
        intentions_adopted=kinds["intention.adopted"],
        intentions_completed=kinds["intention.completed"],
        plans_created=(
            kinds["schedule.created"] + kinds["npc.plan_created"] + kinds["self_project.accepted"]
        ),
        plans_completed=(
            kinds["schedule.completed"]
            + kinds["npc.plan_completed"]
            + kinds["self_project.completed"]
        ),
        independent_npc_actions=kinds["npc.activity_recorded"],
        active_npc_actors=tuple(sorted(npc_actors)),
        world_events=kinds["world_event.occurred"],
        model_calls=kinds["role.completed"],
        model_failures=model_failures,
        narrative_lines=len(narrative),
        repeated_narrative_lines=repeated,
        narrative_repetition_rate=round(repeated / len(narrative), 4) if narrative else 0.0,
        narrative_repetitions_by_kind=repetitions_by_kind,
    )


def compare_experiment(canonical: Path, experiment: Path) -> ExperimentComparison:
    report = inspect_experiment(experiment)
    canonical_backup = verify_backup(canonical)
    if canonical_backup.event_count < report.fork_event_count:
        raise ValueError("Canonical life is older than the experiment fork")
    count, _, last_event_id, prefix_checksum = _history_anchor(canonical, report.fork_event_count)
    if (
        count != report.fork_event_count
        or last_event_id != report.fork_last_event_id
        or prefix_checksum != report.prefix_checksum
    ):
        raise ValueError("Experiment was not forked from this canonical life")
    canonical_kinds = _kind_counts(canonical, report.fork_event_count)
    experiment_kinds = _kind_counts(experiment, report.fork_event_count)
    canonical_ids = _event_ids_after(canonical, report.fork_event_count)
    experiment_ids = _event_ids_after(experiment, report.fork_event_count)
    return ExperimentComparison(
        report.experiment_id,
        report.name,
        report.fork_event_count,
        canonical_backup.event_count,
        report.backup.event_count,
        canonical_backup.event_count - report.fork_event_count,
        report.backup.event_count - report.fork_event_count,
        canonical_kinds,
        experiment_kinds,
        review_life_evidence(canonical, report.fork_event_count),
        review_life_evidence(experiment, report.fork_event_count),
        canonical_ids != experiment_ids,
    )


def _event_ids_after(path: Path, offset: int) -> list[str]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT event_id FROM events ORDER BY rowid LIMIT -1 OFFSET ?", (offset,)
            )
        ]
