# Feature inventory

Companion to the [roadmap](ROADMAP.md). Stable IDs are planning handles, not
existing classes/services. Built = tested prototype; Partial = narrow version;
Planned = missing; Optional = deferred. Phases indicate next substantial delivery.

## Simulation and cognition

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| CORE-01 | Atomic event history, replay, revisions, pause/resume | Built | P0 |
| CORE-02 | Typed proposals, causation/entity IDs, schema migration, preconditions | Partial: action/intention/world-event/social/speech/belief/association/travel/relating + trace migration | P1 |
| CORE-03 | Durable jobs, priority, cancel/retry, stale results, idempotent effects | Partial: supervised workers + detached/revalidated Murmur results | P1 |
| CORE-04 | Actor visibility and capability-limited context | Partial: role filtering + speech audience perceptions | P1–P2 |
| CORE-05 | Attention/generation budgets and optional work shedding | Partial: request limits + nonblocking Murmur/capacity shedding | P1 |

## Memory and belief — Ethos / Mnemosyne

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| MEM-01 | Owned experiences, source links, confidence, importance, emotional tags | Partial: owner/source/confidence/importance | P2 |
| MEM-02 | Working context, episodic/semantic/recent/dream memory distinctions | Partial: recent seven | P2 |
| MEM-03 | Cue/entity/goal retrieval, diversity, score explanations, optional embeddings | Partial: term/entity/goal/relationship indexes + diverse explanations | P2 |
| MEM-04 | Accessibility/detail fading, rehearsal, reminders, bounded reinforcement | Partial: time decay/capped rehearsal | P2 |
| MEM-05 | Consolidation, recurring themes, source-linked summaries | Partial: owner-separated daily themes with complete source membership | P2 |
| MEM-06 | Associations, resurfacing cues, unfinished-concern links | Partial: typed source-linked associations with bounded attention | P2 |
| MEM-07 | Owned beliefs, uncertainty, testimony reliability, correction history | Partial: discounted testimony, direct confirmation and revision ledger | P2 |
| MEM-08 | Intentional imperfect recall distinct from world truth | Partial: conservative detail omission in working context | P2 |
| MEM-09 | Long-run retention/index maintenance and archive policy | Planned | P6 |

Accepted encounter evidence already has explicit deterministic archive recovery.
Actual user-requested data deletion is a privacy workflow, not simulated fading.

## Self, affect and needs — Pathos / Hexus / Ethos

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| SELF-01 | Stable identity, values, preferences, sourced backstory, knowledge limits | Partial: persisted sourced values/preferences + bounded context | P2 |
| SELF-02 | Multidimensional affect, appraisal, episodes and baseline mood | Partial: source-linked valence/arousal episodes + recovery | P2 |
| SELF-03 | Rest, connection, curiosity, mastery; bounded satisfaction/frustration | Partial: durable needs with circadian pressure/recovery | P2–P4 |
| SELF-04 | Emotional residue, recovery, regulation, capped dream carryover | Partial: sleep cycle + capped non-action dream appraisal | P2–P4 |
| SELF-05 | Decisions balance values, needs, commitments and feasible options | Partial: sourced values + energy/rest/mastery/window policy | P3 |
| SELF-06 | Slow trait/preference change, habits, skills, evidence/drift limits | Planned | P6 |

## Planning and time — Chronos / Pathos

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| PLAN-01 | Goals, projects, motivations, progress, completion/abandonment | Partial: linked accepted-work goals | P3 |
| PLAN-02 | Intentions, promises, deadlines, dependencies, responsible actors | Partial: consent-linked intentions/commitments | P3 |
| PLAN-03 | Calendar, recurrence, availability, travel, reservations | Partial: durations/conflicts/travel buffers/open hours | P3 |
| PLAN-04 | Feasibility, priority, conflicts, missed-commitment consequences | Partial: repair/resource/conflict/deadline rules | P3 |
| PLAN-05 | Interrupt, postpone, renegotiate, cancel, bounded replan | Partial: interruption/reschedule and social deadline negotiation | P3 |
| PLAN-06 | Proposed/accepted/attempted/resolved distinctions | Partial: proposed/accepted/rejected action audit | P3 |
| PLAN-07 | Bounded catch-up, meaningful decisions, interval summaries | Planned: restart pauses | P5 |

## World — Firmament / Moira

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| WORLD-01 | Places, routes, travel, opening hours, occupancy, perception | Partial: four places + typed routes/open hours | P3 |
| WORLD-02 | Actor observations, offscreen facts, information propagation | Partial: co-present public-event perception and owned memory | P3 |
| WORLD-03 | Objects, ownership, condition, inventory, borrowing/gifts/repairs | Partial: validated lamp custody/location/repair | P3 |
| WORLD-04 | Work, hobbies, activities, skills, finite resources | Partial: authored routine | P3 |
| WORLD-05 | NPC-private state, needs, calendars, beliefs and plans | Partial: persisted movement and private low-detail needs/activity | P3 |
| WORLD-06 | Event causes, lead time, stakes, cooldowns, participation | Partial: typed weather pacing/causes | P5 |
| WORLD-07 | Offscreen low-detail simulation, scene activation, pacing | Partial: bounded hourly movement and six-hour activity | P5 |
| WORLD-08 | Seasons, recurring events, evolving projects, world packs | Planned | P6 |

## Interaction catalog — Pathos and NPC performers

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| SOCIAL-01 | User dialogue, remembered visits, contextual replies, idempotent sends | Partial: limited context | P2–P3 |
| SOCIAL-02 | Multi-turn greeting, small talk, questions, storytelling, topic shifts, exits | Partial: single encounter | P3 |
| SOCIAL-03 | Requests, invitations, offers, favors, promises, accept/decline/negotiate | Partial: bounded favors and scheduled invitations with explicit consent | P3 |
| SOCIAL-04 | Shared work, teaching, learning, exploration, play, quiet company | Partial: co-present scheduled time together | P3 |
| SOCIAL-05 | Disagreement, misunderstanding, disappointment, apology, repair, boundaries | Partial: typed disagreement/boundary/apology with unresolved-rupture rule | P3 |
| SOCIAL-06 | Directed trust/familiarity/affection/tension, shared history, obligations | Partial: directed metrics/causal trust | P3 |
| SOCIAL-07 | Disclosure, secrets, gossip, unreliable testimony and corrections | Partial: private structured claims and confidence-weighted review | P3 |
| SOCIAL-08 | Follow-ups, anniversaries, remembered preferences, opt-in in-app outreach | Partial: source-linked internal follow-up reminders | P5 |

Every scene needs turn budgets, availability, the right to decline/leave, private
vs public speech, interruption/resume, observer-specific memories and validated
consequences. Not every conversation changes a relationship. Virtual gifts or
money never authorize real purchases. Romance is not assumed as a default mode.

## Inner life — Murmur / Reflection / Oneiros / Chronicler

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| INNER-01 | Structured unresolved concerns and emotional residue | Partial: concern lifecycle/dream residue | P4 |
| INNER-02 | Private associations, cue selection, salience/attention competition | Partial: sourced private/surfaced associations | P4 |
| INNER-03 | Reflection proposes interpretations, links, concern/plan updates | Partial: source-linked scheduled interpretation | P4 |
| INNER-04 | Sleep/wake transitions, rest recovery, sleep windows, dream budgets | Partial: routine bedtime | P4 |
| INNER-05 | Dream seeds, transformation, motifs, variation, intensity/recurrence caps | Partial: bounded owned seeds, motifs and complete lineage | P4 |
| INNER-06 | Partial dream recall, waking affect, inspiration, fading | Partial: explicit recall/capped effect | P4 |
| INNER-07 | Source-linked subjective/objective journals and interval summaries | Partial: factual daybook with complete source membership | P4–P5 |

## UX

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| UX-01 | Observatory: present state, changes, while-away summary | Partial: daily dashboard | P5 |
| UX-02 | Conversation: recall context, availability, uncertainty, stream/cancel/retry | Partial: chat/sidebar | P2–P3 |
| UX-03 | World/people: active scenes, objects, relationships, private/public lenses | Partial: map/neighbors | P3 |
| UX-04 | Memory explorer: full-history search, provenance, strength, links, revisions | Partial: latest 300 search/export | P2–P5 |
| UX-05 | Calendar/projects: intentions, deadlines, conflicts, progress, changes | Partial: linked projects/promises/calendar/audit view | P3 |
| UX-06 | Ensemble: traces, recovery, queue, budgets, context/causal inspector | Partial: latest 100 traces | P1 onward |
| UX-07 | Sleep/dream journal: seeds, remembered fragments, next-day effects | Partial: motif/seed journal and waking effects | P4 |
| UX-08 | Keyboard/mobile/accessibility, reduced motion, onboarding, error/recovery states | Partial: five-view prototype | Every phase |

Operator visibility is not character knowledge. Generated private associations
are simulation artifacts, not the inference model's literal hidden reasoning.

## Operations and verification

| ID | Feature | Status | Phase |
| --- | --- | --- | --- |
| OPS-01 | Role profiles, health, context/token budgets, prompt/config versions | Partial: one endpoint/model | P1 |
| OPS-02 | Persistent workers, supervision, priority, backpressure, failure policy | Partial: supervised bounded queue with deadlines | P1 |
| OPS-03 | Backups, restore, migrations, checkpoints, private networking, secrets | Partial: verified online SQLite backup/replay + migrations/loopback | P1 |
| OPS-04 | Dell inventory, compatible stack, benchmarks, routing and monitoring | Planned: hardware pending | Host track |
| OPS-05 | Retention, metrics, swaps, upgrades, rollback, experiment branches | Planned | P6 |
| QA-01 | Unit/replay/atomicity/idempotency tests, offline fixtures | Built baseline | Every phase |
| QA-02 | Timeout/crash/duplicate/cancellation/stale-result fault injection | Partial: HTTP/concurrency tests | P1 |
| QA-03 | Contract vs semantic evaluations, role probes, honest failure reporting | Partial: lab probes/critic | Every phase |
| QA-04 | Recall, forgetting, evidence lineage, hidden-knowledge isolation | Partial: owned recall/belief and source-membership fixtures | P2 |
| QA-05 | Dream/fact separation, affect caps, no action bypass | Partial: category/label checks | P4 |
| QA-06 | Seven-day plan/relationship causality and coherent recall | Partial: deterministic multi-day causal fixtures | P5 |
| QA-07 | Month soak, repetition/drift/cost/storage review, model comparisons | Partial: offline month replay/drift/storage gate | P6 |

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
