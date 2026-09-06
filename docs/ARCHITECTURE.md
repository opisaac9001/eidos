# Architecture

## Implemented local prototype

`cli.py` wires SQLite and stand-in or HTTP model adapters into `application/life.py`.
Both CLI advances and HTTP actions use that single scene engine. The HTTP
adapter serves bundled static HTML/CSS/JavaScript on loopback. A serialized
worker advances simulated time every three seconds while running. Client
polling reads state every 1.5 seconds; it never drives simulation time.

Each scene builds a batch of events, including role traces and accepted prose.
The batch commits with a stream revision check. A failed model proposal records
an error; unexpected scene failures do not commit partial state. Chat retries
use request IDs. The application restores state on startup and requires explicit
resume. Event payloads are immutable scalar values with a versioned datetime
codec that also reads the original time-event format.

Real HTTP inference and a recent-call inspector are implemented. State reads use
a cached committed snapshot while inference holds the serialized mutation lock.
Source archiving recovers accepted encounters when memory-model copying fails.
The critic has conservative contract checks, not general semantic understanding.

The durable SQLite job store and isolated runner are implemented and tested for
priority, concurrent claims, leases, bounded retry, cancellation and stale
results before/after inference. Normal CLI and browser model paths use the queue
through a durable gateway decorator; background supervision remains pending.
Explainable lexical recall is implemented; vector retrieval and tools are not.
The [master roadmap](ROADMAP.md), [feature inventory](FEATURES.md) and
[system interactions](SYSTEM_INTERACTIONS.md) define the delivery sequence and
behavioral contracts. Their richer event fields require explicit schema evolution.

## Two systems, one product

Eidos is split by a hard network boundary:

```text
User interfaces
      |
Eidos application
  - API and UI
  - deterministic simulation kernel
  - cognition scheduler
  - memory and event store
  - tool policy
      |
Typed, OpenAI-compatible model gateway
      |
Dell T630 AI host
  - inference router
  - llama.cpp model servers
  - embedding and reranking workers
  - speech and image workers when supported
  - model storage, metrics, and health checks
```

The Eidos application never imports a serving engine's SDK. It asks for a
capability such as `pathos-dialogue`, `npc-dialogue`, `reflection`, or
`embedding`. Deployment configuration maps that capability to a concrete model.

## Start as a modular monolith

The simulation, API, scheduler, and persistence layer initially ship as one
Python application and one SQLite database for the local foundation. PostgreSQL
remains an option for multiple application processes; the event-store port isolates
that decision. Background work will use a durable
job table before introducing a message broker. This keeps transactions and
debugging straightforward while the domain is still changing.

The Dell inference processes are separate because GPU allocation, restarts, and
model lifecycles have different operational needs.

## Dependency direction

```text
adapters -> application -> domain
    |             |
    +----------> ports <---------- inference/storage implementations
```

- `domain` contains deterministic rules and has no database, HTTP, or model
  dependencies.
- `application` coordinates use cases and transactions.
- `ports` define external capabilities needed by the application.
- `adapters` implement HTTP, databases, inference clients, and tools.

## State and event flow

1. Chronos requests that simulated time advance.
2. The domain produces one or more proposed events.
3. Rules validate events against current authoritative state.
4. Accepted events are appended atomically to the event log.
5. Projections update the current world, memory indexes, and UI views.
6. Events may enqueue cognition jobs.
7. A model response returns a proposal, never a state mutation.
8. The proposal is validated and becomes events or is rejected with a reason.

This makes model behavior auditable and lets tests replay the same history
without running an LLM.

## Initial bounded contexts

### Identity and memory (Ethos)

Owns autobiographical memories, semantic beliefs, relationships, traits, goals,
and provenance. Vector search finds candidates; explicit rules determine what
becomes authoritative memory.

### World (Firmament)

Owns locations, actors, objects, environment, visibility, and physical/social
consequences. NPC improvisation cannot contradict established world state.

### Time (Chronos)

Owns simulation time, calendars, timers, recurrence, pause/catch-up policy, and
the ordering of scheduled work.

### Affect (Hexus)

Owns slowly changing emotional dimensions and short-lived responses. LLM prose
may describe emotion but does not set numeric state directly.

### Cognition

Builds bounded context, invokes a named model capability, parses structured
proposals, and records traces. Conscious dialogue, reflection, subconscious
association, NPC improvisation, and dreams are distinct job types.

### Tools (Logos)

Owns authorization, validation, execution, and observation of effects outside
the simulated world. Model output alone never grants permission.

## Persistence

SQLite currently stores versioned event batches with optimistic concurrency.
State and the journal are rebuilt from those events. The planned schema will combine:

- an append-only domain event table;
- relational projections for current state;
- durable scheduled jobs;
- memory records with provenance and salience;
- vector columns when semantic retrieval is introduced;
- inference traces containing metadata, not hidden chain-of-thought.

The current port requires atomic appends and revision conflicts, independent of
database engine. A PostgreSQL adapter must satisfy the same persistence tests.
Materialized projections and vectors are not implemented yet. Replay currently
builds in-memory term, entity, and goal memory indexes with weighted recall
explanations. Durable cognition jobs run on supervised workers with lease recovery
and operator cancellation, although required callers still await their results.
Role traces record status, model/backend, latency, and a trace ID.

## Model contract

Every request includes:

- capability and task version;
- structured messages or input;
- an output schema when a proposal is expected;
- sampling and token budgets;
- correlation and idempotency identifiers;
- privacy classification and timeout.

Every response records the resolved model, serving backend, latency, token
usage, finish reason, and parse outcome.

No character or simulation state is stored only in a model's context window.
