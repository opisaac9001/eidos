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
from eidos.ports.town_signals import TownSignalSource


def _town_source_from_env() -> TownSignalSource | None:
    values = {
        "town": os.environ.get("EIDOS_TOWN_NAME"),
        "latitude": os.environ.get("EIDOS_TOWN_LATITUDE"),
        "longitude": os.environ.get("EIDOS_TOWN_LONGITUDE"),
    }
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise ValueError(
            "Set EIDOS_TOWN_NAME, EIDOS_TOWN_LATITUDE, and EIDOS_TOWN_LONGITUDE together"
        )
    from eidos.adapters.british_town_signals import BritishTownSignalAdapter

    return BritishTownSignalAdapter(
        str(values["town"]),
        float(str(values["latitude"])),
        float(str(values["longitude"])),
        news_feed_url=os.environ.get("EIDOS_TOWN_NEWS_RSS_URL"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Eidos persistent simulation")
    parser.add_argument("--database", type=Path, default=Path("data/eidos.sqlite3"))
    parser.add_argument("--base-url", default=os.environ.get("EIDOS_MODEL_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("EIDOS_MODEL_NAME"))
    parser.add_argument(
        "--routes-file",
        type=Path,
        default=Path(value) if (value := os.environ.get("EIDOS_MODEL_ROUTES_FILE")) else None,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Inspect current state")
    commands.add_parser("probe-model", help="Test every performer against the configured model")
    benchmark = commands.add_parser(
        "benchmark-model", help="Run a repeatable synthetic quality corpus"
    )
    benchmark.add_argument("--runs", type=int, default=3)
    advance = commands.add_parser("advance", help="Advance an authored simulated routine")
    advance.add_argument("--hours", type=float, default=24)
    catch_up = commands.add_parser("catch-up", help="Explicitly catch up at most seven days")
    catch_up.add_argument("--hours", type=float, required=True)
    commands.add_parser("resume-catch-up", help="Resume an interrupted catch-up session")
    commands.add_parser("cancel-catch-up", help="Cancel an interrupted catch-up session")
    commands.add_parser("journal", help="Read accepted autobiographical events")
    backup = commands.add_parser("backup", help="Create a verified online SQLite backup")
    backup.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-backup", help="Verify a SQLite backup without changing it")
    verify.add_argument("--input", type=Path, required=True)
    experiment_create = commands.add_parser(
        "experiment-create", help="Fork a verified, independent life experiment"
    )
    experiment_create.add_argument("--output", type=Path, required=True)
    experiment_create.add_argument("--name", required=True)
    experiment_create.add_argument("--purpose", required=True)
    experiment_create.add_argument("--profile")
    experiment_inspect = commands.add_parser(
        "experiment-inspect", help="Verify an experiment and its fork anchor"
    )
    experiment_inspect.add_argument("--input", type=Path, required=True)
    experiment_compare = commands.add_parser(
        "experiment-compare", help="Compare an experiment with its canonical life"
    )
    experiment_compare.add_argument("--input", type=Path, required=True)
    world_pack = commands.add_parser(
        "world-pack-import", help="Atomically add a validated world content release"
    )
    world_pack.add_argument("--input", type=Path, required=True)
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
        if args.command in {
            "experiment-create",
            "experiment-inspect",
            "experiment-compare",
        }:
            from eidos.adapters.sqlite_experiments import (
                ExperimentComparison,
                ExperimentReport,
                compare_experiment,
                create_experiment,
                inspect_experiment,
            )

            experiment_result: ExperimentReport | ExperimentComparison
            if args.command == "experiment-create":
                experiment_result = create_experiment(
                    args.database,
                    args.output,
                    name=args.name,
                    purpose=args.purpose,
                    model_profile=args.profile,
                )
            elif args.command == "experiment-inspect":
                experiment_result = inspect_experiment(args.input)
            else:
                experiment_result = compare_experiment(args.database, args.input)
            print(json.dumps(asdict(experiment_result), indent=2, default=str))
            return
        if args.command == "world-pack-import":
            from eidos.application.world_packs import import_world_pack

            pack_store = SQLiteEventStore(args.database)
            pack_history = pack_store.read("pathos")
            pack_result = import_world_pack(
                pack_store,
                args.input,
                simulated_at=Life.project(pack_history).simulated_at,
            )
            print(json.dumps(asdict(pack_result), indent=2, default=str))
            return
        gateway: ModelGateway = StandInGateway()
        mode = "stand-in"
        if args.routes_file is not None:
            if args.base_url or args.model:
                raise ValueError("Choose either a routes file or one base URL/model pair")
            from eidos.adapters.routed_gateway import routed_gateway_from_file

            gateway = routed_gateway_from_file(args.routes_file, os.environ)
            mode = "routed-local-models"
        elif args.base_url or args.model:
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
        if args.command == "benchmark-model":
            if mode == "stand-in":
                raise ValueError("benchmark-model requires a model endpoint and model name")
            from eidos.application.model_benchmark import benchmark_model

            result = asyncio.run(benchmark_model(gateway, args.runs))
            print(json.dumps(result, indent=2))
            if float(str(result["contract_pass_rate"])) < 1:
                raise SystemExit(1)
            return
        town_signal_source = _town_source_from_env()
        if args.command == "serve":
            from eidos.adapters.web_server import serve

            serve(
                args.database,
                args.port,
                gateway=gateway,
                mode=mode,
                town_signal_source=town_signal_source,
            )
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
        simulation = Life(store, durable, mode=mode, town_signal_source=town_signal_source)
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
        elif args.command == "cancel-catch-up":
            simulation.cancel_catch_up()
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
