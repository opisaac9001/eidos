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
through a durable gateway decorator with supervised background workers. Optional
Murmur associations submit after the authoritative tick and are revalidated and
reconciled idempotently later. The real-time waking inner stream uses separate
quarter-hour pulse identities and retains only a bounded recent tail for continuity;
other callers still await their requested result. Beneath the pulses, the server runs an
always-on monologue (`application/inner_stream.py`): a background thread that reads the
cached snapshot, calls `murmur` directly (outside the durable queue), and keeps fleeting
thoughts in a rolling `inner_stream` table rather than the event log. Each pulse records
the most salient of them as its `thought.recorded` (`kept_from_stream`).
What his mind drifts to is weighted toward what's unresolved in his life: *current
concerns* (`application/concerns.py`, after Klinger) now open from friends' worries and
losses and from things coming up that he looks forward to or dreads, pull harder as the day
nears or while a worry is fresh, and resolve or recede; *open loops*
(`application/open_loops.py`) are intentions picked out of his own thoughts ("should oil
that hinge") or left by interruptions, recalled by cues (being at the place, seeing the
person, the time arriving), sometimes slipping overnight, and closed when he does or plans
them. Both reach his passing thoughts as cues and his voice as `on_his_mind_lately` and
`meaning_to`; the bookkeeping is code and the models only word it.
Explainable term/entity/goal/relationship recall is implemented; vector retrieval and
outside tools are not.
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
They communicate through an owned, append-only cognitive workspace rather than direct
unbounded model-to-model chat: attention, emotion, recalled experience, and the recent
inner stream become limited inputs to the next eligible faculty. The workspace is a
bounded projection of Pathos-owned events, not a second mutable truth store. Every item
identifies its faculty, source event, age, salience, epistemic status, and lack of action
authority; future, expired, and another actor's private material are excluded. This
preserves the ensemble design while keeping provenance, privacy, pacing, and action
authority clear.

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
Anchored, checksummed, disposable projections now shorten core Pathos-state replay
and persist the memory term/entity/goal/relationship/rehearsal indexes. Both fall back
to full replay if stale, corrupt, or semantically invalid. Schema 4 adds only the
rebuildable projection table and leaves existing event history unchanged. Belief,
planning, relationship, and consolidation projections still rebuild from history;
broader materialization and vectors are not implemented yet. Durable cognition jobs run on
supervised workers with lease recovery and operator cancellation, although required
callers still await their results.
Role traces record status, model/backend, latency, and a trace ID.

## Incremental projections

A tick folds `history + pending` many times per simulated hour, so a projection that
replays from the first event makes each day cost more than the last. Pure folds therefore
go through `domain/folding.py`:

- `IncrementalFold(initial, step)` memoizes a left fold and resumes from the longest cached
  prefix whose events are the **identical objects**, checked by identity. Filtered,
  reordered or speculative lists can never share state by accident; they simply fold from
  the start. Use `key=`/`initial=` when an argument only changes the seed.
- Fold states must be immutable. `GrowOnlyMap` (first write wins) and `PersistentMap`
  (last write wins) give branch-safe, add-only lookups without copying: states share one
  log and each sees only its own prefix. The activity timeline uses the same idea with
  shared append-only lists.
- `SQLiteEventStore` keeps decoded history in process, reads only new rows, and adopts
  committed events, so the same objects flow into the next tick and folds resume there.
- `EventId` caches its text, because nearly every projection keys by `str(event_id)`.

A new projection should be a fold with a `step` over an immutable state, registered as a
module-level `IncrementalFold`. Scanning `history` inside an hourly helper is acceptable
only for small, recent windows (for example `history[-3000:]` walked backwards with an
early exit).

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

## A lived day (2026-10-06)

Several small modules replace meters and timetables with causes, each rule-based in code
with models only wording what the rules decide:

- `application/alertness.py`: a two-process body clock (sleep pressure, sleep debt, the
  day's rhythm) that waking energy follows; bodily sensations with causes, once a day each.
- `application/sleep_schedule.py` `body_clock`: the minute he drops off and wakes (alarm,
  snoozing, lie-ins, waking early when worried); the real-time server stops at those minutes.
- `application/concerns.py` and `application/open_loops.py`: what's weighing on him or coming
  up, and what he means to do, as described above.
- `application/time_feel.py`: how the week and season feel, from his rota, the month and
  his balance.
- `application/happenings.py`: small things that happen because of his situation.
- `application/gossip.py`: news held by residents with source, strength and version,
  spreading between residents who are together and drifting in the retelling; Patrick hears
  it second-hand. Residents recall their recent moments with him.
- `application/group_chat.py`: his close friends' group chat, read when he's free.
- `application/life_lately.py`: a nightly first-person "my life lately" written while he
  sleeps (`pathos_life_summary`, on his inner-life models).
- `application/believability.py`: `GET /api/believability` and `eidos believability`
  measure the last week against human base rates (mind-wandering, thinking ahead,
  intentions slipping, sameness of days, sleep regularity, company, range of feeling).
- Residents keep an ordinary day of their own (`npc_movement.their_place_now`) and go home
  to rest when worn out; the news, friends' news and reflection move by an hour or two a day
  (`application/day_rhythm.py`).
- Plans suggested in the group chat are real invitations (`chat-plan-` ids) he decides on
  through the ordinary invitation flow; a yes is booked with that friend as companion, and
  he answers in the chat once. A friend's private trouble stays out of his posts until
  they've told the group themselves (`group_chat.his_to_share`, `_tells_on`).
- `application/day_recall.py`: "what did you do Monday evening?" hands his voice
  `that_time`, what he remembers of that stretch, in order.
- `application/repair_jobs.py`: the jobs on his bench (taken in, worked hour by hour on
  shift, setbacks and parts on order, finished, collected), feeding feelings, his thoughts
  at work and `on_the_bench` in conversation. No model calls.
- `domain/british.py`: the commonest American slips put right in anything said in the
  town; scene participants reach the model by name (`who_is_who`), not id.
- Meals drift with the day (`nourishment._MEAL_HOURS`): later on a day off, sometimes
  skipped on a rushed work morning, cooked properly or beans on toast, a takeaway now and
  then (`provision_source` "takeaway", charged by the economy).
- A neutral mood takes its name from his strongest feeling (`feelings.mood_from_feelings`).
- Things to take somewhere come back as he sets off from home (`open_loops._carried`).
