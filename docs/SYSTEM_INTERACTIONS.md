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
| Memory is recalled | `memory.accessed` | Retrieval reinforcement, attention | Actor can access it; one bounded update per meaningful access |
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
4. **Rehearse:** meaningful recall or a real reminder modestly improves access.
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

Chronos orders due work deterministically, breaks ties explicitly and handles
time zones only at presentation/external scheduling boundaries. Recurring entries
create distinct occurrences with IDs. Use simulated deadlines inside Firmament;
wall-clock API timeouts remain operational concerns.

Interruptions have priority, duration, impact and available choices. Replanning
checks travel, actor availability, needs, existing commitments and resources.
Bound the number of replans per scene; record inability to find a feasible plan.

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

NPCs act offscreen through inexpensive schedules/decisions. Important consequences
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
resolver. Broader recurring dialogue and voluntary-exit policies remain future work.

User communication has two distinct paths. An ordinary message is committed as
delivered with a replay-stable response time; sleep, occupied scenes, appointments,
energy and personal variability can defer it. A live visit must first pass the same
availability projection. When accepted, the user and Pathos enter a private
alternating scene for up to 40 turns, either can end it, and a routine departure ends
the visit through a sourced interruption before travel occurs. Calls use this same
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

A ready follow-up can instead prompt Pathos to make an outbound invitation while he is
awake and has emotional and physical capacity. The other person decides independently
from their own energy, connection need, purpose, and replay-stable variability; Pathos's
directed trust is not borrowed as proof of their feelings. A decline remains a durable
social outcome without a calendar entry. Acceptance is passed through the same opening
hours, schedule-conflict, and travel-feasibility planner as other commitments. The shared
appointment then moves Pathos through the ordinary routine override and only completes
if both people are actually co-present.

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

Moira supplies candidate circumstances without choosing from a closed event list.
The initial contract accepts any concise event type and asks for a specific cause,
known place, start delay, duration, theme and opportunity. A strict parser, recent
novelty check and world-event rules decide whether the candidate can become scheduled
fiction. Generated prose never makes the event occur by itself. The deterministic
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

Examples include a neighborhood gathering, workshop delay, weather disruption,
request for help, or opportunity related to an existing goal.
Each needs cause, prerequisites, lead time, affected entities, likely duration,
visibility, stakes, cooldown and novelty/pacing cost. Kernel rules decide whether
it can occur. Actors decide how to respond.

Start with quiet routines plus sparse meaningful disruptions, not constant crises.
Avoid coincidences that repeatedly solve problems or manipulate user attachment.

Catch-up uses an explicit time horizon and budgets. Advance routine low-impact
state cheaply; stop at consequential choices for normal resolution. Preserve
commitment deadlines, sleep, resource accounting and causal order. If the budget
is exhausted, stop at a coherent checkpoint and report the remaining interval.
Cancellation keeps completed batches and prevents later unapproved catch-up work.

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
