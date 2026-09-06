"""Local operator entry point; no models or network access required."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.ports.event_store import RevisionConflict


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
    commands.add_parser("journal", help="Read accepted autobiographical events")
    web = commands.add_parser("serve", help="Open the local observatory and run simulation loops")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        gateway = StandInGateway()
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
        simulation = Life(SQLiteEventStore(args.database), gateway, mode=mode)
        if args.command == "journal":
            print(
                json.dumps(
                    [dict(e.payload) for e in simulation.history() if e.kind == "memory.recorded"],
                    indent=2,
                )
            )
            return
        if args.command == "advance":
            simulation.advance(args.hours)
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
    except (ValueError, RevisionConflict) as error:
        parser.exit(2, f"eidos: {error}\n")


if __name__ == "__main__":
    main()
