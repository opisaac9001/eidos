"""Loopback-only operator server and serialized simulation worker."""

import json
import logging
import mimetypes
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, urlsplit

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.events import DomainEvent
from eidos.ports.event_store import RevisionConflict
from eidos.ports.job_store import JobConflict
from eidos.ports.model_gateway import ModelGateway

STATIC = Path(__file__).parent / "web"
logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, life: Life, interval: float = 3) -> None:
        self.life = life
        self.interval = interval
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.error: str | None = None
        self.ticks = 0
        self.thread: threading.Thread | None = None
        self.cached: dict[str, Any] | None = None
        self.working = False

    def start(self) -> None:
        with self.lock:
            self.life.bootstrap()
            config = self.life.snapshot()["config"]
            # Resume is explicit: downtime never creates an unbounded catch-up burst.
            if config["running"]:
                self.life.configure(False, config["minutes_per_tick"])
            self.cached = self.life.snapshot()
        self.thread = threading.Thread(target=self._loop, name="eidos-chronos", daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while not self.stop.wait(self.interval):
            with self.lock:
                config = {"minutes_per_tick": 15}
                try:
                    config = self.life.snapshot()["config"]
                    if config["running"]:
                        self.working = True
                        self.life.advance(config["minutes_per_tick"] / 60)
                        self.ticks += 1
                        self.error = None
                        self.cached = self.life.snapshot()
                except Exception:
                    logger.exception("Simulation tick failed")
                    self.error = "The simulation paused after a tick failed. Its last committed state is safe."
                    try:
                        self.life.configure(False, config["minutes_per_tick"])
                    except Exception:
                        logger.exception("Could not persist pause")
                    self.stop.set()
                finally:
                    self.working = False

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=30)
        close_gateway = getattr(self.life.gateway, "close", None)
        if callable(close_gateway):
            close_gateway()

    @contextmanager
    def mutation(self) -> Iterator[None]:
        with self.lock:
            self.working = True
            try:
                yield
            finally:
                self.working = False
                self.cached = self.life.snapshot()

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
        return {
            **self.cached,
            "jobs": {
                "counts": job_counts,
                "recent": [
                    {
                        "id": str(job.job_id),
                        "capability": job.capability,
                        "status": job.status,
                        "attempts": job.attempts,
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
            elif path == "/api/export":
                with runtime.lock:
                    events = [event_json(event) for event in runtime.life.history()]
                self.respond(200, {"schema": 2, "events": events})
            elif path in ("/", "/app.js", "/style.css"):
                asset = STATIC / ("index.html" if path == "/" else path[1:])
                self.respond(
                    200, asset.read_bytes(), mimetypes.guess_type(asset)[0] or "text/plain"
                )
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
                if not 0 < size <= 12000:
                    raise ValueError("Invalid request size")
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                path = urlsplit(self.path).path
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_store = getattr(runtime.life.gateway, "jobs", None)
                    if job_store is None:
                        raise ValueError("This runtime has no durable cognition queue")
                    job_id = path.removeprefix("/api/jobs/").removesuffix("/cancel").strip("/")
                    from uuid import UUID

                    job_store.cancel(UUID(job_id))
                    self.respond(200, runtime.snapshot())
                    return
                with runtime.mutation():
                    if self.path == "/api/control":
                        if body.get("running") and runtime.stop.is_set():
                            raise ValueError(
                                "Restart the local server to recover its stopped worker"
                            )
                        runtime.life.configure(body["running"], body["minutes_per_tick"])
                    elif self.path == "/api/step":
                        runtime.life.advance(body.get("hours", 1))
                    elif self.path == "/api/catch-up":
                        runtime.life.catch_up(body.get("hours", 24))
                    elif self.path == "/api/catch-up/resume":
                        runtime.life.resume_catch_up()
                    elif self.path == "/api/chat":
                        text_value = body.get("text")
                        request_id = body.get("request_id")
                        if not isinstance(text_value, str) or not isinstance(request_id, str):
                            raise ValueError("Chat text and request ID must be strings")
                        runtime.life.chat(text_value, request_id)
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
    database: Path, port: int = 8765, gateway: ModelGateway | None = None, mode: str = "stand-in"
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
    life = Life(store, durable, mode=mode)
    runtime = Runtime(life)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(runtime))
    runtime.start()
    print(f"Eidos is ready at http://127.0.0.1:{port} — {mode} mode", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        server.server_close()
