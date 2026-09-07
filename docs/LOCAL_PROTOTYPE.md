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
The ordinary worker commits wall time in small batches, but every user message,
visit, pause, or control change first flushes the exact pending interval so the
interaction cannot be timestamped several minutes in the past. A delayed real-time
tick is split at crossed quarter hours, allowing the waking Murmur stream to retain
its intended cadence instead of producing only one thought at the end of the gap.

The daybook uses the latest seven recorded experiences, so it is a brief extract
rather than a complete daily archive. The archive itself retains the full log.
NPC movement outside encounters is a projection of the authored schedule, not
independent model reasoning. Resident simulation now has explicit cognitive levels
of detail: everyone keeps a cheap deterministic offscreen life, route-near residents
become local, and co-presence plus attention or a scene makes them focused and eligible
for costlier generative planning. Detail is derived without growing the event log; only
the resident's actual actions, needs, plans, and consequences persist. The tiers are
engine state, never Pathos knowledge.

The town also has a cheap anonymous population layer. Public-place footfall varies
deterministically with the hour, weekday, weather, and kind of place, but contains no
names, person IDs, biographies, private needs, or memories. The world view can show
that unrelated people are around; Pathos's model context receives only the aggregate
presence at his current location. When Moira turns one of those possibilities into a
new recurring resident, registration records the population window and immediately
flows into a causal first encounter. A new person can never materialize inside
Pathos's private home.

The catalog is not Pathos's address book. Only direct encounters and Pathos-owned
memories make a person available to his planning and recall. Newly generated residents
are placed at Pathos's current location and registered together with their first causal
encounter, rather than appearing as complete offscreen strangers before he meets them.
The continuity critic checks proposal shape and
allowed weather vocabulary, source-memory identity, scene fragments/missing
scheduled actors, and explicit dream labels; it does not evaluate arbitrary prose
for truth. Rejected calls carry stable reason codes and correlated critic traces.
The Ensemble's expandable call inspector shows the latest 100 traces, model,
backend, latency, token count when available, and outcome.

Conversation context now uses explainable cue-based recall with importance,
confidence, simulated-time accessibility decay and capped rehearsal. Replay-built
term, entity and active-goal indexes contribute separately weighted scores, which
the Memory Archive exposes for explicit conversation recalls. This is not yet
semantic/vector retrieval; the audit history never fades.
The lamp fixture now opens a social request with an infeasible deadline. Pathos's
capacity/window policy counters; Mara explicitly accepts the counteroffer; only
then does the reusable planner create a linked goal, commitment, schedule and
owned intention. The repair later passes deterministic intention, custody,
location, condition and elapsed-work checks. A tested low-capacity branch declines
without creating an implied commitment, and overdue accepted work creates linked
failure, memory and relationship consequences. Other action families remain.

The unresolved lamp concern seeds the first night's dream. Waking records it
explicitly as a dream and applies one capped emotional residue. Duplicate
application is prevented. Each evening now records a replayable sleep window shaped
by rest, energy, arousal, and nearby calendar obligations. An unfinished conversation
or active incident can delay actual sleep without silently changing that intention.

Pathos now has replayed, bounded rest, hunger, connection, curiosity and mastery.
Hunger rises gradually, flexible meal windows wait through occupied time, and an
actual meal leaves validated bodily evidence before it can become a memory. Source-linked
appraisals update the other needs from routines,
encounters, interruptions, completed actions and missed commitments. The work
request policy combines energy, rest and mastery with schedule feasibility.
Non-café meals consume owned household provisions. Low stock uses the established
order, handoff, retry and cancellation lifecycle instead of silently refilling; café
meals identify their external source and cost. The prototype opens an additive GBP
household ledger. Actual weekday
workshop evidence earns income; café meals and accepted provision orders cost money;
failed deliveries refund only an earlier charge; and weekly housing costs are either
paid or explicitly missed without overdrawing the account. Older experiences before
the ledger was introduced are not retroactively charged or paid.
Rare, explicitly non-clinical physical episodes can now emerge from ordinary chance,
with elevated likelihood when rest or nourishment is poor. They last one to three
days, recover monotonically, reduce effective capacity, and can turn optional or
severely constrained planned time into rest. The same condition reaches somatic
attention, emotional appraisal, model context, visit availability, delayed texting,
routine memory and the Observatory. The simulator does not invent a diagnosis or
silently make a temporary symptom permanent.
Foreground attention is no longer a fixed concern-first label. Each hour, bounded
competition among bodily pressure, concerns, active goals, nearby people, place and
imminent commitments selects one focus with modest inertia. The focus informs Murmur
and later open-ended activity/project proposals but cannot perform an action. A
separate feasibility rule lets a genuinely critical unmet need redirect at most one
optional routine hour per day; obligations, appointments, incidents and the opening
story remain protected, and the reason is retained in the resulting memory.
Home now has replayable unfinished work rather than decorative chore prose. Home meals
add dishes; ordinary lived days add laundry and tidying; received deliveries add
clutter; and household obligations add paperwork. Once a load becomes substantial it
can win one optional hour, only at home, and completed work lowers that exact load.
Sources are applied once, pre-feature history is not reinterpreted, domestic pressure
can enter attention and model context, and the Observatory shows the largest current
load without flooding the public feed with every small accumulation.
Pathos's spoken voice now receives a separate affect-derived disposition rather than
being expected to interpret raw emotion fields. Valence, arousal, energy, prolonged
low mood, mixed feeling, and immediate time pressure softly shape openness, warmth,
hesitation, elaboration, and cadence. The prompt keeps his register casual and forbids
announcing those metrics or performing therapy language. Live conversation records
the chosen cadence, so slow or clipped delivery changes actual replay-validated
thinking and speaking seconds; pre-feature turns retain the original steady timing.
Dream residue receives an appraisal but cannot directly change a need, belief,
intention or action. Selected five-to-ten-hour sleep windows recover rest while
waking hours create modest need pressure; pre-window saved worlds retain a safe
circadian fallback. A seven-day calibration keeps these signals away from permanent
floors and ceilings. Richer values remain future work.

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

The current suite has more than 180 tests and strict static typing passes. A durable
queue and runner cover restart, concurrent claims, ownership, priority, leases,
bounded retry, cancellation, invalid output and stale revisions before/after
inference. It wraps normal CLI and browser inference, exposes aggregate queue counts,
and uses supervised background workers; required cognition calls still wait for their
accepted result.

## Next connection

The HTTP adapter is implemented and tested against the small lab server; see
[local models](LOCAL_MODELS.md). State reads use a cached committed snapshot
during generation, while writes remain serialized. Durable jobs, cancellation,
and per-role model selection remain follow-ups. Keep the stand-in adapter as a
fast test backend. No model is granted world-editing authority by the transport.
