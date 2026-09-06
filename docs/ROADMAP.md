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
multidimensional affect and needs, including replayable hunger and meals, source-linked memories,
delayed inbox conversations, and five
UX views. Eight logical AI roles use stand-ins or real HTTP inference; they are not
eight deployed services. A deterministic critic checks contracts. The offline suite
includes unit, replay, seven-day, and thirty-day gates under strict static typing.
Rare non-clinical physical discomfort now forms a replayable one-to-three-day arc:
onset, monotonic recovery and resolution can alter somatic attention, mood, effective
capacity, routine choices, plans, visit availability and queued response timing.
Hourly foreground attention now competes among needs, concerns, goals, people, place
and imminent commitments with bounded inertia. It informs generative context without
gaining action authority. Critical need pressure may redirect one free-time beat per
day through an auditable rule while commitments and the authored opening stay intact.
Domestic continuity now connects meals, deliveries, obligations and daily use to
bounded dishes, laundry, tidying and paperwork loads. High load can compete for
attention and one optional at-home task per day; completion reduces projected state,
while existing worlds receive a clean introduction cutoff rather than retroactive work.
Moira can also submit open-vocabulary fictional incidents with explicit cause, place,
lead time, duration, theme and opportunity; rejected or failed generations produce a
quiet interval instead of falling back to a scripted event.
When one occurs, a source-linked neighborhood thread now persists beyond the opening:
it progresses, may extend once, and resolves to a bounded outcome. Later stages become
memories only for co-present actors, while the operator can see active and resolved
threads in the World view. Pre-existing old events are not retroactively reinterpreted.
Replayable added places now contribute their own opening hours and connected roads to
planning, travel, and promise-retiming feasibility instead of acting as display-only
map markers. Newly introduced people also use their introduced place for generic
need-driven goals, travel there during the day, and can complete validated activity
there rather than being silently folded into the seed cast's routines. Pathos now
turns an introduced place into a source-linked, two-visit exploration goal, fits it
around existing plans and travel, physically goes there, and completes it through
the ordinary action resolver. Introduced useful objects can likewise become optional
two-session projects according to Pathos's current curiosity, mastery, and stable
values. Their sessions require the real shared object at its projected location and
end in completion, refusal, or explicit access failure rather than narrated success.
A genuinely co-present neighbor can independently join or decline one of those sessions.
Only joined use creates shared relationship evidence, memory, and a later follow-up
that can enter the existing invitation lifecycle.
After two validated uses, an introduced shared object now develops explicit wear and
becomes unavailable. Eidos schedules an inspection followed by repair around opening
hours, conflicts, and travel, remains at the site for the work interval, and restores
the object only through the ordinary repair resolver. He can instead retire an object
that does not justify the time and effort. A chosen repair can fail against present
mastery, leaving the condition broken and resolving its schedule, intention, goal, and
setback memory honestly. This creates a reusable causal loop from discovery through
use, social consequence, wear, judgment, and imperfect care.
Retirement or repair failure now opens a separate recovery choice: live without the
object, seek a compatible substitute, or order a replacement. A substitute loan needs
the owner, Eidos, and the object co-present; the owner independently accepts or declines,
Eidos explicitly accepts custody, and return waits for later co-presence. A replacement
has delayed fallible handoffs and registers as a distinct object, preserving the old
object and its history instead of laundering condition through an identity swap.
Borrowed substitutes now create two resource-backed use sessions only when both fit
before the agreed return time. Otherwise Eidos records that the loan was too short to
use honestly. An overdue return changes trust and tension once and remains returnable
when owner, borrower, and object later meet. Received replacements enter the ordinary
curiosity/capability choice and can develop their own use and maintenance history.
Selected delivered supplies now carry an explicit quantity, unit, and low-stock point.
Ordinary co-located use decrements stock; Pathos can instead save it. Low stock creates
an order-or-go-without decision, and ordered stock arrives after a delay with one retry
rather than appearing automatically. Depleted resources fail feasibility. Legacy
materialized object records upgrade with no invented quantities.

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
Need-driven choices now record all three competing levels and their selected priority;
repeated successfully realized voluntary activities also create evidence-backed learned
preferences only after three choices span at least seven days. At most one preference
changes in fourteen days, only five learned preferences may coexist, and 120 days of
behavioral disuse retires one without altering the character-pack identity. Active
preferences are visible and feed subsequent activity and project proposals as soft
influences rather than scripts.
Behavioral openness, sociability, and follow-through are separate slow tendencies:
five matching resolved outcomes across at least thirty days can move one by 0.01,
only once per month and no farther than 0.15 from its character baseline. The active
levels ground conversation and future proposals, but never override feasibility.
Critical exhaustion can interrupt and causally replace a lower-priority private plan
without making ordinary fluctuations rewrite the day. Shared familiarity can make a
connection need more attractive, but Pathos's one-sided trust is never treated as
proof of an NPC's hidden reciprocal feeling. The authored opening uses person-specific,
replay-stable project palettes. After that foundation, each offscreen resident can
submit an open-vocabulary private activity proposal grounded only in their own needs,
public identity, owned perceptions, and known places. Passing plans move the resident
to the planned place and require a matching offscreen action; invalid proposals become
private, rate-limited failures rather than facts. Term,
entity, goal, relationship, and rehearsal recall indexes now persist
as a versioned disposable projection and increment from the event tail. Planning and
actor-owned beliefs and directed relationships now do the same with ordered,
semantically checked disposable snapshots so restarts preserve exact presentation
order. Relationship state also influences whether Pathos interrupts a live visit to
answer someone else's call. Daily consolidation now keeps an incrementally grouped,
prefix-verified source index rather than rescanning the entire life each midnight.

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
- Every Pathos memory now carries a replay-derived emotional encoding from the
  valence, arousal, intensity, and named feeling present when it formed. A dedicated
  source appraisal overrides that background tone for mood-congruent retrieval.
- Explainable cue-based recall using relevance, accessibility, importance,
  relationships and goals; search beyond recent items. Embeddings are optional.
- Fade accessibility/detail in simulated time. Reminders and rehearsal strengthen
  access within bounds; the historical audit record does not decay.
- Current mood now slightly biases recall toward memories with matching source-linked
  emotional appraisals. Hazy recollections reconsolidate at most monthly into a
  persistent subjective version with lower confidence, altered emphasis, and a bounded
  trace of how Pathos felt while remembering. Two similar hazy memories actually
  accessed together can blend, with both source links retained and no change to either
  source. Later thought begins from that version while immutable evidence remains
  separate. A newer direct structured confirmation that contradicts a remembered claim
  can restore clarity and confidence while retaining the source, drift, and correction
  trail; testimony and evidence that predates the drift cannot do so.
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
- Open-ended personal agency proposals grounded in needs, emotions, values, memories,
  relationships, places and possessions. Activity meaning may be novel, while execution
  still uses typed actions and deterministic feasibility. Pathos can also propose a
  two-to-four-step project with atomic schedule/travel/resource admission, incremental
  action-backed progress, and whole-project cleanup on a failed required step. Residents
  independently propose owner-private open-vocabulary plans after the authored opening.
- Persistent objects and validated actions: move, meet, borrow, give, repair,
  learn, rest, work and attend. Narration alone cannot perform an action.
- A replayable household ledger now makes workshop attendance produce bounded income,
  charges café meals and provision orders, refunds failed deliveries, and resolves
  weekly housing costs as paid or explicitly missed. Affordability constrains food
  choices and enters agency context; balances cannot silently become negative.
- Domestic work accumulates from actual living and can occupy optional time at home.
  Each source applies once, completed work lowers the corresponding load, and neither
  narration nor a migration can fabricate a backlog or a finished task.
- Rare physical discomfort is explicitly non-clinical and time-bounded. Its severity
  can defer optional activity or interrupt a plan, but does not bypass emergencies,
  travel, schedule consequences, communication availability or ordinary recovery.
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
- Nightly sleep intentions are now replayable five-to-ten-hour windows shaped by
  reserves, arousal, and nearby commitments. Active conversations and incidents delay
  the transition rather than ending abruptly; older worlds retain a safe fallback.
- Select dreams from salient memories, unresolved concerns and emotional state.
  Record seed IDs, symbolic transformations, recurring motifs and intensity limits.
- Permit mundane dreams, nightmares and no recalled dream. Avoid forced profoundness.
- Waking carries limited, decaying affect and partially recalled fragments. Dream
  inspiration must pass through ordinary planning before it changes behavior.
- Opposed recent appraisals now survive as source-linked mixed emotion rather than
  cancelling into a deceptively neutral label. Complexity modestly slows initiative,
  pace and risk. Rate-limited regulation can lower arousal or protect a sleep intention,
  but never directly turns sadness into happiness; protected rest completes only when
  sleep actually begins.
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
- NPC cognitive detail is now explicit: background residents use deterministic
  needs/plans, route-near residents become local, and co-present attended residents
  become focused. Detail is cheaply derived without per-resident bookkeeping events;
  generated people materialize through a first encounter, and Pathos's
  planning sees only people supported by his own encounters or memories.
- Co-present residents now hold cooldown-paced conversations without requiring Pathos.
  Turns produce audience-owned memories, completed scenes update two separate directed
  relationships and connection needs, and only public speech heard at Pathos's actual
  location enters his memory. Evidence-backed beliefs can now travel through those
  turns as discounted, listener-owned testimony without becoming universal truth.
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
  and callbacks that wait for a free waking interval. Connection goals can instead
  produce a next-day physical visitor whom Pathos may miss, defer, or admit according
  to presence, energy, emotion, and relationship state. Admitted visitors occupy his
  home, block new visits, and pause/resume an active user conversation. Calls, visits,
  apologies, and shared time now create durable follow-ups that prioritize the relevant
  person and topic when they next meet, and close only against later causal contact.
  Ready follow-ups can also become outbound invitations during a waking, socially open
  interval. The invited NPC accepts or declines from their own energy, connection need,
  purpose, and replay-stable variability; acceptance enters Pathos's ordinary feasibility
  planner and calendar, while refusal creates no implied plan. After a call or visitor
  leaves, resumption is no longer automatic: co-presence,
  exhaustion, an imminent commitment, and replay-stable inclination decide whether
  Pathos returns or ends the visit with an explicit reason. A public event he actually
  perceived can now cause a later neighborhood parcel; its two delivery attempts can
  be received, missed, or returned, and an object enters his home only after receipt.
  Door handoffs use the same interruption and recovery rules. Higher-intensity or
  plainly hazardous public incidents Pathos directly perceives now create a bounded
  respond/decline decision. A response holds him at the scene, can displace routine or
  commitments, interrupts a user visit, and leaves factual and emotional aftermath;
  refusal never pretends that he acted. Co-present witnesses now become explicit shared
  aftermath, relationship evidence, and follow-up sources. If an undamaged relevant
  object already exists at that location, the response records its use; narration cannot
  conjure one. Simulation controls and
  private diagnostics now render only on the explicit local `/operator` surface, so
  the ordinary life-facing UI changes the world only through communication.
- Every accepted user/Pathos exchange now consumes a replay-validated five to fifteen
  simulated minutes based on its bounded word count. The conversation view exposes
  elapsed time and the next routine or calendar obligation. Crossing an hourly boundary
  runs the ordinary world loop, so departures and eligible interruptions can genuinely
  occur during a long visit; queued inbox replies wait until Pathos is no longer busy.
- After prior user contact, optional in-app outreach can originate from one Pathos-owned
  non-dream memory. It is off by default, user-revocable, limited to 18:00 and once per
  72 simulated hours, and suppressed while a reply is owed or a live visit is active.
  It never creates an external notification. Generated absence, guilt, or dependency
  pressure is rejected with an audit event rather than delivered.
- A first completed meaningful interaction establishes one private, source-linked date
  per relationship. At 08:00 on its annual recurrence, Pathos records a factual memory;
  an NPC date can enter the ordinary follow-up and invitation path, while a user date
  remains in-app context and cannot bypass outreach consent or create an external alert.
- The Memory Archive now searches and pages through the complete Pathos-owned history
  rather than silently stopping at a recent display window. Cold-archive state and
  current accessibility remain visible, while NPC-private memories stay outside the
  ordinary endpoint and interface.
- Explicit first-person user statements and structured NPC self-reports create private
  remembered likes or avoidances. Later direct statements revise rather than erase the
  record; unsupported knowledge becomes uncertain after 180 simulated days. A held
  place preference can shape an invitation, but gossip and ambiguous language cannot.
- Ordinary NPC conversations now recur from actual non-home co-presence rather than
  one authored date. They use only Pathos-observable topics, advance two turns per
  simulated hour, shift topics, scale their 2/4/6-turn budget with familiarity, end
  when someone leaves, and permit an early NPC exit under sustained tension.
- Tune opt-in outreach cadence from lived use; retain quiet hours, rate limits, an off
  switch, and deterministic rejection of guilt, pressure, or punishment for absence.

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

- Tune saturation, retrieval bias, emotional feedback, remaining trait drift,
  relationship recovery, skills, habits, recurring events, physical episode pacing
  and ongoing projects.
- An apology now opens a source-linked repair attempt whose other-party response stays
  unknown. At most three later direct contacts can gently reduce Pathos's own tension
  and add familiarity without restoring trust or claiming forgiveness; thirty days
  without contact makes the attempt dormant rather than silently resolving it.
- Versioned world packs now import bounded additive releases atomically through the
  ordinary entity-continuity rules; the bundled Canal Quarter release adds a place,
  person and project-capable object. Its second release adds private character-history
  facts with familiarity thresholds. They stay out of model context and Pathos memory
  until the resident speaks one in a validated co-present scene.
- Residents accepted through Moira's open-world expansion now receive a bounded
  three-stage private history generated from public identity alone. Invalid output
  never becomes biography, retries are daily and capped, and the facts remain unknown
  to Pathos until the same witnessed disclosure boundary is crossed.
- Measure queue pressure, model costs, repetition and storage growth. Exercise
  outages, model swaps, backup restore, upgrades and migrations.
- Verified experiment branches now copy an exact life, discard inherited cognition
  work, anchor their shared event prefix and compare later event-kind divergence.
  Their evidence review contrasts social and activity variety, emotion, dreams,
  agency, world activity, model failures and exact narrative repetition without a
  false single quality score. Add governed promotion/rollback decisions only after
  real-model comparison evidence exists.

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
6. Route capabilities by measured results using the strict per-role routing adapter;
   retain stand-ins and honest failure modes.
7. Add embeddings, speech and images only when useful and supported reliably.

## Immediate implementation queue

1. Capture the Dell inventory, then benchmark and pin its private inference stack.
2. Run the reviewed seven-context real-model corpus on the Dell and calibrate per-role
   acceptance thresholds from measured results. Explicit contradiction pairs,
   perspective canaries, role pressure, future-action boundaries, dream/fact separation,
   coverage reporting, and repetition checks are now deterministic.

Completed: the opt-in British-town adapter now records attributed, expiring
Open-Meteo weather/daylight and optional RSS headlines. Moira can cite them only as
non-authoritative inspiration; deterministic validation, replay, failure visibility,
and the observatory preserve the seed-versus-world-fact boundary.

Completed: a bounded monthly retention review now moves cold ordinary memories out of
background recall without deleting evidence. Important or recently accessed memories
stay active, direct cues can resurface archived material, the observatory exposes the
cold shelf, and a deterministic two-year policy soak preserves every source event.

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
