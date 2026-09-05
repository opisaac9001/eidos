# Eidos

Eidos is a local-first simulation of a persistent digital person named Pathos.
Pathos has a continuing inner life, memory, mood, relationships, a schedule, and
a world that changes even when nobody is chatting with him.

This branch is a ground-up rebuild. The original implementation remains
available on the repository's `main` branch and is treated as design history,
not as a dependency.

## What makes this rebuild different

- The simulation owns truth. Language models may propose thoughts and actions,
  but they cannot mutate state directly.
- Pathos is independent of any model vendor, model name, or serving engine.
- One typed model gateway connects Eidos to local or hosted inference.
- The application begins as a modular monolith. Components split into services
  only when deployment or scaling provides a concrete reason.
- Every meaningful change is recorded as an event so behavior can be inspected,
  replayed, and tested.
- The fictional world and operational reality remain explicitly separated.

## Repository map

```text
docs/               Product vision, architecture, decisions, and roadmap
infra/dell-t630/     Deployment contract for the local AI host
src/eidos/domain/    Deterministic simulation concepts and rules
src/eidos/ports/     Interfaces to models, storage, clocks, and external tools
src/eidos/application/ Simulation use cases
src/eidos/adapters/  SQLite persistence implementation
tests/               Executable architecture and domain expectations
```

## Current milestone

The foundation now runs a persistent, authored day with a clock, locations,
energy changes, and a factual journal. SQLite stores atomic event batches;
the application reconstructs state from the history on restart. AI generation,
NPC dialogue, semantic retrieval, and a web interface are still future work. See the
[creative direction](docs/CREATIVE_DIRECTION.md), [roadmap](docs/ROADMAP.md),
and [architecture](docs/ARCHITECTURE.md).

## Development

Python 3.12 or newer is required. With mise installed:

```bash
mise trust
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/eidos status
.venv/bin/eidos advance --hours 24
.venv/bin/eidos journal
.venv/bin/eidos status
```

Commands default to `data/eidos.sqlite3`. Use `eidos --database PATH ...` to
create independent worlds. Time advances only on request, by up to seven days
per command; closing the program pauses the simulation. The seed world starts
at midnight UTC on January 1, 2026. Journal entries are explicitly authored
routine events, not outputs from a language model.

Original code: `git show main:eidos/README.md`. The rebuild does not import the
legacy packages. Both histories are available locally; no push is needed to run.
