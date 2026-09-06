"""Local operator entry point; no models or network access required."""

import argparse
import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.ports.event_store import RevisionConflict
from eidos.ports.model_gateway import ModelGateway


def main() -> None:
    parser = argparse.ArgumentParser(description="Eidos persistent simulation")
    parser.add_argument("--database", type=Path, default=Path("data/eidos.sqlite3"))
    parser.add_argument("--base-url", default=os.environ.get("EIDOS_MODEL_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("EIDOS_MODEL_NAME"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Inspect current state")
    commands.add_parser("probe-model", help="Test every performer against the configured model")
    advance = commands.add_parser("advance", help="Advance an authored simulated routine")
    advance.add_argument("--hours", type=float, default=24)
    catch_up = commands.add_parser("catch-up", help="Explicitly catch up at most seven days")
    catch_up.add_argument("--hours", type=float, required=True)
    commands.add_parser("resume-catch-up", help="Resume an interrupted catch-up session")
    commands.add_parser("journal", help="Read accepted autobiographical events")
    backup = commands.add_parser("backup", help="Create a verified online SQLite backup")
    backup.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-backup", help="Verify a SQLite backup without changing it")
    verify.add_argument("--input", type=Path, required=True)
    inventory = commands.add_parser(
        "inventory-server", help="Read hardware and firmware inventory from iDRAC"
    )
    inventory.add_argument("--output", type=Path)
    inventory.add_argument("--ca-file", type=Path)
    web = commands.add_parser("serve", help="Open the local observatory and run simulation loops")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "inventory-server":
            from urllib.parse import urlsplit

            from eidos.adapters.redfish import RedfishClient
            from eidos.application.hardware_inventory import collect_redfish_inventory

            base_url = os.environ.get("EIDOS_IDRAC_URL", "")
            username = os.environ.get("EIDOS_IDRAC_USERNAME", "")
            password = os.environ.get("EIDOS_IDRAC_PASSWORD", "")
            client = RedfishClient(base_url, username, password, ca_file=args.ca_file)
            inventory_report = collect_redfish_inventory(
                client.get_json, urlsplit(base_url).hostname or "unknown"
            )
            encoded = json.dumps(inventory_report, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(encoded)
                print(f"Wrote read-only inventory to {args.output}")
            else:
                print(encoded, end="")
            return
        if args.command in {"backup", "verify-backup"}:
            from eidos.adapters.sqlite_backup import create_backup, verify_backup

            report = (
                create_backup(args.database, args.output)
                if args.command == "backup"
                else verify_backup(args.input)
            )
            print(
                json.dumps(
                    {
                        "path": str(report.path),
                        "integrity": report.integrity,
                        "schema_version": report.schema_version,
                        "events": report.event_count,
                        "jobs": report.job_count,
                    },
                    indent=2,
                )
            )
            return
        gateway: ModelGateway = StandInGateway()
        mode = "stand-in"
        if args.base_url or args.model:
            if not args.base_url or not args.model:
                raise ValueError("Set both --base-url and --model")
            from eidos.adapters.http_gateway import HTTPModelGateway

            gateway = HTTPModelGateway(
                args.base_url, args.model, os.environ.get("EIDOS_MODEL_API_KEY")
            )
            mode = "local-model"
        if args.command == "probe-model":
            if mode == "stand-in":
                raise ValueError("probe-model requires a model endpoint and model name")
            from eidos.application.model_probe import probe_roles

            result = asyncio.run(probe_roles(gateway))
            print(json.dumps(result, indent=2))
            if not result["passed"]:
                raise SystemExit(1)
            return
        if args.command == "serve":
            from eidos.adapters.web_server import serve

            serve(args.database, args.port, gateway=gateway, mode=mode)
            return
        from eidos.adapters.durable_gateway import DurableModelGateway
        from eidos.adapters.sqlite_jobs import SQLiteJobStore
        from eidos.application.cognition_supervisor import CognitionSupervisor

        store = SQLiteEventStore(args.database)
        jobs = SQLiteJobStore(args.database)

        def revision_for(aggregate: str) -> int:
            return len(store.read(aggregate))

        supervisor = CognitionSupervisor(jobs, gateway, revision_for)
        durable = DurableModelGateway(gateway, jobs, revision_for, supervisor=supervisor)
        simulation = Life(store, durable, mode=mode)
        if args.command == "journal":
            print(
                json.dumps(
                    [dict(e.payload) for e in simulation.history() if e.kind == "memory.recorded"],
                    indent=2,
                )
            )
            durable.close()
            return
        if args.command == "advance":
            simulation.advance(args.hours)
        elif args.command == "catch-up":
            preview = simulation.preview_catch_up(args.hours)
            print(json.dumps({"preview": asdict(preview)}, indent=2))
            simulation.catch_up(args.hours)
        elif args.command == "resume-catch-up":
            simulation.resume_catch_up()
        state = simulation.project(simulation.history())
        print(
            json.dumps(
                {
                    "pathos_id": state.pathos_id,
                    "location": state.location_id,
                    "simulated_at": state.simulated_at.isoformat(),
                    "energy": state.energy,
                    "valence": state.valence,
                    "mode": mode,
                },
                indent=2,
            )
        )
        durable.close()
    except (ValueError, RevisionConflict) as error:
        parser.exit(2, f"eidos: {error}\n")


if __name__ == "__main__":
    main()
