"""Local operator entry point; no models or network access required."""

import argparse
import json
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.ports.event_store import RevisionConflict


def main() -> None:
    parser = argparse.ArgumentParser(description="Eidos persistent simulation")
    parser.add_argument("--database", type=Path, default=Path("data/eidos.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Inspect current state")
    advance = commands.add_parser("advance", help="Advance an authored simulated routine")
    advance.add_argument("--hours", type=float, default=24)
    commands.add_parser("journal", help="Read accepted autobiographical events")
    web = commands.add_parser("serve", help="Open the local observatory and run simulation loops")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from eidos.adapters.web_server import serve

            serve(args.database, args.port)
            return
        simulation = Life(SQLiteEventStore(args.database), StandInGateway())
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
                    "mode": "stand-in; no AI connected",
                },
                indent=2,
            )
        )
    except (ValueError, RevisionConflict) as error:
        parser.exit(2, f"eidos: {error}\n")


if __name__ == "__main__":
    main()
