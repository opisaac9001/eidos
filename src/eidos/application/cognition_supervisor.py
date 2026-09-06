"""Supervised background workers for restart-safe cognition jobs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

from eidos.application.job_runner import CognitionJobRunner
from eidos.ports.job_store import JobStore
from eidos.ports.model_gateway import ModelGateway


class CognitionSupervisor:
    def __init__(
        self,
        jobs: JobStore,
        gateway: ModelGateway,
        revision_for: Callable[[str], int],
        *,
        worker_count: int = 2,
        poll_interval: float = 0.02,
    ) -> None:
        if not 1 <= worker_count <= 16:
            raise ValueError("Worker count must be between 1 and 16")
        if not 0.005 <= poll_interval <= 5:
            raise ValueError("Poll interval must be between 0.005 and 5 seconds")
        self.jobs = jobs
        self.gateway = gateway
        self.revision_for = revision_for
        self.worker_count = worker_count
        self.poll_interval = poll_interval
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._started = False
        self.completed_runs = 0
        self.last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self.jobs.expire_deadlines(datetime.now(timezone.utc))
            self.jobs.recover_expired(datetime.now(timezone.utc))
            self._started = True
            for index in range(self.worker_count):
                thread = threading.Thread(
                    target=self._work,
                    args=(f"cognition-{index + 1}",),
                    name=f"eidos-cognition-{index + 1}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def _work(self, worker_id: str) -> None:
        runner = CognitionJobRunner(self.jobs, self.gateway, self.revision_for, worker_id)
        next_recovery = 0.0
        while not self.stop_event.is_set():
            try:
                result = runner.run_once()
                if result is None:
                    if time.monotonic() >= next_recovery:
                        self.jobs.expire_deadlines(datetime.now(timezone.utc))
                        self.jobs.recover_expired(datetime.now(timezone.utc))
                        next_recovery = time.monotonic() + 1
                    self.stop_event.wait(self.poll_interval)
                else:
                    with self._lock:
                        self.completed_runs += 1
                        self.last_error = None
            except Exception as error:
                # One malformed row or transient storage error must not silently kill supervision.
                with self._lock:
                    self.last_error = type(error).__name__
                self.stop_event.wait(min(1.0, self.poll_interval * 10))

    def close(self, timeout: float = 5) -> None:
        self.stop_event.set()
        for thread in self._threads:
            thread.join(timeout=timeout)

    @property
    def alive_workers(self) -> int:
        return sum(thread.is_alive() for thread in self._threads)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "configured_workers": self.worker_count,
                "alive_workers": self.alive_workers,
                "completed_runs": self.completed_runs,
                "last_error": self.last_error,
            }
