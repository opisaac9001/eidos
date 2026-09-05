"""Local operator entry point; no models or network access required."""

import argparse
import json
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.application.simulation import Simulation
from eidos.ports.event_store import RevisionConflict


def main() -> None:
    parser = argparse.ArgumentParser(description="Eidos persistent simulation")
    parser.add_argument("--database", type=Path, default=Path("data/eidos.sqlite3"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Inspect current state")
    advance = commands.add_parser("advance", help="Advance an authored simulated routine")
    advance.add_argument("--hours", type=float, default=24)
    commands.add_parser("journal", help="Read accepted autobiographical events")
    args = parser.parse_args()
    try:
        simulation = Simulation(SQLiteEventStore(args.database))
        if args.command == "journal":
            print(json.dumps([dict(e.payload) for e in simulation.journal()], indent=2))
            return
        state = simulation.advance(args.hours) if args.command == "advance" else simulation.state()
        print(json.dumps({
            "pathos_id": state.pathos_id, "location": state.location_id,
            "simulated_at": state.simulated_at.isoformat(), "energy": state.energy,
            "valence": state.valence, "mode": "authored-routine; no AI connected",
        }, indent=2))
    except (ValueError, RevisionConflict) as error:
        parser.exit(2, f"eidos: {error}\n")


if __name__ == "__main__":
    main()
