"""Loopback-only operator server and serialized simulation worker."""

import hmac
import json
import logging
import mimetypes
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable, Iterator
from urllib.parse import parse_qs, urlsplit

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.events import DomainEvent
from eidos.ports.event_store import RevisionConflict
from eidos.ports.job_store import JobConflict
from eidos.ports.model_gateway import ModelGateway
from eidos.ports.news import NewsSource
from eidos.ports.town_signals import TownSignalSource

STATIC = Path(__file__).parent / "web"
logger = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self,
        life: Life,
        interval: float = 3,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
        realtime_quantum_seconds: float = 300,
        operator_token: str | None = None,
    ) -> None:
        self.life = life
        # Operator controls change time and expose private history; they need this token.
        # The switchable model setup behind the Models page, when this server has one.
        self.models: Any = None
        self.operator_token = (
            operator_token or os.environ.get("EIDOS_OPERATOR_TOKEN") or secrets.token_urlsafe(18)
        )
        self.interval = interval
        self.clock = clock
        self.sleeper = sleeper
        self.realtime_quantum_seconds = realtime_quantum_seconds
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.error: str | None = None
        self.ticks = 0
        self.thread: threading.Thread | None = None
        self.cached: dict[str, Any] | None = None
        self.working = False
        self.realtime_pending_seconds = 0.0
        self.last_wall_tick = self.clock()
        self.realtime_suppressed_until = self.last_wall_tick
        self.live_reply_speech: dict[str, float] = {}

    def start(self) -> None:
        with self.lock:
            self.life.bootstrap()
            config = self.life.snapshot()["config"]
            # Resume is explicit: downtime never creates an unbounded catch-up burst.
            if config["running"]:
                self.life.configure(
                    False,
                    config["minutes_per_tick"],
                    config.get("clock_mode", "realtime"),
                )
            self.cached = self.life.snapshot()
            self.realtime_pending_seconds = 0.0
            self.last_wall_tick = self.clock()
        self.thread = threading.Thread(target=self._loop, name="eidos-chronos", daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self.stop.wait(self.interval):
            wall_now = self.clock()
            with self.lock:
                config: dict[str, Any] = {
                    "running": False,
                    "clock_mode": "realtime",
                    "minutes_per_tick": 15,
                }
                try:
                    config = self.life.snapshot()["config"]
                    if config["running"]:
                        if config.get("clock_mode", "realtime") == "realtime":
                            self._accrue_realtime(wall_now)
                            if self.realtime_pending_seconds < self.realtime_quantum_seconds:
                                continue
                            self.working = True
                            self._commit_realtime_pending()
                        else:
                            self.realtime_pending_seconds = 0.0
                            self.last_wall_tick = wall_now
                            self.working = True
                            self.life.advance(config["minutes_per_tick"] / 60)
                        self.ticks += 1
                        self.error = None
                        self.cached = self.life.snapshot()
                    else:
                        self.realtime_pending_seconds = 0.0
                        self.last_wall_tick = wall_now
                except Exception:
                    logger.exception("Simulation tick failed")
                    self.error = "The simulation paused after a tick failed. Its last committed state is safe."
                    try:
                        self.life.configure(
                            False,
                            config["minutes_per_tick"],
                            config.get("clock_mode", "realtime"),
                        )
                    except Exception:
                        logger.exception("Could not persist pause")
                    self.stop.set()
                finally:
                    self.working = False

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=30)
        with self.lock:
            config = self.life.snapshot()["config"]
            wall_now = self.clock()
            self._accrue_realtime(wall_now)
            if (
                self.error is None
                and config["running"]
                and config.get("clock_mode", "realtime") == "realtime"
                and self.realtime_pending_seconds > 0
            ):
                self._commit_realtime_pending()
                self.ticks += 1
                self.cached = self.life.snapshot()
        close_gateway = getattr(self.life.gateway, "close", None)
        if callable(close_gateway):
            close_gateway()

    @contextmanager
    def mutation(self) -> Iterator[None]:
        with self.lock:
            self.working = True
            try:
                config = self.life.snapshot()["config"]
                if config["running"] and config.get("clock_mode", "realtime") == "realtime":
                    self._accrue_realtime(self.clock())
                    if self.realtime_pending_seconds > 0:
                        self._commit_realtime_pending()
                yield
            finally:
                self.working = False
                self.cached = self.life.snapshot()

    def _accrue_realtime(self, wall_now: float) -> None:
        self.realtime_pending_seconds += max(
            0.0, wall_now - max(self.last_wall_tick, self.realtime_suppressed_until)
        )
        self.last_wall_tick = wall_now

    def _commit_realtime_pending(self) -> None:
        """Commit exact wall time and pulse Murmur at crossed quarter hours."""
        remaining = self.realtime_pending_seconds
        self.realtime_pending_seconds = 0.0
        simulated_at = datetime.fromisoformat(self.life.snapshot()["time"])
        try:
            while remaining > 0.000001:
                seconds_into_quarter = (
                    (simulated_at.minute % 15) * 60
                    + simulated_at.second
                    + simulated_at.microsecond / 1_000_000
                )
                until_boundary = 900 - seconds_into_quarter if seconds_into_quarter else 900
                step = min(remaining, until_boundary)
                self.life.advance(step / 3600)
                remaining -= step
                simulated_at += timedelta(seconds=step)
                if abs(step - until_boundary) <= 0.000001:
                    self.life.pulse_inner_stream()
        except Exception:
            # Completed slices are already durable; retain only wall time that was
            # not committed so a recoverable failure cannot silently lose it.
            self.realtime_pending_seconds += remaining
            raise

    def pace_live_reply(self, previous_message_ids: set[str], started_at: float) -> float:
        """Hold listening/thought, then expose speech on a shared wall-clock timeline."""
        conversations = self.life.snapshot().get("conversations", [])
        new_replies = [
            item
            for item in conversations
            if str(item.get("id")) not in previous_message_ids
            and item.get("speaker") == "pathos"
            and item.get("channel") == "live_visit"
            and isinstance(item.get("pacing_total_seconds"), (int, float))
        ]
        if not new_replies:
            return 0.0
        thought_duration = max(
            float(item.get("pacing_listening_seconds", 0))
            + float(item.get("pacing_thinking_seconds", 0))
            for item in new_replies
        )
        remaining = max(0.0, started_at + thought_duration - self.clock())
        if remaining:
            self.sleeper(remaining)
        speech_started = self.clock()
        for item in new_replies:
            speech_ends = speech_started + float(item.get("pacing_speaking_seconds", 0))
            self.live_reply_speech[str(item["id"])] = speech_ends
            self.realtime_suppressed_until = max(self.realtime_suppressed_until, speech_ends)
        # Life already advanced its simulated clock by the whole exchange. Chronos
        # excludes both this held thought and the still-unfolding spoken interval.
        self.last_wall_tick = speech_started
        return remaining

    def live_reply_in_progress(self) -> bool:
        """Keep all clients from talking over a reply that is still being spoken."""
        now = self.clock()
        expired = [
            message_id for message_id, ends_at in self.live_reply_speech.items() if ends_at <= now
        ]
        for message_id in expired:
            self.live_reply_speech.pop(message_id, None)
        return bool(self.live_reply_speech)

    def snapshot(self) -> dict[str, Any]:
        if self.lock.acquire(blocking=False):
            try:
                self.cached = self.life.snapshot()
            finally:
                self.lock.release()
        if self.cached is None:
            raise RuntimeError("Runtime has not initialized")
        job_store = getattr(self.life.gateway, "jobs", None)
        supervisor = getattr(self.life.gateway, "supervisor", None)
        jobs = job_store.list_jobs(100) if job_store else []
        job_counts = {
            status: sum(job.status == status for job in jobs)
            for status in ("queued", "running", "completed", "failed", "cancelled")
        }
        snapshot = dict(self.cached)
        now = self.clock()
        paced_conversations = []
        for item in snapshot.get("conversations", []):
            speech_ends = self.live_reply_speech.get(str(item.get("id")))
            if speech_ends is None:
                paced_conversations.append(item)
                continue
            remaining = max(0.0, speech_ends - now)
            if remaining <= 0:
                self.live_reply_speech.pop(str(item.get("id")), None)
                paced_conversations.append(item)
                continue
            paced_conversations.append(
                {**item, "pacing_phase": "speaking", "pacing_remaining_seconds": remaining}
            )
        snapshot["conversations"] = paced_conversations
        return {
            **snapshot,
            "jobs": {
                "counts": job_counts,
                "recent": [
                    {
                        "id": str(job.job_id),
                        "capability": job.capability,
                        "status": job.status,
                        "attempts": job.attempts,
                        "task_version": job.task_version,
                        "max_output_tokens": job.max_output_tokens,
                        "temperature": job.temperature,
                        "resolved_model": job.resolved_model,
                        "backend": job.backend,
                        "prompt_tokens": job.prompt_tokens,
                        "output_tokens": job.output_tokens,
                        "error_code": job.error_code,
                        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
                    }
                    for job in jobs[:20]
                ],
                "supervisor": supervisor.snapshot() if supervisor else None,
            },
            "runtime": {
                "ticks": self.ticks,
                "interval_seconds": self.interval,
                "error": self.error,
                "worker_alive": bool(self.thread and self.thread.is_alive()),
                "working": self.working,
                "realtime_pending_seconds": round(self.realtime_pending_seconds, 3),
            },
        }


def make_handler(runtime: Runtime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            logger.debug(format, *args)

        def local_request(self) -> bool:
            host = self.headers.get("Host", "")
            port = int(getattr(self.server, "server_port"))
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if host not in allowed:
                self.respond(403, {"error": "This server accepts local requests only"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{value}" for value in allowed}:
                self.respond(403, {"error": "Cross-origin requests are not accepted"})
                return False
            return True

        def operator_request(self) -> bool:
            supplied = self.headers.get("X-Eidos-Operator", "")
            if not hmac.compare_digest(supplied.encode(), runtime.operator_token.encode()):
                self.respond(403, {"error": "This control needs the operator token"})
                return False
            return True

        def respond(self, status: int, value: Any, content_type: str = "application/json") -> None:
            body = (
                json.dumps(value, allow_nan=False).encode()
                if content_type == "application/json"
                else value
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if path in OPERATOR_GET_PATHS and not self.operator_request():
                return
            if path == "/api/state":
                self.respond(200, runtime.snapshot())
            elif path == "/api/catch-up/preview":
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    hours = float(query.get("hours", ["24"])[0])
                    with runtime.lock:
                        preview = runtime.life.preview_catch_up(hours)
                    self.respond(
                        200,
                        {name: getattr(preview, name) for name in preview.__dataclass_fields__},
                    )
                except (ValueError, TypeError) as error:
                    self.respond(400, {"error": str(error)})
            elif path == "/api/events":
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    limit = int(query.get("limit", ["100"])[0])
                    before_value = query.get("before", [None])[0]
                    before = int(before_value) if before_value is not None else None
                    with runtime.lock:
                        page = runtime.life.store.read_page(
                            "pathos", before_revision=before, limit=limit
                        )
                    self.respond(
                        200,
                        {
                            "events": [
                                {"revision": record.revision, **event_json(record.event)}
                                for record in page.records
                            ],
                            "next_before": page.next_before_revision,
                        },
                    )
                except (ValueError, TypeError) as error:
                    self.respond(400, {"error": str(error)})
            elif path == "/api/memories":
                try:
                    query_values = parse_qs(urlsplit(self.path).query)
                    offset = int(query_values.get("offset", ["0"])[0])
                    limit = int(query_values.get("limit", ["50"])[0])
                    query_text = query_values.get("q", [""])[0]
                    category = query_values.get("category", ["all"])[0]
                    with runtime.lock:
                        memory_page = runtime.life.browse_memories(
                            offset=offset,
                            limit=limit,
                            query=query_text,
                            category=category,
                        )
                    self.respond(200, memory_page)
                except (ValueError, TypeError) as error:
                    self.respond(400, {"error": str(error)})
            elif path == "/api/export":
                with runtime.lock:
                    events = [event_json(event) for event in runtime.life.history()]
                self.respond(200, {"schema": 2, "events": events})
            elif path in ("/", "/operator", "/app.js", "/style.css"):
                asset = STATIC / ("index.html" if path in {"/", "/operator"} else path[1:])
                self.respond(
                    200, asset.read_bytes(), mimetypes.guess_type(asset)[0] or "text/plain"
                )
            elif path == "/api/models":
                if runtime.models is None:
                    self.respond(404, {"error": "This server runs a fixed model setup"})
                else:
                    self.respond(200, _models_status(runtime.models))
            elif path == "/health":
                self.respond(200, {"status": "ok", "mode": runtime.life.mode})
            else:
                self.respond(404, {"error": "Not found"})

        def do_POST(self) -> None:
            if not self.local_request():
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Send application/json")
                size = int(self.headers.get("Content-Length", "0"))
                limit = 200_000 if urlsplit(self.path).path in MODEL_PATHS else 12000
                if not 0 < size <= limit:
                    raise ValueError("Invalid request size")
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                path = urlsplit(self.path).path
                operator_path = path in OPERATOR_POST_PATHS or (
                    path.startswith("/api/jobs/") and path.endswith("/cancel")
                )
                if operator_path and not self.operator_request():
                    return
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_store = getattr(runtime.life.gateway, "jobs", None)
                    if job_store is None:
                        raise ValueError("This runtime has no durable cognition queue")
                    job_id = path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
                    from uuid import UUID

                    job_store.cancel(UUID(job_id))
                    self.respond(200, runtime.snapshot())
                    return
                if path in MODEL_PATHS:
                    # Model settings and tests never touch his world, so they run outside it.
                    if runtime.models is None:
                        raise ValueError("This server runs a fixed model setup")
                    self.respond(200, _models_action(runtime, path, body))
                    return
                operation_started = runtime.clock()
                with runtime.mutation():
                    if path == "/api/control":
                        if body.get("running") and runtime.stop.is_set():
                            raise ValueError(
                                "Restart the local server to recover its stopped worker"
                            )
                        runtime.life.configure(
                            body["running"],
                            body["minutes_per_tick"],
                            body.get("clock_mode", "accelerated"),
                        )
                    elif path == "/api/step":
                        runtime.life.advance(body.get("hours", 1))
                    elif path == "/api/catch-up":
                        runtime.life.catch_up(body.get("hours", 24))
                    elif path == "/api/catch-up/resume":
                        runtime.life.resume_catch_up()
                    elif path == "/api/catch-up/cancel":
                        runtime.life.cancel_catch_up()
                    elif path == "/api/chat":
                        text_value = body.get("text")
                        request_id = body.get("request_id")
                        if not isinstance(text_value, str) or not isinstance(request_id, str):
                            raise ValueError("Chat text and request ID must be strings")
                        if runtime.live_reply_in_progress():
                            raise ValueError("Pathos is still speaking")
                        previous_message_ids = {
                            str(item["id"])
                            for item in runtime.life.snapshot().get("conversations", [])
                        }
                        runtime.life.chat(text_value, request_id)
                        runtime.pace_live_reply(previous_message_ids, operation_started)
                    elif path == "/api/outreach":
                        enabled = body.get("enabled")
                        if type(enabled) is not bool:
                            raise ValueError("Outreach enabled must be true or false")
                        runtime.life.configure_outreach(enabled)
                    elif path == "/api/visit":
                        request_id = body.get("request_id")
                        if not isinstance(request_id, str):
                            raise ValueError("Visit request ID must be a string")
                        runtime.life.request_visit(request_id)
                    elif path == "/api/visit/end":
                        request_id = body.get("request_id")
                        if not isinstance(request_id, str):
                            raise ValueError("Visit request ID must be a string")
                        runtime.life.end_visit(request_id)
                    else:
                        self.respond(404, {"error": "Not found"})
                        return
                self.respond(200, runtime.snapshot())
            except (ValueError, KeyError, TypeError, TimeoutError, JobConflict) as error:
                self.respond(400, {"error": str(error)})
            except RevisionConflict:
                self.respond(409, {"error": "The world changed in another process. Try again."})
            except Exception:
                logger.exception("Request failed")
                self.respond(
                    500, {"error": "The operation failed; refresh to inspect the last saved state."}
                )

    return Handler


OPERATOR_GET_PATHS = frozenset(
    {"/api/events", "/api/export", "/api/catch-up/preview", "/api/models"}
)
OPERATOR_POST_PATHS = frozenset(
    {
        "/api/control",
        "/api/step",
        "/api/catch-up",
        "/api/catch-up/resume",
        "/api/catch-up/cancel",
        "/api/models",
        "/api/models/test",
        "/api/models/remote",
    }
)
MODEL_PATHS = frozenset({"/api/models", "/api/models/test", "/api/models/remote"})


def _models_status(models: Any) -> dict[str, Any]:
    from eidos.adapters.providers import GROUP_LABELS, PROVIDERS, ROLE_GROUPS

    return {
        **models.configured.status(),
        "mode": models.mode(),
        "provider_kinds": [
            {
                "kind": kind.kind,
                "label": kind.label,
                "base_url": kind.base_url,
                "needs_key": kind.needs_key,
                "local": kind.local,
                "key_hint": kind.key_hint,
            }
            for kind in PROVIDERS.values()
        ],
        "groups": [
            {"id": group, "label": GROUP_LABELS[group], "roles": list(roles)}
            for group, roles in ROLE_GROUPS.items()
        ],
    }


def _models_action(runtime: Any, path: str, body: dict[str, Any]) -> dict[str, Any]:
    import asyncio
    import os

    from eidos.adapters.model_settings import check_model, list_models

    models = runtime.models
    if path == "/api/models":
        models.configured.save(body.get("settings"))
        runtime.life.mode = models.mode()
        return _models_status(models)
    if path == "/api/models/test":
        model_id = str(body.get("model_id", ""))
        entry = models.configured.entries().get(model_id)
        if entry is None:
            raise ValueError("Save the model first, then test it")
        return asyncio.run(check_model(entry.gateway))
    provider_id = str(body.get("provider_id", ""))
    providers = models.configured.settings().get("providers", {})
    provider = providers.get(provider_id)
    if provider is None:
        raise ValueError("Save the provider first, then list its models")
    try:
        return {"models": list_models(provider, os.environ)}
    except Exception as error:  # a provider's own error, shown to the operator
        return {"models": [], "error": str(error)[:200]}


def event_json(event: DomainEvent) -> dict[str, Any]:
    return {
        "id": str(event.event_id),
        "kind": event.kind,
        "schema_version": event.schema_version,
        "causation_id": str(event.causation_id) if event.causation_id else None,
        "correlation_id": event.correlation_id,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in event.payload.items()
        },
    }


def serve(
    database: Path,
    port: int = 8765,
    gateway: ModelGateway | None = None,
    mode: str = "stand-in",
    town_signal_source: TownSignalSource | None = None,
    news_source: NewsSource | None = None,
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    from eidos.adapters.durable_gateway import DurableModelGateway
    from eidos.adapters.sqlite_jobs import SQLiteJobStore
    from eidos.application.cognition_supervisor import CognitionSupervisor

    store = SQLiteEventStore(database)
    jobs = SQLiteJobStore(database)

    def revision_for(aggregate: str) -> int:
        return len(store.read(aggregate))

    inner = gateway or StandInGateway()
    supervisor = CognitionSupervisor(jobs, inner, revision_for)
    durable = DurableModelGateway(
        inner,
        jobs,
        revision_for,
        supervisor=supervisor,
    )
    life = Life(
        store,
        durable,
        mode=mode,
        town_signal_source=town_signal_source,
        news_source=news_source,
    )
    from eidos.adapters.model_settings import SwitchingGateway

    life.news_follows_real_time = True
    runtime = Runtime(life)
    runtime.models = inner if isinstance(inner, SwitchingGateway) else None
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(runtime))
    runtime.start()
    print(f"Eidos is ready at http://127.0.0.1:{port} — {mode} mode", flush=True)
    print(
        f"Operator view: http://127.0.0.1:{port}/operator?token={runtime.operator_token}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        server.server_close()
