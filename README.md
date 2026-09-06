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

The local prototype has six connected views: Observatory, World, Conversation,
Memory Archive, Plans & Time, and Ensemble. A background clock runs routines,
NPC encounters, thoughts, weather, memory formation, reflection, dreams, projects,
scheduled activities, and a factual daybook. All eight
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

Create and verify a consistent backup while the world database is in use:

```bash
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 backup --output backups/eidos.sqlite3
PYTHONPATH=src .venv/bin/python -m eidos verify-backup --input backups/eidos.sqlite3
```

Backup creation refuses to overwrite an existing file. A verified backup can be
opened directly with `--database` to prove that the event history replays before
it is promoted during a recovery.

Downtime is never simulated automatically. To preview and explicitly run a bounded
catch-up (maximum seven days), resume one interrupted between atomic chunks, or
cancel it at its last committed checkpoint:

```bash
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 catch-up --hours 48
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 resume-catch-up
PYTHONPATH=src .venv/bin/python -m eidos --database data/observatory.sqlite3 cancel-catch-up
```

Python 3.12 or newer is required. With mise installed:

```bash
mise trust
mise exec -- python -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/eidos serve
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
PYTHONPATH=src .venv/bin/eidos status
PYTHONPATH=src .venv/bin/eidos advance --hours 24
PYTHONPATH=src .venv/bin/eidos journal
```

Commands default to `data/eidos.sqlite3`. Use `eidos --database PATH ...` to
create independent worlds. Manual advances are bounded to 24 hours. The seed
calendar begins January 1, 2026, UTC. The preview built during development uses
`data/observatory.sqlite3`; run it again with
`PYTHONPATH=src .venv/bin/eidos --database data/observatory.sqlite3 serve`.

## Verify

```bash
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
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
- NPC movement, needs, private activity, public-event perception, private beliefs,
  relationship metrics, and private goals formed from each neighbor's own perceived
  events or changing needs persist by replay. Pathos completes a causal promise/repair
  story and a resource-backed personal
  project; the planner checks
  consent, custody, terms, resources, schedules, open hours, travel buffers,
  abandonment, and renegotiation. General autonomous planning remains future work.
- A typed social-scene lifecycle enforces co-presence, alternating turns, topic state,
  a hard turn budget, voluntary exits, sourced interruptions, and observer-owned
  memories. Integrated two- and four-turn scenes request performer-generated dialogue;
  the longer exchange pauses for a sourced world incident and resumes a day later with
  its topic and turn order intact. Both use explicit audited authored fallbacks when
  generation fails.
- A calm four-week neighborhood rhythm plans seed swaps, repair tables, shared tea,
  and sketch walks with explicit lead time and cooldowns. Only co-present residents
  perceive each occurrence, which gives Mara, Ellis, and Rowan distinct evidence for
  their own private plans during the month soak. Each event requires a persistent
  physical community resource at the right place and is cancelled if it becomes
  unavailable.
- After the authored six-day acceptance story, replay-stable weekday and weekend
  palettes combine dozens of ordinary activities instead of repeating one daily
  script. Emotional initiative and social openness can bend optional outings toward
  restorative solitude or company while leaving obligations intact.
- The simulation calendar records season transitions as replayable world facts and
  exposes the current season beside weather; it does not depend on generated prose.
- Every simulated hour samples a named, persistent emotional state and advances
  somatic awareness, affect, attention, and association. Emotional valence, arousal,
  intensity, and duration bias social capacity and planning style without bypassing
  feasibility or consent. Prolonged low mood is represented as a lived pattern, never
  as an automatic clinical diagnosis. Awake
  conditions also activate deliberative and social layers; evening reflection and
  sleeping dream layers have distinct cadences. These replayable pulses guide model
  context but have no authority to become memories or actions by themselves.
- Memories have provenance, importance, diversified term/entity/goal/relationship
  recall, accessibility/detail fading, capped rehearsal, and source-linked
  consolidation. The recall maps are maintained as a versioned, checksummed,
  event-anchored projection that can be discarded and rebuilt safely. Existing
  databases migrate in place without rewriting events. Vector retrieval remains
  optional and unimplemented.
- The server is loopback-only. Authentication and hardened LAN deployment belong
  to the server installation phase.
- Full-history replay passes restart-spanning seven-day acceptance and thirty-day
  offline soak gates. Event history has stable revision pagination and a checksummed,
  event-anchored core-state checkpoint; longer deployments still need broader
  materialized indexes and archive maintenance. Verified online backups and supervised
  durable model workers are implemented.
- Export history downloads the entire event log, including conversations.

Original code: `git show main:eidos/README.md`. The rebuild does not import the
legacy packages. Both histories are available locally; no push is needed to run.
