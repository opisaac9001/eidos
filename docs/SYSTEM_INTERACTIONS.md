# System interactions and behavioral contracts

Target design, September 5, 2026. Unless called out as current behavior, the
contracts below are planned. See [roadmap](ROADMAP.md) for sequence and
[feature inventory](FEATURES.md) for scope. Names identify responsibilities,
not a requirement to deploy a service or dedicate a model/GPU to each one.

## 1. One world, many perspectives

Keep five different kinds of information distinct:

| Layer | Meaning | Example | May change world truth? |
| --- | --- | --- | --- |
| World history | Accepted events and their actual consequences | Mara handed Pathos a broken lamp | Only validated new events |
| Perception | What a particular actor observed or was told | Pathos heard Mara say it was broken | No; testimony can be wrong |
| Memory/belief | That actor's accessible recollection or interpretation | He believes the switch is faulty | No; revisions keep evidence |
| Imagination/dream | Explicitly fictional subjective content | The lamp illuminated an ocean | Never |
| Operator diagnostics | Jobs, hidden world state, validation and model metadata | A repair proposal failed a precondition | Never automatically visible to actors |

The user is an external visitor by default, not automatically a physically present
world avatar. A chat message may create a communicated experience, not a physical
world action. User knowledge and operator knowledge are not Pathos's knowledge.
Authored initial facts must be marked as seed data rather than fake lived memories.

## 2. Ownership and access

| Component | Owns / is responsible for | Reads | Can propose | Cannot do |
| --- | --- | --- | --- | --- |
| Simulation kernel | Validation, atomic event commits, authoritative projections | Relevant world state and rules | Accepted consequences | Treat prose as an executed action |
| Chronos | Simulation clock, calendar and due-work ordering | Time, accepted schedules, availability | Due jobs, missed deadlines, recurrence | Invent motives or silently catch up indefinitely |
| Firmament | Places, objects, physical/social scene state, observations | World facts and perception rules | Feasible actions, observations, scene outcomes | Give every actor omniscient context |
| NPC performers | Each NPC's voice and choices | Only that NPC's perceptions, beliefs, needs and plans | Speech, actions, invitations, commitments | Read Pathos's private memory or compel his consent |
| Pathos | Central character's voice, attention and decisions | His permitted context, recalled memories, needs, commitments | Speech, action attempts, intentions | Read hidden state or declare his own success |
| Ethos | Identity, memories, beliefs, directed relationships, goals | Accepted actor-relevant evidence | State revisions through rules | Erase history to remove contradictions |
| Mnemosyne | Memory selection/consolidation/association proposals | Actor-owned evidence and recall metadata | Links, summaries, salience or belief-review candidates | Fabricate factual source records |
| Hexus | Needs, appraisal, affect episodes, named emotion, duration and recovery rules | Perceived events, needs, bounded dream effects | Validated affect changes and planning bias | Rewrite identity from one emotional sentence or diagnose a condition |
| Murmur | Low-cost private associations | Limited cues, concerns, affect and recalled memory | Attention candidates, dream seeds | Directly move actors, change beliefs or create obligations |
| Reflection | Deliberate interpretation | Recalled experiences, beliefs, concerns and outcomes | Reframing, links, concern/plan reconsideration | Treat an interpretation as a historical event |
| Oneiros | Dream composition | Selected permitted seed memories, concerns, affect | Labeled dream plus bounded effect candidates | Reveal secrets, complete goals or alter other actors |
| Moira | World-event proposals and pacing | Relevant world state, event budgets and constraints | Plausible candidate events | Force Pathos's choices or leak director knowledge |
| Chronicler | Readable summaries | Source-linked accepted records for the intended audience | Journal/interval summaries | Add events, hide uncertainty or leak private facts |
| Continuity critic | Out-of-fiction validation/evaluation | Proposal plus permitted evidence and rules | Accept/reject/flag with reasons | Speak as Pathos or invent replacement history |
| Logos | Boundary to approved outside tools | Explicit permissions and minimal task context | Authorized real-world action requests/results | Interpret simulated intent as real-world authority |

Ethos is the state owner; Mnemosyne is a bounded performer working on it. Chronos
owns *when* accepted work is due; Pathos owns *why* he wants it; Firmament decides
whether the attempted action can happen. Moira proposes circumstances, not choices.

## 3. Main causal loop

```text
Chronos / user visit / accepted world event
                    |
           actor-specific perception
                    |
       +------------+---------------+
       |            |               |
    memory        Hexus         relationships
       |         appraisal       / concerns
       +------------+---------------+
                    |
       attention + recall + current goals
                    |
             Pathos / NPC decision
                    |
            typed action proposal
                    |
      permissions + feasibility + continuity
                    |
       accepted event and atomic consequences
                    |
              next perceptions

Offshoot: concerns + memories + affect → reflection / Murmur / sleep
                                      → dream → bounded waking effect
                                      → attention (not direct action)
```

Causal links let the operator inspect why a plan changed, which encounter affected
trust, which memories seeded a dream and which waking emotion came from it.

## 4. Common event and proposal contract

Current storage has immutable scalar event payloads and source/trace links.
The richer schema below requires versioned migrations or separate projection
tables; do not silently insert incompatible nested structures into old events.

Planned common fields:

- Stable event/proposal/entity IDs, type and schema version.
- Simulated occurrence time and separately recorded wall-clock time.
- Initiating actor, affected entities, observer/audience information.
- Causation, source-event and correlation/job IDs.
- Expected relevant state revision and explicit preconditions.
- Provenance category: seed, observed, reported, inferred, dreamed or operator.
- Outcome status and structured reason codes; model/prompt/config versions in traces.

Representative contracts:

| Proposed change | Validated output | Main consumers | Required guard |
| --- | --- | --- | --- |
| Actor speaks | `speech.delivered` plus audience observations | Memories, scene participants, relationships | Speaker and recipients present/connected; privacy scope |
| Actor attempts repair | `action.resolved`, object condition update | Goal progress, observers, memory | Possession/access, tools, time, skill and resource rules |
| Promise is mutually accepted | `commitment.created` | Calendar, both actors' memory, concerns | Parties/terms/deadline explicit; no consent by implication |
| Appointment is agreed | `schedule.created` | Chronos, availability, participants | Conflicts, travel, location and recurrence checks |
| A deadline is missed | `commitment.missed` | Appraisal, relationships, replanning | Still active, not fulfilled/cancelled, exactly once |
| Memory is recalled or explicitly prompted by the user | `memory.accessed`, optionally `memory.reminded` and `memory.reconsolidated` | Separately capped reinforcement, attention, mood-congruent selection, selective drift, and source-confused content/person/place attribution | Actor can access every cited source; changed attribution must come from a cited companion memory, reminders never become another occurrence, and immutable evidence stays separate |
| Direct evidence contradicts a drifted claim | `memory.correction_resisted` or `memory.recollection_corrected` | Later recall, operator memory view, feed | Newer `resource.confirmed` evidence matches subject/predicate and differs in value; a highly certain familiarity-based error resists once and needs independent direct corroboration; source history is never rewritten |
| Belief is revised | `belief.revised` | Context, decisions | Owned belief, cited evidence, confidence and prior version |
| Dream completes | `dream.recorded` | Dream journal, sleep processing | Seed lineage, fiction category, intensity/length limits |
| Waking effect is accepted | `affect.changed` / `attention.cued` | Hexus, recall and later decisions | Caps, decay, source dream ID; no direct factual update |
| Moira proposes a neighborhood event | `world_event.scheduled` | Calendar, world, eligible observers | Plausible cause, lead time, budget and actors/resources |

Action, intention and world-event v1 envelopes now implement the corresponding
subset above; other names remain target contracts, not API endpoints. Speech about an
action is different from resolving it. Events form atomic consequence batches:
an object transfer cannot commit without the matching ownership change.

## 5. Memory lifecycle and fading

1. **Encode:** create actor-specific experience from an accepted observation.
   Preserve factual evidence deterministically. The existing source-archive
   recovery remains valid even when the memory performer is unavailable.
2. **Appraise:** attach initial significance from novelty, emotion, relationship
   relevance, goal relevance and consequences. Model suggestions are bounded.
3. **Retrieve:** find eligible candidates using cues/entities, then rank by relevance,
   accessibility, importance and current concerns. Diversify sources; record why.
4. **Rehearse:** meaningful recall or a source-linked explicit reminder modestly
   improves access through separate caps. The reminder reinforces the recollection
   Pathos actually has; it cannot reveal the operator's preserved source version.
   Polling the UI, repeated job retries and self-generated summaries do not count
   as repeated lived evidence.
5. **Fade:** simulated time reduces accessibility and optional remembered detail.
   Start with simple explainable curves; calibrate parameters with fixtures.
6. **Consolidate:** combine repeated episodes into source-linked summaries/themes.
   Keep individual evidence and uncertainty; a theme is not an additional event.
7. **Correct:** conflicting testimony creates a belief review, not a destructive
   overwrite. Preserve whose account changed, why and with what confidence.

Proposed metadata: owner, category, evidence IDs, entities, created/last-accessed
times, access count, significance, accessibility, detail fidelity, confidence,
emotional associations, unresolved-concern links and consolidation version.

Subjective forgetting is not database deletion. An inaccessible memory remains
inspectable to the operator. Privacy deletion is a separate authorized workflow
that must also address indexes, summaries and backup retention. It must never be
blocked by a fictional requirement that "nothing can be forgotten."

On the first simulated day of each month, a deterministic retention review moves at
most 200 cold, ordinary Pathos memories older than 180 days into a subjective archive.
Memories at importance 0.75 or above and memories accessed within 90 days remain in
ordinary working retrieval. Archiving is an event that points to the original memory;
it deletes zero audit events. Archived material no longer enters background context,
but a matching word, entity, goal, or relationship cue can still resurface it. The
observatory exposes both the review and a searchable cold-archive shelf. A two-year
deterministic policy soak checks batching, idempotency, unique archive identities, and
source preservation. Physical event-log retention and privacy deletion remain distinct
operator policies.

Important invariants: high confidence is not guaranteed truth; a dream can be
remembered as an experience without its content becoming fact; embedding
similarity is relevance, not proof; generated associations never manufacture
independent corroboration for the belief that seeded them.

## 6. Plans, scheduled events and interruptions

Distinguish five objects:

- **Goal:** desired outcome and motivation, e.g. become better at repairing things.
- **Intention:** an actor's chosen next action, possibly unscheduled.
- **Commitment:** an obligation to self/another actor with explicit terms.
- **Calendar entry:** reserved time/participants/resources for accepted activity.
- **Historical event:** what actually occurred, including failures and changes.

Suggested state machines:

```text
Goal: proposed → active ↔ blocked → achieved / abandoned
Plan: proposed → feasible → scheduled → active → completed / failed
                                      ↘ interrupted → resumed / replanned / cancelled
Commitment: proposed → accepted → fulfilled / missed / renegotiated / cancelled
World event: candidate → validated → scheduled → triggered → resolved
                         ↘ rejected       ↘ cancelled / deferred
```

Alternative branches require recorded reasons. A completed plan needs action
evidence, not a model saying "done." Renegotiation creates a new agreed version;
it does not erase a previously missed deadline or assume the other party agreed.

Operational experiment branches are separate from Pathos's alternative plans. An
operator may fork the persistent database at a verified event-history anchor to
compare a model, route or prompt. The fork preserves accepted history and derived
projections but discards queued and cached cognition jobs, preventing work authored
for one model configuration from leaking into another. Canonical and experimental
events may then diverge independently. Inspection proves the original shared prefix;
comparison is read-only and offers no automatic merge because two lived histories
cannot be silently reconciled.

Chronos orders due work deterministically, breaks ties explicitly and handles
time zones only at presentation/external scheduling boundaries. Recurring entries
create distinct occurrences with IDs. Use simulated deadlines inside Firmament;
wall-clock API timeouts remain operational concerns.

Interruptions have priority, duration, impact and available choices. Replanning
checks travel, actor availability, needs, existing commitments and resources.
Bound the number of replans per scene; record inability to find a feasible plan.

Pathos's agency performer periodically proposes an ordinary activity using an
open-vocabulary activity type. It may combine current needs, emotional stance, sourced
values, memories, known people, places, usable objects, and calendar openings. It may
not invent a place or possession, spend money, guarantee another actor, or narrate an
outcome. A rules layer checks opening hours, duration, calendar overlap, travel buffers,
custody, condition, stock, and known companions before creating a schedule and owned
intention. Completion later passes through the ordinary action resolver. If a named
companion is elsewhere when the activity is due, the schedule fails and the intention
is abandoned rather than silently fabricating attendance.

Longer self-directed projects use a separate structured proposal containing two to four
chronological steps. The rules layer admits all steps atomically: every interval, route,
place hour, usable object, intention, and fractional progress share must be valid before
the goal exists. Each later action contributes only its configured bounded share. The
last successful step produces project completion. A missed or resource-blocked required
step fails its schedule and intention, cancels unfinished sibling steps, abandons their
intentions and the goal, and records the project failure without erasing completed work.

## 7. Social scenes and independent NPCs

Scene lifecycle: establish location/participants → assemble each actor's own
context → choose social move → bounded exchange → validate consequences → record
observations and actor-specific memories → update relationships/commitments.

Every social move needs intent, audience, optional target object/commitment,
response choices and possible non-success outcomes. An invitation is not attendance;
an apology is not forgiveness; an offered gift is not an accepted transfer.

Relationship state is directed: Pathos can trust Mara more than Mara trusts him.
Separate familiarity, trust, affection and tension rather than one friendship
meter. Change only dimensions supported by the experience; apply inertia and
allow recovery. No automatic large reward for every encounter.

NPCs act offscreen through inexpensive schedules/decisions. The authored opening uses
stable fixtures; afterward a structured resident-agency performer may invent the plan's
activity and action vocabulary from that resident's needs and owner-visible perceptions.
The performer never receives another resident's private context. Known-place hours,
offscreen tick alignment, cooldowns, and owner/visibility rules remain deterministic.
The plan still completes only when its resident moves to the place and records the
matching activity; malformed or outcome-claiming prose becomes a private rejection.
Important consequences
are committed even if Pathos is absent. He learns them later through observation
or testimony, not because the summarizer read the world database.

The world rhythm schedules one low-stakes neighborhood occurrence each week from a
sixteen-event pack spanning repair, reading, nature, art, play, reuse, neighborhood
care, food, and quiet company. Each is announced five
simulated hours before it begins, has a unique occurrence ID, obeys the community-event
cooldown, and becomes knowledge only for actors present at its location.
Calendar-derived season transitions are separate replayable world facts. Weather and
season are therefore durable inputs for later planning, not implications extracted
from narration.
Each recurring event is linked to a persistent community object. Scheduling and
occurrence recheck its condition and location; unavailable resources cause an explicit
skip or cancellation rather than a magical event with missing prerequisites. Theme
and opportunity tags follow the scheduled event into actor-owned perceptions; they
are planning cues, not completed projects. The version-two resource seed adds only
missing objects to an existing version-one world.

The current deterministic baseline lets each resident turn owned public-event
perception into a private, evidence-linked plan suited to their routine. A structured
matching activity must occur on or after its scheduled time to complete it; otherwise
the deadline expires. Plan cooldowns bound repetition. These private plans appear only
in the operator lens and are never inserted into Pathos's context automatically.

Social scenes now have an explicit start, alternating typed turns, mutable topic,
bounded one-to-40-turn budget, voluntary exit, sourced pause/resume, and terminal status.
Private turns create memories only for their audience; public turns also reach
co-present observers. The first two-turn bench exchange is an authored acceptance
fixture whose individual lines are performer proposals. A four-turn workshop exchange
is interrupted by a durable incident and resumes the next day only after both actors
return; topic and awaited speaker survive replay. Invalid or unavailable model output
records a failure and uses a labeled authored fallback without bypassing the scene
resolver. Recurring NPC dialogue uses actual co-presence, relationship-paced budgets,
observable topics, and an early voluntary exit under sustained tension.

User communication has two distinct paths. An ordinary message is committed as
delivered with a replay-stable response time; sleep, occupied scenes, appointments,
energy and personal variability can defer it. A live visit must first pass the same
availability projection. When accepted, the user and Pathos enter a private
alternating scene for up to 40 turns, either can end it, and a routine departure ends
the visit through a sourced interruption before travel occurs. Each accepted pair of
turns advances a replay-validated five, ten, or fifteen simulated minutes from its
actual word count. The UI shows cumulative time and a near-term routine or calendar
obligation. Crossing an hour runs the ordinary life loop, so a long visit can encounter
departures, calls, visitors, deliveries, or incidents without a separate operator step.
The final turn budget creates a visible natural ending. A due inbox message remains
delivered while Pathos is asleep or occupied and is answered only after capacity returns.
Calls use this same
lifecycle rather than appearing only in dialogue. A neighbor's private connection
goal can now cause a source-linked call. If Pathos is with the user, his energy,
social openness and replay-stable variability influence whether he answers or
declines. Answering pauses the visit until the call completes; declining schedules a
callback that waits until he is awake and no longer in an active scene. These events
are auditable and cannot be asserted into existence by the dialogue performer.

The same private connection goal can instead reserve a replay-stable next-day visit.
At arrival time the world checks that Pathos is awake and home, then weighs energy,
social openness, familiarity, trust, tension, and stable personal variability. A
missed or deferred visit remains an explicit consequence. An admitted visitor moves
to the apartment in the projected world, forms a source-linked encounter memory,
blocks other live-visit requests, and can pause the user's conversation at the door.
The visitor departs on a later world tick, changes the relationship through the time
actually shared, and only then resumes a still-paused user scene.

Completed calls, visits, shared activities, ordinary conversations, and apologies can
schedule a source-linked follow-up. When it becomes ready, a co-present encounter with
that person receives priority over an unrelated available acquaintance and the reminder
becomes the initial conversation topic. The reminder is not cleared by time or generated
prose: a later typed contact event for the same person must causally complete it. That
new contact may schedule a future reminder, allowing relationships to recur without a
fixed daily script.

An apology is an offered act, not evidence that the other person accepted it. A Pathos
apology tied to a prior disagreement opens a durable repair attempt with forgiveness
explicitly unknown. Up to three later completed calls, visits, shared activities, or
other directly evidenced contact can reduce Pathos's own tension by a small capped
amount and add a little familiarity. It never restores trust automatically. The
contact event causes the repair step, which in turn causes the directed relationship
change; replay rejects mismatched people, reused contact, and out-of-order evidence.
After thirty simulated days without contact, the attempt becomes dormant with no
relationship delta. A ready apology follow-up can make the unresolved topic available
to ordinary dialogue, still labeled as cautious repair rather than forgiveness.

A ready follow-up can instead prompt Pathos to make an outbound invitation while he is
awake and has emotional and physical capacity. The other person decides independently
from their own energy, connection need, purpose, and replay-stable variability; Pathos's
directed trust is not borrowed as proof of their feelings. A decline remains a durable
social outcome without a calendar entry. Acceptance is passed through the same opening
hours, schedule-conflict, and travel-feasibility planner as other commitments. The shared
appointment then moves Pathos through the ordinary routine override and only completes
if both people are actually co-present.

Completion of an answered call or admitted visit does not automatically reset a user
conversation to its prior state. A separate causal decision records current energy,
whether the user and Pathos are still together, and the next scheduled commitment. An
exhausted or absent Pathos ends the scene; a commitment within an hour creates genuine
time pressure; otherwise a replay-stable inclination can still favor either resuming or
leaving the conversation there. The user receives a visible system explanation in both
cases, and replay retains the exact decision rather than rerolling it.

A delivery is never invented merely because the clock reached a scripted weekday. A
public neighborhood event Pathos personally perceived may, under a stable sparse
selection, cause a follow-up parcel two days later. The first absent handoff schedules
one retry; the second returns the parcel. Answering the door pauses an active user
scene, temporarily blocks another visit request, and completes on a later tick. Only a
completed receipt registers the parcel as a Pathos-owned object at home and creates a
source-linked memory. The handoff then enters the ordinary resume-or-end decision, and
other phone interruptions are paced out of the same hour.

Urgency begins only from a public world event Pathos directly perceived. Intensity and
plain hazard/help language make it eligible; private NPC knowledge and quiet ambient
texture do not. Pathos weighs care, energy, severity, and stable inclination before a
typed respond/decline decision. Responding pauses a live user scene and holds his
physical location for a bounded one-to-two-hour interval, even when that displaces a
routine or appointment. Completion or abandonment creates source-linked memory and an
appraised emotional consequence before the normal resume-or-end choice. Declining also
has an emotional aftermath but cannot claim that Pathos performed the response.
Co-present NPC observers are captured at decision time. A completed shared response
creates per-person aftermath evidence, directed relationship change, and a later
follow-up; leaving it unfinished may instead add tension. Resource use is separately
typed and allowed only for a suitable, undamaged object whose projected location already
matches the response site. The response never creates or teleports a convenient tool.

User outreach is a local communication preference, not a simulated need. It defaults
off and becomes eligible only after the user has initiated contact. When enabled,
Pathos may send one in-app message at 18:00 from a cited non-dream memory, no more than
once per 72 simulated hours. Outreach is suppressed while he owes the user a reply or
a live visit is active, and the fixed 22:00–08:00 quiet window cannot be weakened by
an event. The user can disable it immediately. Nothing invokes an operating-system or
third-party notification. Output that pressures the user through absence, waiting,
loneliness, or dependency is retained as a rejected audit result and never delivered.

Relationship dates are projections of shared evidence, not generated biography. The
first completed social activity, call, visit, shared incident aftermath, or shared
object use with a person establishes one private milestone and preserves that source's
simulated calendar date. At 08:00 on each annual recurrence, including February 28 for
a February 29 origin in a non-leap year, the engine emits one causally linked anniversary
and one factual memory. An NPC anniversary can use the normal follow-up and invitation
machinery, where availability and NPC consent still apply. A date involving the user
is visible only as local context and cannot itself send a message or notification.

Remembered social preferences have a narrower evidence rule than general beliefs. An
explicit first-person user message (for example, a direct like, preference, or
avoidance) can establish a user preference. An NPC preference requires a structured
self-report perceived by Pathos: third-party gossip is insufficient. A later direct
statement about the same normalized topic creates a revision and preserves the earlier
evidence in history. If no direct evidence refreshes a held preference for 180
simulated days, it becomes uncertain rather than being deleted. Only held place
preferences influence the location of an invitation; the ordinary feasibility and
independent NPC-consent checks remain authoritative.

## 8. Dream and reflection feedback loop

Pathos's mind is modeled as concurrent replayable layers rather than one prompt.
Somatic pressure, attention, and association advance every simulated hour. Deliberation,
social awareness, reflection, and dream processing activate under distinct conditions.
A layer pulse selects focus and activation but is neither a memory nor permission to
act; it becomes bounded context for the performers and downstream appraisal systems.
Hourly emotion samples interpret replayed valence, arousal and duration into states
such as joy, contentment, sadness, anxiety or prolonged low mood. Their bounded bias
changes initiative, social openness, risk tolerance and pace; feasibility and consent
still decide what can happen. A prolonged pattern is not a clinical diagnosis.
Opposed positive and negative appraisals from the prior twelve hours may remain as a
source-linked secondary feeling with bounded complexity. This makes initiative, pace,
and risk slightly more cautious without pretending one scalar can cancel the other.

At most once per seventy-two hours, an awake Pathos may select an explicit regulation
response to high arousal, low feeling, or strongly mixed emotion. Grounding, making
space for a feeling, and naming mixed feeling can move arousal only a small step toward
baseline; they never directly improve valence. When low feeling coincides with poor
rest, Pathos can instead choose to protect sleep. That attempt remains pending until a
real `sleep.started` event completes it. Selection cites the exact emotion sample,
practice cites the selection, and completion cites actual sleep, so a narrated coping
claim cannot manufacture recovery.

1. During waking, track perceived experiences, unfinished concerns and affect.
2. Sleep begins when the chosen schedule/needs allow it, not merely because a
   cron hour arrives. Protect sleep-state transitions against duplicate jobs.
3. Select a bounded, diverse seed set from that actor's accessible context.
   Exclude private facts belonging to others and operator diagnostics.
4. Oneiros transforms motifs into labeled subjective fiction; record seeds,
   not purported universal symbolic meanings. Recurrence is allowed but capped.
5. Validate output; failures mean no generated dream for that slot, not corrupted
   sleep or invented replacement history. Rest recovery does not require an LLM.
6. On waking, select full/partial/no recalled dream and bounded emotional residue.
   Store dream recall separately from factual memory. Residue decays over time.
7. Murmur or reflection may associate a fragment with an existing concern.
8. Pathos may reconsider an intention; ordinary planning and action rules still apply.

Emotional effects need source IDs, magnitude caps, decay and a per-cycle budget.
Do not let a dream increase a memory's importance, which causes the same dream,
which further increases importance without fresh evidence. Distinguish creative
association strength from confidence in a factual claim.

Example: a dream of a lamp going dark may leave Pathos uneasy about an unfinished
repair. It does not reveal the lamp's actual fault, prove Mara is disappointed,
change Mara's trust, or supply a repair skill he has not acquired.

## 9. Moira, pacing and catch-up

An optional morning adapter polls current weather/daylight plus a configured local RSS
feed for one British town. Every accepted external report retains a credential-free
HTTPS source, external observation time, poll identity, and expiry. Both
`world_fact=false` and `action_authority=false` are explicit. Failure is visible but
creates no substitute report and changes no fictional state. Active reports enter
Moira's context only as an ID-to-summary inspiration map. A proposal must cite an ID
from that map or `none`; a citation is recorded on the schedule but does not prove that
the corresponding circumstance exists in Eidos's neighborhood. Only the ordinary
scheduled-event and co-present perception lifecycle can make the invented circumstance
a fact or memory.

Moira supplies candidate circumstances without choosing from a closed event list.
The initial contract accepts any concise event type and asks for a specific cause,
known place, start delay, duration, theme, opportunity, concrete participation, stakes,
and one known physical resource. The resource must currently be usable and non-depleted
at that same place. A strict parser, cross-field recent-novelty score and world-event
rules decide whether the candidate can become scheduled fiction. Accepted metadata and
its novelty score are source-linked to the schedule. If the resource later moves,
breaks, or depletes, occurrence is cancelled. Generated prose never makes the event
occur by itself. The deterministic
sixteen-event neighborhood pack remains an offline fixture and minimum texture, not
the production generator's creative boundary.

Future proposal versions can introduce persistent actors, objects and places, but
only by explicit entity-registration effects with collision, provenance and
continuity checks. The first version is now implemented: on a sparse weekly budget,
Moira can propose an open-ended person, useful object, or reachable place. Stable IDs,
duplicate names, known introduction/connection locations, map layout, opening hours,
route duration and display metadata are checked before one registration event becomes
fact. New people enter the same offscreen need/goal/perception projection as the seed
cast. New objects enter ordinary ownership/condition planning. New places and their
routes appear in the world catalog and observatory. This is what lets the world expand
without turning every model sentence into hidden state.

Operator-authored world packs use that same registration boundary. A strict manifest
contains one to thirty-two ordered entity proposals; a place can therefore be added
before people or objects that depend on it. Pack ID, sequential version and canonical
manifest checksum are recorded with individual registration links. Validation occurs
against a projected catalog before one atomic append, so a collision or impossible
route leaves no partial neighborhood behind. An identical release is idempotent, but
an already-imported version cannot be rewritten and version gaps are rejected. Packs
are additive history, never an in-place replacement of people or places.

Schema-v2 packs may seed resident-owned biography with an explicit familiarity
threshold. A seed is private to that resident and never enters Pathos's recall or the
ordinary dialogue model context. When the resident has an eligible turn in a validated
co-present scene, one fact can become the exact utterance. The normal scene resolver
then creates Pathos's direct perception and memory, after which a disclosure event
marks that fact shared. A prompt mentioning a private fact, a narrator summary, or an
operator view never counts as disclosure.

A person accepted through Moira's sparse expansion boundary receives a separate
resident-history proposal. Its prompt contains only that person's public catalog
entry—not Pathos's memories, another resident's private state, or operator data. The
model proposes three first-person past facts; deterministic policy assigns early,
middle, and high familiarity thresholds. Exact shape, length, distinct topics, and
known-person references are checked before any private fact is appended. A failed
proposal creates no fallback biography and may retry only once per simulated day,
with three total attempts. Successful facts then use the identical witnessed
disclosure path as pack-authored facts.

The resident's own agency performer may use those facts as owner-visible context when
proposing a private plan. Biography can therefore influence a choice without making
the choice inevitable: the plan must still satisfy ordinary need, place, schedule,
and action rules. No other resident's biography is included.

Residents can also enter cooldown-paced ordinary scenes with one another when they
are genuinely co-present and neither is already in a scene. Each turn passes through
the shared scene resolver and creates perception and memory only for its audience.
Most of these low-detail exchanges are private; a replay-stable minority are public,
and Pathos remembers one only if his projected location makes him an actual observer.
A completed exchange independently increases each resident's directed familiarity
and satisfies some connection need. Those effects cite the final spoken turn, cannot
be created by narration alone, and remain visible in the private operator lens.

If a speaker holds an evidence-backed belief, one ordinary scene turn may carry it as
explicit testimony. The claim metadata is attached to the spoken turn and copied only
into the perceptions of its real audience and any co-present public observers. Each
listener forms or revises a separately owned belief; default speaker reliability
discounts confidence, so a claim loses strength as it travels. A resident will not
immediately echo testimony back to the person who supplied their latest evidence.
Conflicting later testimony contests the belief rather than rewriting world truth.
Pathos receives none of this from a private offscreen exchange, although the operator
can inspect resident beliefs and their evidence counts.

An introduced object is evaluated once against Pathos's current curiosity and mastery
plus stable curiosity and craft values. Declining records the choice without silently
creating a goal. Pursuit creates two one-hour sessions in open, conflict-free windows
at the object's actual location. Each session goes through the normal intention and
action resolver, which permits a community-held object only for co-located attendance
and rejects missing or unusable resources. Successful use is an explicit sourced event
and memory; two completed sessions achieve the goal. Expired inaccessible sessions and
their intentions fail before the goal is abandoned, preserving a complete causal trail.
Immediately after real use, a neighbor at that same projected location may choose to
join or decline according to their own energy, purpose, connection need, familiarity,
and replay-stable inclination. Absence produces no decision and later proximity cannot
rewrite the earlier moment. Joined use creates a separate sourced fact, directed
relationship evidence, and a shared memory; declined use creates none of those. The
shared fact enters the ordinary follow-up system and can later motivate a mutually
accepted invitation through the existing availability and feasibility rules.

Two validated uses of an introduced object cause one source-linked maintenance need.
The condition changes to broken before new uses are allowed. Current mastery, care,
craft values, replay-stable inclination, and whether two feasible windows exist decide
between retirement and a two-stage inspection/repair goal. Retirement changes condition
without inventing work. A repair goal fits into real opening hours, calendar gaps, and
travel constraints.
The inspection contributes bounded progress but does not alter condition. Repair accepts
a community-held object only while Eidos and the object remain at its site, after the
scheduled work duration has elapsed. Physical uncertainty then compares present mastery
with a stable outcome sample. Success records the repaired condition, remaining goal
progress, completion, skill evidence, and memory. Failure preserves the broken condition
and explicitly fails the schedule, abandons the intention and goal, and records a setback
memory. Ordinary routines cannot move Eidos away halfway through scheduled work. This
rule is additive, so historical objects without a maintenance event preserve their
projected condition.

A retirement decision or failed repair may produce one recovery decision. Compatible
substitutes must share the object's practical kind, remain usable and non-depleted, and
be physically co-present with both Eidos and their NPC owner. Eidos first decides to
seek the loan; the owner then independently accepts or declines from their own capacity.
Acceptance still goes through the normal lend offer and Pathos response, so neither
custody nor consent is implied. The loan records a due time, and return uses the same
transfer resolver only after borrower, owner, and object meet again; until then custody
truthfully remains with Eidos.

Without a viable loan, reliability and stable inclination choose replacement or living
without the object. Replacement ordering does not change the old object. A delayed
handoff succeeds only at the object's place, retries once after absence, and then cancels.
Receipt registers a new object ID with `replacement_for` provenance while the original
condition stays broken or retired. Thus continuity queries can distinguish two physical
objects even when one functionally succeeds the other.

An accepted recovery loan is not treated as useful merely because custody changed. On
the following planning pass, two open, conflict-free, resource-backed sessions must both
end before the recorded return time. If they cannot, a sourced skip marker is recorded
and no goal is implied. If they can, ordinary travel and action validation govern both
uses. A due loan that cannot be returned because the participants are apart creates one
overdue fact, directed trust/tension change, and memory; it does not transfer custody or
repeat punishment hourly. Later co-presence can still complete the normal return.
Replacement registrations are eligible for the ordinary object-opportunity evaluator
and later wear rules, so a replacement has a new independent history rather than serving
as a terminal success flag.

Consumability is explicit object state, never inferred for every object. Qualifying
delivered supplies register a non-negative quantity, reorder point, and unit; legacy
objects retain null stock fields. When awake at the object's location, Pathos makes one
replayable use-or-save decision per day. Use creates a sourced consumption fact before
an ordered stock transition and low-importance ordinary memory. At or below the reorder
point, a separate reliability-weighted order-or-go-without decision occurs. Ordering
creates a next-day handoff rather than stock: presence receives it, absence schedules
one retry, and a second miss cancels it. Every stock event states its prior quantity so
reordered, duplicated, or stale transitions fail projection. Quantity zero makes a
resource unavailable to the action resolver. The observatory displays remaining units.

Examples include a neighborhood gathering, workshop delay, weather disruption,
request for help, or opportunity related to an existing goal.
Each needs cause, prerequisites, lead time, affected entities, likely duration,
visibility, stakes, cooldown and novelty/pacing cost. Kernel rules decide whether
it can occur. Actors decide how to respond.

Start with quiet routines plus sparse meaningful disruptions, not constant crises.
Avoid coincidences that repeatedly solve problems or manipulate user attachment.

An accepted ambient event is not an isolated feed card. Its occurrence can open one
bounded `world_thread` with a source event, place, theme, start, and due time. The
thread progresses after half its duration, then either resolves or—by replay-stable
pacing—extends once for two days before resolving. Every transition cites the prior
stage and replay rejects early, stale, source-changing, or fabricated transitions.
The operator sees these world facts. An actor receives a perception, and Pathos a
memory, only when physically present at the thread's place for that transition.
Pathos appraises the owned direct-perception memory rather than the global occurrence;
an unwitnessed event cannot alter his needs or mood. A co-present resident may instead
form or revise their own private belief from their owned thread perception.
Events from worlds created before this lifecycle are left alone once their opening
hour has passed; upgrading does not manufacture aftermath in the present.

Catch-up uses an explicit time horizon and budgets. Advance routine low-impact
state cheaply; stop at consequential choices for normal resolution. Preserve
commitment deadlines, sleep, resource accounting and causal order. If the budget
is exhausted, stop at a coherent checkpoint and report the remaining interval.
Cancellation keeps completed batches and prevents later unapproved catch-up work.

### Preferences emerge from a life rather than prose

Character-pack values and initial preferences remain stable identity. A learned
preference can arise only from authoritative `agency.activity_realized` events: at
least three distinct self-chosen activities must support the same broad action or
place affinity across seven simulated days. Free-form thoughts, conversations,
reflections, dreams, and model claims are never preference evidence.

An evening review may make at most one change per fourteen simulated days, with no
more than five learned preferences active. The emergence event cites every sampled
source event and replay checks that each source actually supports the exact label.
Active preferences return to later activity and multi-day-project performers as soft
context; feasibility, commitments, needs, emotion, novelty, and consent still decide
what can happen. If no supporting voluntary behavior recurs for 120 days, a sourced
retirement removes only that learned preference. The default character pack is never
silently edited. Both changes remain in the event history and are shown in the feed.

Traits are slower numeric tendencies, not moods or moral scores. Openness,
sociability, and follow-through begin from the character pack. Five matching realized
choices or resolved project/commitment outcomes must span thirty days before one level
can move by 0.01. Only one trait changes per thirty days and each remains within 0.15
of baseline. Replay validates the prior value, direction, result, source category,
source times, cadence, and bound. Failed outcomes may support a small downward
follow-through tendency; they do not erase values, diagnose pathology, or prove what
Pathos will do next.

## 10. Failure, safety and inference boundaries

- Queue jobs only from committed state, or use an atomic outbox. Input snapshots
  carry revisions and permitted evidence IDs. No cross-role shared prompt state.
- Outputs are proposals. Check schema, permissions, feasibility, idempotency,
  actor knowledge and deterministic invariants before committing effects.
- Separate hard rejection from semantic warnings. A model critic's fluent opinion
  is not proof. Quarantine dubious high-impact proposals for review/deferment.
- Bounded retry only for retryable failures; no infinite self-repair dialogues.
  Never claim success because a request returned HTTP 200.
- If inference is unavailable, preserve due commitments and explicit failure state.
  Continue safe deterministic maintenance; do not invent decisions to clear queues.
- Fictional promises never authorize real email, purchases, host changes or network
  tools. Logos requires a separately defined permission and audit boundary.
- Label stand-ins, local models, archives, inferred beliefs and dream content.
  User absence must not be framed as harming a supposedly conscious being.

## Worked example: the lamp

The deterministic integration fixture now exercises an infeasible initial
deadline, a Pathos counteroffer, explicit acceptance by Mara, linked feasible
planning, interruption, rescheduling, validated completion and causal trust.
Separate fixtures prove low-capacity refusal creates no commitment, conflicting
work is rejected, overdue accepted work has consequences, and legacy mid-story
worlds still replay to completion.

1. At the café, Mara asks Pathos to repair a lamp by tomorrow. Only participants
   and actual witnesses receive the exchange as a perception.
2. Pathos checks obligations and may accept, decline or negotiate. If accepted,
   record terms, lamp ownership/access, a commitment and feasible workshop time.
3. Both parties encode their own experience. Pathos's concern links to the promise;
   Mara's expectation is hers, not automatically known to him in detail.
4. A missing component interrupts the repair. Firmament records the actual obstacle;
   Pathos considers alternatives. No repair occurs merely because prose describes it.
5. If he postpones, notify Mara only through a valid communication scene. A missed
   deadline creates a recorded outcome and bounded relationship/appraisal effects.
6. Reflection notices the unfinished concern. Sleep selects it as a possible dream
   seed; a symbolic dark lamp leaves modest unease the next morning.
7. A cue makes the promise easier to recall. Pathos may obtain the component,
   renegotiate, or abandon the goal. Dreaming is not an obligation to choose repair.
8. A validated successful repair changes object condition and fulfills the promise.
   Mara can observe/learn it and respond; trust changes need not be symmetric.
9. Days later, minor dialogue details fade while the meaningful promise/outcome
   remains accessible. A user question retrieves that evidence, not an invented
   heroic account or the dream as literal history.

## Additional integration fixtures

| Scenario | Expected behavior | Forbidden shortcut |
| --- | --- | --- |
| Private secret | Only witnesses/authorized recipients learn it | Omniscient NPC or Pathos retrieval |
| Conflicting testimony | Separate beliefs with sources and uncertainty | Rewrite history to whichever account is newest |
| Old reminder | Relevant old memory resurfaces, access update is bounded | Treat reminder as another occurrence of the event |
| Declined invitation | No attendance reservation; relationship effect depends on context | Automatic consent or punishment |
| Interrupted scene | Persist committed turns, resume or close coherently | Duplicate gifts/promises on retry |
| Dream of betrayal | Dream recall and bounded subjective unease | Record betrayal as fact or change the other actor's state |
| Model outage at deadline | Preserve clock/obligation evidence and explicit unresolved work | Pretend the commitment was fulfilled |
| Week-long absence | Budgeted coherent catch-up with a factual interval summary | Millions of thoughts or fabricated completed projects |

## Observability and acceptance

For each consequential action, inspect cause, actor knowledge, retrieved evidence,
proposal, validation, resulting state changes and downstream jobs. Record concise
decision metadata, not hidden model reasoning. Measure contract failures separately
from semantic defects and distinguish recovered work from successful model output.

Use deterministic fixtures for invariants, adversarial fake responses for failure
paths, real-model samples for quality, and human review for believable continuity.
Test restart at boundaries, repeated/split time advances, duplicate completions,
expired jobs, budget exhaustion, forbidden knowledge, emotional amplification and
source loss. Update acceptance thresholds from measured baselines without hiding
regressions by weakening assertions.
