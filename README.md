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
src/eidos/adapters/  SQLite, stand-in performers, HTTP server, and browser assets
tests/               Executable architecture and domain expectations
```

## Current milestone

The local prototype has five connected views: Observatory, World, Conversation,
Memory Archive, and Ensemble. A background clock runs routines, NPC encounters,
thoughts, weather, memory formation, reflection, dreams, and a daybook. All eight
performers can use deterministic stand-ins or a real compatible model endpoint;
a ninth, the continuity critic, performs schema and factual-memory source checks,
not general contradiction detection. Stand-ins remain the offline default.
See [local model testing](docs/LOCAL_MODELS.md) for setup and known limitations.
SQLite stores atomic event batches and rebuilds
state on restart. See the
[creative direction](docs/CREATIVE_DIRECTION.md), [roadmap](docs/ROADMAP.md),
and [architecture](docs/ARCHITECTURE.md).

## Planning the complete experience

The [master roadmap](docs/ROADMAP.md) sets the dependency order and acceptance
milestones. The [feature inventory](docs/FEATURES.md) separates implemented,
partial, planned and optional capabilities. The
[system interaction specification](docs/SYSTEM_INTERACTIONS.md) explains how
memories, emotion, relationships, plans, dreams and world events influence one
another without confusing character beliefs with historical truth.

## Development

Python 3.12 or newer is required. With mise installed:

```bash
mise trust
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/eidos serve
```

Open **http://127.0.0.1:8765**. A new browser world starts at 08:00 on its first
day, paused. Click **Resume world**, choose a speed, or step one hour. One clock
tick occurs every three seconds and advances 5, 15, or 60 simulated minutes.

The browser can close while the server continues running. Stopping the server
stops the clock; starting it again restores history and pauses for explicit
resume. No offline catch-up occurs. Press Ctrl+C in the terminal to stop.

Alternatively, run `./run.command` from the repository. It uses the existing
virtual environment and loads source directly, including on Macs that hide
editable-install path files. It restores `data/observatory.sqlite3` by default;
set `EIDOS_DATABASE` to select another file. Override the port with
`./run.command --port 8766`.

The command line and browser share one application engine:

```bash
.venv/bin/eidos status
.venv/bin/eidos advance --hours 24
.venv/bin/eidos journal
```

Commands default to `data/eidos.sqlite3`. Use `eidos --database PATH ...` to
create independent worlds. Manual advances are bounded to 24 hours. The seed
calendar begins January 1, 2026, UTC. The preview built during development uses
`data/observatory.sqlite3`; run it again with
`.venv/bin/eidos --database data/observatory.sqlite3 serve`.

## Verify

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

No Node runtime is needed to serve the UI. The browser assets ship in the Python
wheel and use no CDN, external fonts, or frontend build pipeline.

## Prototype boundaries

- The application runs locally; real inference has been tested on the small lab
  server. Dell deployment remains pending.
- Offline chat uses templates; model mode uses the configured HTTP endpoint and
  recent memories. The lab model's semantic reliability is limited. Failure,
  source-archive recovery and stand-in states are visible.
- NPC schedules, a first causal promise/repair story and relationship metrics
  persist by replay. The lamp request now negotiates explicit terms before a
  reusable planner creates linked work; its repair passes stale-state, intention,
  custody, location, schedule and elapsed-time checks. Broader autonomous NPC
  planning remains future work.
- Memories have provenance, importance, cue-based recall, accessibility fading
  and capped rehearsal. Entity/semantic retrieval and consolidation are pending.
- The server is loopback-only. Authentication and hardened LAN deployment belong
  to the server installation phase.
- Full-history replay is appropriate for short prototype runs. Longer runs need
  snapshots, pagination and backups. Normal model calls use a durable queue;
  separate background-worker supervision is still pending.
- Export history downloads the entire event log, including conversations.

Original code: `git show main:eidos/README.md`. The rebuild does not import the
legacy packages. Both histories are available locally; no push is needed to run.
