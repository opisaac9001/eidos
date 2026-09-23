# Feature inventory

Companion to the [roadmap](ROADMAP.md). Stable IDs are planning handles, not
existing classes/services. Built = tested prototype; Partial = narrow version;
Planned = missing; Optional = deferred. Phases indicate next substantial delivery.

## Simulation and cognition

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| CORE-01 | Atomic event history, replay, revisions, pause/resume | Built: ordinary runtime follows real elapsed time at 1×, commits exact pending wall time before user mutations, and reserves acceleration/catch-up for explicit operator tools | P0 |
| CORE-02 | Typed proposals, causation/entity IDs, schema migration, preconditions | Partial: action/intention/world-event/social/speech/belief/association/travel/relating + trace migration | P1 |
| CORE-03 | Durable jobs, priority, cancel/retry, stale results, idempotent effects | Partial: supervised workers + restart-safe text/structured proposals and profiles + detached/revalidated Murmur results | P1 |
| CORE-04 | Actor visibility and capability-limited context | Partial: role filtering, speech-audience perceptions, encounter-sourced acquaintance, known-only social initiation, and private-scene appraisal isolation | P1–P2 |
| CORE-05 | Attention/generation budgets and optional work shedding | Partial: request limits + nonblocking Murmur/capacity shedding | P1 |

## Memory and belief — Ethos / Mnemosyne

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| MEM-01 | Owned experiences, source links, confidence, importance, emotional tags | Partial: owner/source/confidence/importance plus replay-derived valence, arousal, intensity, and named feeling at encoding for every Pathos memory | P2 |
| MEM-02 | Working context, episodic/semantic/recent/dream memory distinctions | Partial: cue-selected episodic context plus source-linked fallible semantic expectations formed across at least three remembered days | P2 |
| MEM-03 | Cue/entity/goal retrieval, diversity, score explanations, optional embeddings | Partial: durable term/entity/goal/relationship indexes + diverse explanations | P2 |
| MEM-04 | Accessibility/detail fading, rehearsal, reminders, bounded reinforcement | Partial: time decay, capped rehearsal, and source-linked explicit user reminders with separately bounded reinforcement | P2 |
| MEM-05 | Consolidation, recurring themes, source-linked summaries | Partial: owner-separated daily themes plus revisable person/place expectations, both with complete source membership; daily grouping is prefix-verified and incremental | P2 |
| MEM-06 | Associations, resurfacing cues, unfinished-concern links | Partial: typed source-linked associations with bounded attention | P2 |
| MEM-07 | Owned beliefs, uncertainty, testimony reliability, correction history | Partial: Pathos and residents form actor-owned discounted testimony, direct confirmation can strengthen or contest it, and revision ledgers/materialization remain checked | P2 |
| MEM-08 | Intentional imperfect recall distinct from world truth | Implemented: accessibility-driven omission, mood-congruent retrieval, mood-colored reconsolidation, source-linked content/person/place/time confusion, repetition-driven false certainty, first-contradiction resistance, and independently corroborated direct correction without changing source history | P2 |
| MEM-09 | Long-run retention/index maintenance and archive policy | Partial: incremental event-anchored index plus monthly bounded cold archive with direct-cue resurfacing; physical compaction remains separate | P6 |

Accepted encounter evidence already has explicit deterministic archive recovery.
Actual user-requested data deletion is a privacy workflow, not simulated fading.

## Self, affect and needs — Pathos / Hexus / Ethos

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| SELF-01 | Stable identity, values, preferences, sourced backstory, knowledge limits | Partial: persisted sourced values, evidence-developed preferences, and a cautious revisable follow-through self-concept derived from Pathos's own outcomes | P2 |
| SELF-02 | Multidimensional affect, named emotion, duration, appraisal, episodes and baseline mood | Partial: replayable primary/secondary mixed emotion, prolonged-low tracking, loss-sensitive source-linked valence/arousal episodes, positive adaptation and recovery, plus bounded effects on conversational openness, warmth, hesitation, length, and cadence; prospective plans can create one small source-linked anticipatory episode—pleasant, pressured, or mixed from companionship, purpose, obligation, energy, rest, and arousal—without claiming the plan occurred, and later cancellation produces bounded disappointment or relief only when that specific plan was previously anticipated; the month gate requires ordinary positive, low, and frustrated states rather than permanent contentment | P2 |
| SELF-03 | Rest, hunger, connection, curiosity, mastery; bounded satisfaction/frustration | Partial: durable need pressure with condition- and commitment-shaped sleep, opportunity- and interruption-aware meals, and critical-need redirection of free time; a full night now restores a full day's rest, he wakes at the hour he chose, and he heads home before bedtime, at closing time or after idle lingering so he sleeps at home | P2–P4 |
| SELF-04 | Emotional residue, recovery, regulation, capped dream carryover | Partial: sleep cycle, capped non-action dream appraisal, source-lineage-based reflective emotional echoes, and source-linked regulation that can lower arousal or protect actual sleep without erasing low valence; reflection prose is never treated as sentiment evidence and dream fiction cannot manufacture a factual cause | P2–P4 |
| SELF-05 | Decisions balance values, needs, emotion, commitments and feasible options | Partial: sourced values + primary/mixed emotional planning bias + open-vocabulary activity proposals checked against energy/rest/mastery/windows and recent repetition pressure; critical needs can redirect one optional hour per day | P3 |
| SELF-06 | Slow trait/preference change, habits, skills, evidence/drift limits | Partial: open-vocabulary source-linked skills with diminishing practice gains, bounded rust and relearning; contextual activity/place/time rhythms with lapse, reactivation and evidence-backed competition; capped week-spanning preference lifecycle; and one-point month-spanning behavioral trait drift | P6 |
| SELF-07 | Household income, costs, affordability, obligations and missed-payment consequences | Partial: source-linked GBP ledger for workshop shifts, café meals, provision orders/refunds and weekly housing without overdrafts; a recorded part-time work agreement with Ellis publishes a week-ahead rota whose shifts pay for hours actually worked, and groceries are a priced weekly shop with daily-held go-without decisions and a courier window; identity-grounded wants are saved for with a cushion, bought on free days, owned and used | P3–P6 |
| SELF-08 | Physical comfort, minor illness, recovery and capacity effects | Partial: rare replayable non-clinical one-to-three-day episodes with monotonic recovery and bounded effects on attention, mood, plans and availability | P3–P6 |
| SELF-09 | Domestic upkeep, accumulating chores and ordinary household consequences | Partial: replayable dishes, laundry, tidying and paperwork loads sourced from daily living, home meals, deliveries and obligations; high load can claim bounded free time | P3–P6 |
| SELF-10 | Developing self-identity: questions about himself, insights, value drift, possible selves, life chapters | Partial: replay-validated loop from lived value evidence to private inquiries, reflection-revisited insights, bounded value steps that flow into identity, evidence-counted hoped/feared selves that pull on volition, and cited life chapters; see [SELFHOOD](SELFHOOD.md) | P4–P6 |

## Planning and time — Chronos / Pathos

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| PLAN-01 | Goals, projects, motivations, progress, completion/abandonment | Partial: motivated goals + model-originated multi-step project progress/completion/audited whole-project failure + ordered materialized replay | P3 |
| PLAN-02 | Intentions, promises, deadlines, dependencies, responsible actors | Partial: consent-linked intentions/commitments + distinct linked intentions for every generated project step | P3 |
| PLAN-03 | Calendar, recurrence, availability, travel, reservations | Partial: durations/conflicts/multi-hop travel buffers/replayed place hours + model-originated personal plans + agreement-sourced work shifts that the employer also keeps | P3 |
| PLAN-04 | Feasibility, priority, conflicts, missed-commitment consequences | Partial: repair/resource/conflict/deadline rules + absent-companion failure | P3 |
| PLAN-05 | Interrupt, postpone, renegotiate, cancel, bounded replan | Partial: interruption, priority-sensitive optional release, reflection-triggered conflict/travel/open-hours-safe personal rescheduling, feasible two-party promise retiming with delayed independent creditor response + atomic project cancellation | P3 |
| PLAN-06 | Proposed/accepted/attempted/resolved distinctions | Partial: separate agency proposal, feasibility, intention, schedule, prospective-memory lapse, action and realized/missed audit; replay-stable forgetting is rare and limited to low-priority solo one-off choices, becomes a mild negative realization and at most a short light concern, while promises, shared plans, projects and reconsideration remain protected | P3 |
| PLAN-07 | Bounded catch-up, meaningful decisions, interval summaries | Partial: preview/chunks/restart/cancel + bounded sourced factual recap | P5 |

## World — Firmament / Moira

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| WORLD-01 | Places, routes, travel, opening hours, occupancy, perception | Partial: four seed places plus replayable registered places with layout/hours/connected-route planning | P3 |
| WORLD-02 | Actor observations, offscreen facts, information propagation | Partial: co-present public-event perception, owner-specific scene memory, public resident conversation overhearing, confidence-decaying resident testimony chains, and no Pathos affect from unperceived private resident dialogue | P3 |
| WORLD-03 | Objects, ownership, condition, inventory, borrowing/gifts/repairs | Partial: consented bounded loans/returns with overdue consequences, gifts, finite household provisions, domestic load, wear, failed repair, replenishment, and project-capable distinct replacements | P3 |
| WORLD-04 | Work, hobbies, activities, skills, finite resources | Partial: accepted work/learn/attend/repair plans, open-ended learning that becomes demonstrated capability, one-off and multi-day self-chosen projects, domestic work, completed bookbinding, feasible exploration, and optional introduced-object projects with co-present participation; planned, delayed, domestic, and recovery beats retain replay-stable place-and-moment texture instead of collapsing to repeated consequence prose | P3 |
| WORLD-05 | NPC-private state, needs, calendars, beliefs and plans | Partial: every persistent person receives cheap deterministic needs and plans; nearby/focused residents may originate schema-checked open-vocabulary plans from owner-only context, including their own private biography, then move/act or fail; audited priorities and critical-energy replanning remain deterministic | P3 |
| WORLD-06 | Event causes, lead time, stakes, cooldowns, participation | Partial: typed weather, attributed inspiration, open-ended resource-backed events, witnessed urgent responses, and multi-stage aftermath | P5 |
| WORLD-07 | Offscreen low-detail simulation, scene activation, pacing | Partial: identity-free town footfall varies by place, hour, weekday, and weather; persistent residents then use explicit background/local/focused cognitive LOD derived from route distance, co-presence, scenes, and Pathos attention without per-NPC bookkeeping events; all named tiers retain bounded hourly movement and six-hour consequences | P5 |
| WORLD-08 | Seasons, recurring events, evolving projects, world packs | Partial: replayable seasons/daily texture, open-ended Moira events that become bounded evolving world threads, rare schema-checked entities entering goals, and atomic additive entity/character-pack releases | P6 |

## Interaction catalog — Pathos and NPC performers

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| SOCIAL-01 | User dialogue, remembered messages/visits, contextual replies, idempotent sends | Partial: persistent delayed inbox that waits through occupied periods plus time-bearing availability-gated live user visits | P2–P3 |
| SOCIAL-02 | Multi-turn greeting, small talk, questions, storytelling, topic shifts, exits | Partial: time-bearing up-to-40-turn user visits with natural endings, replay-stable listening/thinking/speaking seconds and runtime-enforced thought followed by emotion-shaped human-rate speech shared across clients, recent-dialogue continuity, a casual non-assistant Pathos voice whose disclosure and rhythm change without theatrical mood narration, plus one bounded auditable revision when a reply is measurably assistant-like, ungrounded, repetitive, confused, or poorly shaped; an unrepaired known contradiction, identity error, or unsupported activity is rejected rather than delivered; recurring Pathos/NPC and NPC/NPC scenes retain relationship pacing, hourly continuation, voluntary exits, and replay-stable person/topic/turn-aware stand-in dialogue | P3 |
| SOCIAL-03 | Requests, invitations, offers, favors, promises, accept/decline/negotiate | Partial: authored requests, follow-up-driven outbound invitations with independent NPC consent, and sparse resident-originated invitations whose delayed Pathos response reflects his capacity, emotion, values, availability, and real calendar before creating a feasible shared plan | P3 |
| SOCIAL-04 | Shared work, teaching, learning, exploration, play, quiet company | Partial: resident-originated conversation, walks, shared learning, practical help, and quiet company become co-presence-gated scheduled activity with distinct memories and relationship evidence; absent companions create failure rather than invented shared history | P3 |
| SOCIAL-05 | Disagreement, misunderstanding, disappointment, apology, repair, boundaries | Partial: typed disagreement/boundary/apology plus durable post-apology repair attempts that progress only through later direct contact and never imply forgiveness | P3 |
| SOCIAL-06 | Directed trust/familiarity/affection/tension, shared history, obligations | Partial: Pathos and resident-to-resident directed metrics derive from witnessed contact; shared incident aftermath and capped repair contact create evidence-linked changes and follow-ups without automatic trust restoration | P3 |
| SOCIAL-07 | Disclosure, secrets, gossip, unreliable testimony and corrections | Partial: private structured claims can travel through witnessed resident testimony with confidence loss; biography remains familiarity-gated and learned only through witnessed disclosure | P3 |
| SOCIAL-08 | Follow-ups, anniversaries, remembered preferences, opt-in in-app outreach | Partial: source-linked reminders and annual dates, including a completed decision to repair a missed commitment flowing to the actual creditor and their independent invitation response; explicit evidence-bound preferences with correction/fading and invitation influence, plus consented memory-grounded in-app outreach with quiet hours and anti-pressure rejection | P5 |
| SOCIAL-09 | Calls and interruptions: answer/decline, callback, visitors, deliveries, incidents, pause/resume current company | Partial: calls and home visits originate only from people Pathos knows; they, deliveries, and witnessed urgent incidents share the advancing live-conversation clock, with choices, pacing, presence checks, and post-interruption resume/end decisions | P3–P5 |

Every scene needs turn budgets, availability, the right to decline/leave, private
vs public speech, interruption/resume, observer-specific memories and validated
consequences. Not every conversation changes a relationship. Virtual gifts or
money never authorize real purchases. Romance is not assumed as a default mode.

## Inner life — Murmur / Reflection / Oneiros / Chronicler

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| INNER-01 | Structured unresolved concerns and emotional residue | Partial: recent missed promises, strained relationships, failed plans, blocked goals and financial setbacks create bounded source-linked private concerns; later lived evidence resolves them, while unattended issues can recede without being falsely marked solved; semantic cooldown prevents duplicate worries and attentional fatigue lets needs, people, work and commitments displace a concern before it naturally returns; concerns still feed reflection and dreams | P4 |
| INNER-02 | Private associations, cue selection, salience/attention competition | Partial: hourly somatic/affective/association pulses plus a waking quarter-hour real-time Murmur stream emitted at every crossed boundary, including delayed worker intervals, and a bounded Pathos-private cross-faculty workspace; sourced subjective handoffs reach speech, reflection, dreams, activities, and projects without fact or action authority, with inertial foreground competition among needs, domestic load, concerns, goals, people, places and imminent commitments; a separate prospective layer lets plans enter the background up to eight hours ahead with increasing salience while explicitly retaining that they may change | P4 |
| INNER-03 | Reflection proposes interpretations, links, concern/plan updates | Partial: continuous deliberative focus plus source-linked scheduled interpretation whose bounded emotional echo follows the appraised lived source rather than model prose; reflection on an appraised setback can raise an expiring typed planning question, later agency may schedule actual time to reconsider, and completing that review yields a linked typed decision that can release an unobligated blocked goal, safely reschedule personal work, seek consent to alter a promise, or initiate later repair contact | P4 |
| INNER-04 | Sleep/wake transitions, rest recovery, sleep windows, dream budgets | Partial: replayable nightly windows shaped by condition and commitments, with occupied-time delay and legacy fallback | P4 |
| INNER-05 | Dream seeds, transformation, motifs, variation, intensity/recurrence caps | Partial: bounded owned seeds, complete lineage, recent-dream repetition context, and replay-stable combinatorial stand-ins whose motif follows varied dream imagery instead of being monopolized by familiar seed memories | P4 |
| INNER-06 | Partial dream recall, waking affect, inspiration, fading | Partial: recall/capped affect plus an expiring non-authoritative possibility; an aligned ordinary activity or two-to-four-step project may cite that possibility only after normal feasibility acceptance, and its later activity or whole-project success/failure closes the link without turning dream fiction into evidence or action authority; a shared two-week influence cooldown prevents recurring dream motifs from taking over ordinary agency | P4 |
| INNER-07 | Source-linked subjective/objective journals and interval summaries | Partial: factual daybook with complete source membership | P4–P5 |

## UX

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| UX-01 | Observatory: present state, changes, while-away summary | Partial: daily dashboard with communication-only ordinary surface, plain-language upcoming anticipation and its emotional tone, and a separate local operator view | P5 |
| UX-02 | Conversation: asynchronous messages plus available co-present visits, recall context, interruptions, exits, stream/cancel/retry | Partial: occupied-aware delayed inbox plus start/leave controls, elapsed simulated time, and approaching-obligation context for live visits | P2–P3 |
| UX-03 | World/people: active scenes, objects, relationships, private/public lenses | Partial: expanding map, neighbors, world threads, attributed outside inspiration, and versioned pack provenance | P3 |
| UX-04 | Memory explorer: full-history search, provenance, strength, links, revisions | Partial: separate human-facing memory, dream and belief tabs with plain-language uncertainty; complete Pathos-owned archive search/pagination; operator-only provenance/export; and revision-cursor event API | P2–P5 |
| UX-05 | Calendar/projects: intentions, deadlines, conflicts, progress, changes | Partial: linked projects/promises/calendar/audit view; small replay-stable prospective-memory lapses and their consequences are explained in ordinary language | P3 |
| UX-06 | Ensemble: traces, recovery, queue, budgets, context/causal inspector | Partial: latest 100 traces | P1 onward |
| UX-07 | Sleep/dream journal: seeds, remembered fragments, next-day effects | Partial: each dream card now carries its replay-derived recall, bounded emotional residue, waking possibility, activity/project link, and terminal outcome; ordinary language stays separate from operator-only event/causation IDs | P4 |
| UX-08 | Keyboard/mobile/accessibility, reduced motion, onboarding, error/recovery states | Partial: five-view prototype | Every phase |
| UX-09 | Emotional history and behavioral consequences | Partial: the Observatory graphs 48 recent hourly samples, explains source-linked influences and positive adaptation in ordinary language, summarizes current planning pressure, and exposes raw event lineage only in operator mode | P2–P6 |

Operator visibility is not character knowledge. Generated private associations
are simulation artifacts, not the inference model's literal hidden reasoning.

## Operations and verification

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| OPS-01 | Role profiles, health, context/token budgets, prompt/config versions | Partial: strict routing plus durable version/budget/schema/model/token provenance | P1 |
| OPS-02 | Persistent workers, supervision, priority, backpressure, failure policy | Partial: supervised bounded queue with deadlines | P1 |
| OPS-03 | Backups, restore, migrations, checkpoints, private networking, secrets | Partial: backup/replay/schema-4 migration + checksummed disposable state/memory/planning/belief/relationship/consolidation projections | P1 |
| OPS-04 | Dell inventory, compatible stack, benchmarks, routing and monitoring | Planned: hardware pending | Host track |
| OPS-05 | Retention, metrics, swaps, upgrades, rollback, experiment branches | Partial: verified non-merging life forks with clean inference queues, immutable provenance and evidence-based divergence review | P6 |
| QA-01 | Unit/replay/atomicity/idempotency tests, offline fixtures | Built baseline | Every phase |
| QA-02 | Timeout/crash/duplicate/cancellation/stale-result fault injection | Partial: HTTP/concurrency tests | P1 |
| QA-03 | Contract vs semantic evaluations, role probes, honest failure reporting | Partial: contract-separated semantic probe warnings plus open-world semantic critic; every accepted live text call now retains nonblocking quality findings in its durable trace and exposes them in the operator Ensemble | Every phase |
| QA-04 | Recall, forgetting, evidence lineage, hidden-knowledge isolation | Partial: owned recall/belief and source-membership fixtures | P2 |
| QA-05 | Dream/fact separation, affect caps, no action bypass | Partial: category/label checks | P4 |
| QA-06 | Seven-day plan/relationship causality and coherent recall | Partial: exact replay plus routed/durable/structured/deferred integrated week | P5 |
| QA-07 | Month soak, repetition/drift/cost/storage review, model comparisons | Partial: offline month replay/drift/storage gate plus seven-case coverage-reporting narrative/agency/project benchmark; the opening week preserves causal times and places while varying every routine description, and stand-in encounters, dreams and inner thoughts rotate replay-stably; Dell calibration remains | P6 |

## Optional expansion

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| EXT-01 | Local speech input/output, interruption, transcripts | Optional | P7 |
| EXT-02 | Stable character/place imagery, illustrated journals/dreams | Optional | P7 |
| EXT-03 | Richer 2D presentation; 3D only if justified | Optional | P7 |
| EXT-04 | User-selected reading material and source-grounded learning | Optional | P7 |
| EXT-05 | Logos outside tools with explicit permission, preview, audit, revocation | Optional | P7 |
| EXT-06 | More central characters, world packs, hobbies, creative work | Optional | P7 |

## First-release cut

P5 needs the connected memory/plan/social/dream loop, not every possible content
variant. Begin with one project, one object interaction, a small vocabulary of
social moves, explainable recall and bounded dreams. Embeddings, imagery, speech,
large populations, public hosting and microservices are not prerequisites.
