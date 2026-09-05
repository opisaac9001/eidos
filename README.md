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
tests/               Executable architecture and domain expectations
```

## Current milestone

Milestone 0 establishes the contracts that future work must preserve. It does
not attempt to recreate the old feature list. See the
[creative direction](docs/CREATIVE_DIRECTION.md), [roadmap](docs/ROADMAP.md),
and [architecture](docs/ARCHITECTURE.md).

## Development

Python 3.12 or newer is recommended.

```bash
python -m unittest discover -s tests
```
