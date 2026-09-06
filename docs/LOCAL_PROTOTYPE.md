# Local prototype: operational notes

## Surfaces

- Observatory: present state, inner monologue, clock, map, and recent events.
- World: four locations, three neighbors, their schedules, and encounter counts.
- Conversation: persisted messages, context-based stand-in replies, retry IDs.
- Memory archive: category and text filters, provenance, complete JSON export.
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
allowed weather vocabulary; it does not evaluate arbitrary prose for truth.

## Persistence and failures

The SQLite event stream is the only durable source of state. Schema version 1
supports the earlier foundation events as well as the new scene events. Request
IDs prevent duplicate chat submissions; an ID cannot be reused for another
message. World writes use optimistic concurrency. An unexpected worker failure
pauses the world and shows an error; restart the server after resolving it.

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

## Next connection

Add an HTTP model adapter after the Dell inventory and inference benchmark.
Before making role calls expensive, introduce bounded durable jobs and caching
so a model timeout does not hold the operator lock. Keep the stand-in adapter
as a fast test backend. No model is granted world-editing authority by the
transport itself.
