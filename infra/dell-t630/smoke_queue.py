"""Probe real role endpoints through the durable queue in a disposable database."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.routed_gateway import routed_gateway_from_file
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.application.cognition_supervisor import CognitionSupervisor
from eidos.application.model_probe import probe_roles

with tempfile.TemporaryDirectory(prefix="eidos-queue-check-") as directory:
    gateway = routed_gateway_from_file(Path("/etc/eidos/model-routes.json"), os.environ)
    jobs = SQLiteJobStore(Path(directory) / "jobs.sqlite3")
    supervisor = CognitionSupervisor(jobs, gateway, lambda _: 0)
    durable = DurableModelGateway(gateway, jobs, lambda _: 0, supervisor=supervisor)
    try:
        report = asyncio.run(probe_roles(durable))
        report["queue"] = [
            {"role": job.capability, "status": job.status, "error": job.error_code}
            for job in jobs.list_jobs()
        ]
    finally:
        durable.close()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
