# Eidos master roadmap

Updated September 5, 2026. This is a design and delivery plan, not a claim that
the planned behavior exists. Milestones are dependency-driven, not dated promises.

## Destination

A persistent fictional person with a life beyond chat: Pathos perceives a small
world, remembers imperfectly, develops relationships, makes commitments, dreams
about unresolved experiences, and acts on what matters to him. Other characters
have their own limited knowledge and lives. Consequences persist.

These are explicit, tunable simulation mechanics, not claims of consciousness or
scientifically faithful human psychology. The first substantial release is
**one coherent seven-day life**. The longer target is a sustainable month whose days
remain recognizably different rather than a repeated short loop.

- [Feature inventory](FEATURES.md): stable feature IDs, scope, status and phase.
- [System interactions](SYSTEM_INTERACTIONS.md): ownership, event contracts,
  memory/dream/planning lifecycles, and worked scenarios.
- [Creative direction](CREATIVE_DIRECTION.md): intended experience.
- [Architecture](ARCHITECTURE.md): software and deployment boundaries.
- [Local model findings](LOCAL_MODELS.md): measured integration results and limits.

## Current baseline

Implemented: SQLite event history, atomic writes/replay, verified backups, replayable
weekday/weekend daily texture, typed travel, open hours, four places, three persistent neighbors,
multidimensional affect and needs, source-linked memories, delayed inbox conversations, and five
UX views. Eight logical AI roles use stand-ins or real HTTP inference; they are not
eight deployed services. A deterministic critic checks contracts. The offline suite
includes unit, replay, seven-day, and thirty-day gates under strict static typing.
Moira can also submit open-vocabulary fictional incidents with explicit cause, place,
lead time, duration, theme and opportunity; rejected or failed generations produce a
quiet interval instead of falling back to a scripted event.
Replayable added places now contribute their own opening hours and connected roads to
planning, travel, and promise-retiming feasibility instead of acting as display-only
map markers.

Hourly associations, reflection, dreams and a factual daybook run at fixed times.
Named emotional state and duration are sampled hourly. Somatic, affective, attention,
and associative layers pulse every simulated hour; deliberative,
social, reflective, and dream layers activate by waking state, context, and cadence.
The connected week exercises a promise, interruption, repair, personal bookbinding
project, explicitly accepted tool loan/return, scheduled learning, skill growth,
concern, dream residue, temporary non-authoritative inspiration, and directed trust.
Goals support evidence-based progress, abandonment, and mutually accepted versioned
deadline changes. Catch-up has preview, atomic daily chunks, restart, cancellation,
and a bounded source-linked factual recap. Lexical recall includes importance,
simulated-time fading and capped rehearsal. Normal CLI and browser model calls use
supervised durable workers and reuse completed work after restart. Pathos makes a
narrow class of value/capacity-aware social choices; NPCs have persistent offscreen
locations, needs, private beliefs, activities, and perception- or need-driven private
goals with cooldowns, deadlines, causal plans, and activity-validated outcomes.
Their option vocabulary remains bounded rather than generally autonomous. Term,
entity, goal, relationship, and rehearsal recall indexes now persist
as a versioned disposable projection and increment from the event tail. Other
projections, including beliefs and consolidation, still rebuild from event history.

Lab tests exercised all performers. The small model still invents details and
produces invalid proposals. Explicit source archiving preserves accepted scenes
when memory copying fails. Empty encounters, missing scheduled actors, altered
memory copies and unmarked dreams are rejected. This is not semantic validation.

## Delivery sequence

| Phase | Outcome | Dependencies | Exit evidence |
| --- | --- | --- | --- |
| P0 — baseline complete | Persistent prototype day | None | Existing tests, replay, lab probes |
| P1 — reliable cognition | Expensive AI work cannot corrupt or stall life | P0 | Job crash/retry/cancel and stale-result tests |
| P2 — remembering self | Selective recall, fading, beliefs, emotional residue | P1 contracts | Recall/decay fixtures, perspective isolation |
| P3 — intentional social life | Goals, calendar, objects, multi-turn scenes | P1–P2 | A promise can be kept, interrupted or broken |
| P4 — connected inner life | Subconscious, reflection, sleep, dream effects | P2–P3 | Concern → dream → bounded next-day influence |
| P5 — coherent week | Pacing, offscreen activity, catch-up, integrated UX | P1–P4 | Seven-day acceptance story |
| P6 — sustainable month | Long-run stability, richer arcs, tuning, recovery | P5 + measured host capacity | Thirty-day soak and restore report |
| P7 — optional embodiment | Voice, visuals, approved outside tools | Stable P5 core + feature choices | End-to-end tests and permission boundaries |

Host work proceeds alongside these phases. Core mechanics must run with
deterministic performers; the Dell is not a prerequisite for their development.
UX and evaluation ship in every phase rather than being postponed to the end.

## P1 — reliable cognition

Feature families: CORE, OPS, QA, UX-06.

- Versioned typed proposals for speech, action attempts, associations, beliefs,
  intentions and world events. Keep old text-only events replayable; do not
  reinterpret legacy prose as authoritative actions.
- Durable prioritized jobs, deadlines, bounded retries, cancellation, idempotent
  effects, stale-context detection and terminal failures.
- Release world locks during inference; revalidate relevant revisions and action
  preconditions when results return. Preserve atomic consequences.
- Role-specific model/context/token/call budgets, backpressure and explicit
  degraded modes. Prioritize active scenes and conversation over optional thoughts.
- Backups, restore, migrations and bounded projections. Show queue state,
  failures, recoveries, budgets and stale-result rejection in the operator UX.

Exit: kill/restart at job boundaries without duplicate consequences; cancelled
jobs cannot later commit; results for an actor who moved are revalidated; slow
inference leaves state reads responsive; restore a backup successfully.

## P2 — memory, identity and affect

Feature families: MEM, SELF-01–04, UX-02/04, QA-04.

- Separate world facts, perceived experiences, recollections, beliefs, summaries
  and dream memories. Track owner, source, confidence, significance and access.
- Explainable cue-based recall using relevance, accessibility, importance,
  relationships and goals; search beyond recent items. Embeddings are optional.
- Fade accessibility/detail in simulated time. Reminders and rehearsal strengthen
  access within bounds; the historical audit record does not decay.
- Consolidate repeated episodes into source-linked summaries and associations.
  Maintain uncertainty and correction history; summaries are not new events.
- Stable values/preferences/traits plus separately changing needs, emotional
  episodes, named emotional states, duration, baseline mood and recovery. Emotional
  planning bias changes attention and option weighting without removing feasibility,
  consent, or agency. Personality cannot reset with each prompt.
- Show why a memory was selected and distinguish what happened from what is recalled.

Exit: an old relevant promise outranks unrelated recent chatter; ordinary details
fade; a reminder changes recall; restart preserves the result; unwitnessed secrets
cannot be retrieved. Intentional mistaken recall never edits world truth.

## P3 — intentions, interactions and consequences

Feature families: PLAN-01–06, WORLD-01–05, SOCIAL-01–07, SELF-05, UX-03/05.

- Goals, projects, motivations, commitments, deadlines, prerequisites and progress.
- Feasible planning around needs, travel, availability, obligations and resources.
  Support refusal, interruption, postponement, renegotiation, failure and abandonment.
- Persistent objects and validated actions: move, meet, borrow, give, repair,
  learn, rest, work and attend. Narration alone cannot perform an action.
- NPC-private knowledge, needs, plans and directed relationships. Bounded multi-turn
  scenes with intent, response, observation and validated consequences.
- Invitations, favors, promises, cooperation, disagreement, misunderstandings,
  apologies, boundaries, shared activities and follow-ups.
- Trust, familiarity, affection, tension and obligations change from evidence,
  not message counts. Show calendar, projects and causal relationship changes.

Exit: the [lamp scenario](SYSTEM_INTERACTIONS.md#worked-example-the-lamp) supports
success and failure without scripted dialogue. No double booking, teleportation,
magical repairs or automatic acceptance of another actor's invitation.

## P4 — subconscious, reflection, sleep and dreams

Feature families: INNER, SELF-03/04, UX-07, QA-05.

- Structured unresolved concerns and emotional residue feed bounded associations.
  Most remain private; only salient fragments enter conscious attention.
- Reflection proposes interpretations, memory links and plan reconsideration,
  never retroactive fact changes.
- Sleep/wake state replaces the fixed dream hour; track rest and dream budgets.
- Select dreams from salient memories, unresolved concerns and emotional state.
  Record seed IDs, symbolic transformations, recurring motifs and intensity limits.
- Permit mundane dreams, nightmares and no recalled dream. Avoid forced profoundness.
- Waking carries limited, decaying affect and partially recalled fragments. Dream
  inspiration must pass through ordinary planning before it changes behavior.
- Dream journal with recalled content; operator-only seed/effect provenance.

Exit: concern → dream seed → bounded waking effect → later consideration works;
Pathos recalls a dream as a dream. No secret revelation, task completion by
dreaming, factual contamination, or self-amplifying emotional loop.

## P5 — coherent seven-day life

Feature families: WORLD-06/07, PLAN-07, SOCIAL-08, UX, QA-06.

- Moira proposes plausible events with prerequisites, lead time, novelty,
  cooldowns and pacing budgets. Quiet days are valid; forced drama is not.
- Low-detail offscreen NPC activity preserves consequential state and knowledge
  boundaries. Meaningful scenes receive higher-detail simulation.
- Opt-in bounded catch-up with preview, cancellation and interval summaries.
  Important decisions retain full fidelity. Keep today's explicit resume default
  until catch-up behavior is deliberately enabled.
- Integrate daily life, conversation, world, memories, calendar, relationships,
  dreams and diagnostics. Add full-history pagination/search and while-away summaries.
- Ordinary user messages now enter an asynchronous inbox with replay-stable,
  state-derived response timing and visible delivered/answered state. Optional
  co-present visits now require availability and use an alternating, bounded live
  scene that either party can leave; a scheduled departure already ends the visit.
  Connection-goal-sourced phone calls now support answer/decline, visit pause/resume,
  and callbacks that wait for a free waking interval. Extend the same mechanism to
  visitors, deliveries, urgency and remembered follow-up. Simulation controls and
  private diagnostics now render only on the explicit local `/operator` surface, so
  the ordinary life-facing UI changes the world only through communication.
- Opt-in in-app outreach, quiet hours, rate limits and an off switch. No guilt,
  pressure or punishment for user absence.

Seven-day acceptance story:

1. Pathos starts with stable values and a modest personal project.
2. An encounter creates a remembered promise and scheduled action.
3. A plausible interruption forces a choice with relationship consequences.
4. Relevant older memories return; ordinary details become less accessible.
5. An unresolved concern seeds a dream and influences next-day attention.
6. Pathos follows through, renegotiates or fails; the actual outcome is recorded.
7. After restart and a user visit, he explains the week from his own knowledge,
   distinguishes dreams from witnessed events and acknowledges uncertainty.

Acceptance combines automated invariants and human review of coherence/variety.
Beautiful prose with contradictory consequences does not pass.

## P6 — sustainable month

Feature families: MEM-09, SELF-06, WORLD-08, OPS-04/05, QA-07.

- Tune saturation, retrieval bias, emotional feedback, trait drift, relationship
  recovery, skills, habits, recurring events and ongoing projects.
- Versioned world/character packs with validated seeds; controlled content expansion.
- Measure queue pressure, model costs, repetition and storage growth. Exercise
  outages, model swaps, backup restore, upgrades and migrations.
- Add checkpoints/experiment branches for comparing model and prompt versions
  without rewriting the canonical life.

Exit: a report covering thirty simulated days, causal invariant violations,
continuity review, repeated motifs, budgets, storage and restore. Use deterministic
long runs and bounded real-model soaks. Set performance targets from measurements.

## P7 — optional expansion

Feature family: EXT. These candidates do not authorize outside actions.

- Local speech input/output with interruption and accessible transcripts.
- Stable character/place art, illustrated journals and optional dream imagery.
- Richer 2D presentation before considering a costly 3D world.
- User-selected books/documents with source-grounded reading and learning.
- Logos tools with explicit permission, action previews, audit and revocation.
- Additional central characters, world packs, hobbies and creative work.

Defer real money, autonomous third-party messages, uncontrolled host/network
access, self-modifying code, foundation-model training and mass NPC simulation.
Romance/intimacy is not a default assumption; any later design requires explicit
boundaries and must not rely on emotional coercion.

## Host workstream

1. Preserve the small lab's other services; use it for bounded integration tests.
2. Inventory Dell GPUs/CPUs/drives/controller/firmware/network/power/cooling through
   iDRAC. Resolve exact disk-erasure targets before OS installation.
3. Verify current compatibility before selecting OS, driver and inference versions.
   Existing deployment notes are a hypothesis, not a proven stack.
4. Benchmark quality, latency, context, concurrency, memory, thermals and stability
   per role. Do not assume one GPU per role or choose models from RAM totals alone.
5. Deploy reproducible private authenticated inference, storage, monitoring,
   restart supervision and backups. Keep credentials out of Git.
6. Route capabilities by measured results; retain stand-ins and honest failure modes.
7. Add embeddings, speech and images only when useful and supported reliably.

## Immediate implementation queue

1. Extend materialization beyond the completed incremental memory index into the
   remaining high-cost belief, planning, relationship, and consolidation projections.
2. Expand the completed perception- and need-driven NPC goal loop with more personal
   projects, competing priorities, interruption, and relationship-motivated choices.
3. Generalize the now-integrated four-turn interruption/resume scene into recurring
   dialogue policies with topic selection, voluntary exits, and relationship pacing.
4. Let Moira propose additions to the completed sixteen-event, resource-backed
   neighborhood palette, with novelty scoring and schema-valid opportunity metadata.
   The additive catalog now registers rare people, useful objects, and connected
   places without changing seed worlds, and place hours/routes participate in
   feasibility. Next, let goals and consequences deliberately select those additions.
5. Add an optional source-attributed British-town signal adapter for weather, daylight,
   public events, and local-news inspiration, with a strict seed-versus-world-fact boundary.
6. Add explicit long-run memory archive/retention maintenance and longer soak evidence.
7. Capture the Dell inventory, then benchmark and pin its private inference stack.
8. Expand semantic and adversarial evaluations for contradictions, perspective leaks,
   repeated prose, and low-quality but schema-valid model output.

Each item ships with deterministic fixtures, failure-path tests, replay checks,
operator visibility, known limitations and migration notes. Real-model probes
follow deterministic validation. Preserve existing worlds and original `main`.

## Decisions and change control

Working defaults: one central Pathos; a small neighborhood; simulation time
separate from wall time; local-first storage; no external outreach by default;
conservative personality change; subjective forgetting without audit destruction;
bounded inference; no required cloud service. These are reversible design choices.

Tune through experiments: decay curves, emotional dimensions, sleep duration,
NPC independence, event frequency, interaction tone and model profiles.
Seek user input for disk-erasure targets, public exposure, paid services,
external communications, sensitive data ingestion and major premise changes.

New ideas enter the inventory before expanding a milestone. Mark features complete
only with implementation/test evidence and a usable UX, not merely a model prompt.
