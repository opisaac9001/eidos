# Local prototype: operational notes

## Surfaces

- Observatory: present state, inner monologue, clock, map, and recent events.
- World: four locations, three neighbors, directed relationship metrics, one
  causal lamp-repair story, persistent plans and object condition.
- Conversation: persisted messages, context-based stand-in replies, retry IDs.
- Memory archive: category/text filters, provenance, accessibility and JSON export.
- Ensemble: role execution counts, last-run times, errors, and filtered history.

## Daily loop

Clock ticks advance through every crossed hour. Routine beats move Pathos and
change energy. Encounters occur with people sharing the destination, excluding
private homes. Encounters produce source-linked memories and a small positive
affect change. Background associations occur from 07:00 through 22:00. Weather
changes at 06:00, 12:00, and 18:00. Reflection runs at 21:00; dreams and the
daybook run at 23:00. Fractional tick sizes cannot skip or duplicate these beats.

The daybook uses the latest seven recorded experiences, so it is a brief extract
rather than a complete daily archive. The archive itself retains the full log.
NPC movement outside encounters is a projection of the authored schedule, not
independent model reasoning. The continuity critic checks proposal shape and
allowed weather vocabulary, source-memory identity, scene fragments/missing
scheduled actors, and explicit dream labels; it does not evaluate arbitrary prose
for truth. Rejected calls carry stable reason codes and correlated critic traces.
The Ensemble's expandable call inspector shows the latest 100 traces, model,
backend, latency, token count when available, and outcome.

Conversation context now uses explainable cue-based recall with importance,
confidence, simulated-time accessibility decay and capped rehearsal. This is
lexical retrieval, not semantic understanding; the audit history never fades.
The authored lamp fixture exercises a goal, promise, owned intention, schedule,
interruption and reschedule. The repair must then pass deterministic intention,
custody, location, condition and time checks before fulfillment and its causal
trust update. It is not yet general autonomous planning.

The unresolved lamp concern seeds the first night's dream. Waking records it
explicitly as a dream and applies one capped emotional residue. Duplicate
application is prevented. General sleep, appraisal and choice remain pending.

## Persistence and failures

The SQLite event stream is the only durable source of state. Schema version 2
adds event schema, causation, and correlation columns; version 1 databases are
migrated in place without rewriting their event payloads. The stream
supports the earlier foundation events as well as the new scene events. Request
IDs prevent duplicate chat submissions; an ID cannot be reused for another
message. World writes use optimistic concurrency. An unexpected worker failure
pauses the world and shows an error; restart the server after resolving it.

Normal CLI and browser inference runs on supervised background cognition workers.
The durable queue recovers expired leases, retries bounded endpoint failures, and
supports cancellation from the Ensemble inspector. Simulation callers still await
required results; detached optional thoughts and explicit job deadlines remain.

If the memory performer cannot copy an accepted encounter exactly, the engine
archives the source text itself. This is labeled `source-archive`, links to the
encounter event, and emits `memory.recovered`. The model failure is retained;
recovery is never presented as a successful AI call. A rejected encounter has no
such recovery: only already accepted scenes can be archived.

The browser shows the latest 160 feed items, 300 memories, and 100 conversation
messages. Export includes every event. Search applies to the loaded memory
window; full-history search and pagination are follow-up work.

## Validation

Automated tests exercise persistence, rollback, stale writers, restart/split-step
equivalence, all stand-in performers, dream/fact separation, malformed proposals,
chat retries, API input boundaries, the live worker, and pause behavior. Browser
checks exercise navigation, hour stepping, contextual replies, archive search,
and desktop/mobile presentation. A built Python wheel must include all three
browser assets so installation works outside an editable checkout.

The suite has 57 tests and strict static typing passes. A durable queue
and runner cover restart, concurrent claims, ownership, priority, leases, bounded
retry, cancellation, invalid output and stale revisions before/after inference.
wraps normal CLI and browser inference and exposes aggregate queue counts. Work
still executes inline; supervised background workers remain a later step.

## Next connection

The HTTP adapter is implemented and tested against the small lab server; see
[local models](LOCAL_MODELS.md). State reads use a cached committed snapshot
during generation, while writes remain serialized. Durable jobs, cancellation,
and per-role model selection remain follow-ups. Keep the stand-in adapter as a
fast test backend. No model is granted world-editing authority by the transport.
