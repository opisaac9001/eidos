# Grounding failures: fixes and repeat checks

## Implemented

1. **Missing memory is not a denial.** A conservative check catches categorical
   denials of calls, meetings, purchases or sales when no corresponding subjective
   evidence is supplied. It requests one bounded revision, then withholds a still-
   unsupported denial. User questions do not count as evidence of Patrick's actions.
   Explicit subjective recollections, including confidently mistaken ones, still
   take precedence; the check never consults hidden historical truth.
2. **Revisions cannot trade away one serious failure for another.** Previously a
   revision with fewer warnings could be selected even with a blocking finding
   remaining. Selection now requires no remaining blocking findings. Regression
   coverage includes a reply that removes assistant phrasing but keeps its false denial.
3. **World cause details are useful and bounded.** The director now receives only
   whitelisted physical facts appropriate to the event: actor/action, arrival, or
   object/condition. Private activity titles, motives, thoughts and plan descriptions
   are excluded. Object-condition events lacking location can resolve it from the
   supplied known-resource map. Patrick's arrival explicitly identifies him, not “the user.”
4. **Complete JSON no longer excuses obvious clipped prose.** World validation
   rejects dangling clauses/punctuation and opaque UUID-only causes. Generation
   instructions request short complete phrases rather than filling each character
   limit. These are conservative syntax checks, not a general grammar oracle.
5. **Patrick's full name shares Pathos's agency protection.** World prose cannot
   pre-commit actions under either name, including inventing a purpose for his arrival.
6. **NPC perspective is explicit.** The preceding speaker-attributed scene handoff
   is reinforced with instructions that shared topics and another actor's time
   pressure are not the NPC's own schedule. Prior book recommendations cannot be
   invented just to make an exchange sound familiar.
7. **Habit evidence represents distinct days.** The full-suite month simulation
   exposed repeated same-day activities being counted as separate days of habit
   evidence, producing an event that strict replay rejected. Formation, reinforcement
   and competing-habit selection now use the latest source per distinct day. Tests
   prove that six activities on two days do not establish a three-day rhythm, and
   that multiple activities on three days produce exactly three replayable sources.
8. **Separate authored acceptance from natural-life invariants.** After the habit
   correction, the natural 30-day simulation completed and its exact replay passed,
   but the old month test demanded a specific emotional itinerary (including
   contentment). Its remaining exact illness/dream expectations are also authored-
   scenario fixtures, like the existing authored week test. The month test now
   explicitly opts into that fixture mode; the production default stays natural.
   A separate nine-day natural-life/restart test checks bounded state and distinct
   habit evidence without imposing emotional, illness or habit-formation quotas.
   The month fixture also no longer requires a dream to become a plan. Any actual
   link still undergoes all provenance and execution checks; dedicated dream-planning
   and fleeting-stream tests exercise both linking and discarding. Month simulation
   generation and its assertions are split so retained diagnostic histories can be
   inspected without repeatedly generating identical months.
   Optional self-directed projects, new preferences, a particular landmark visit,
   and world-thread developments likewise have no monthly occurrence quota.
   Their actual events retain lifecycle/provenance checks, and dedicated feature
   tests still cover positive creation and completion paths.

Personal reply task version 11; Firmament 6; world-event proposal 6. These changes
are local code, not a production model promotion or historical data migration.

## Real-model evidence

Gemma 31B on a P40; Gemma 12B on the RTX3060. Context 8192, thinking disabled,
synthetic fixtures only. The normal server workers were temporarily unloaded and
restored afterward; no actual conversation or world state was advanced.

- Full 24-case personal battery: unknown call becomes “I don't remember calling him
  today. What do you mean?” following one audited revision. Unknown car becomes
  “I don't remember having a green Volvo.” Supported calls and current car ownership
  remain intact. Confident recall: “I met Mara.” Uncertain recall remains tentative.
- Three repeats of eight focused cases: 24/24 returned selected text. All six
  personal evidence/uncertainty cases and the two NPC perspective cases retained
  the targeted distinction in each repeat. One repeated call case needed a revision.
  These are stochastic small-sample checks, not proof against every paraphrase.
- NPC deadline reply now acknowledges **Patrick's** rush rather than inventing the
  NPC's own shift. Book replies no longer invent Patrick's prior recommendation in
  these samples. Some ordinary detail invention remains, such as coffee or two books;
  that is not proof of an actual prior event and is not allowed to execute actions.
- Two world/scene runs: world fields are complete rather than cut off; causes are
  plain language rather than UUIDs. Both repaired-object cases retain the repaired
  condition. Existing validators still reject other low-detail proposals. One later
  proposal invented Patrick's purpose on arrival; the expanded alias/action guard
  now rejects that pattern, with dedicated tests for all three names.
- Replayed all six previously accepted malformed proposals from the two prior Gemma
  12B trials: **6/6 now rejected as incomplete prose**. A separate fixture verifies
  rejection of a UUID cause even when the rest of the proposal is well formed.
- No-cause and already-handled-cause calls still make no model request and emit no
  additional world event. Quiet remains a valid outcome, not a failed novelty quota.
- All returned reasoning fields remained empty. No Pi load or disk changes.

Raw artifacts in `data/evaluations/`:

- `patrick-gemma4-31b-denial-repair-20260908.json`
- `grounding-regression-repeats-20260908.json`
- `world-gemma4-12b-causal-repair-20260908.json`
- `world-gemma4-12b-causal-repair-repeat-20260908.json`

## Limits

This resolves the measured failures and adds guardrails; it does not make either
model perfectly natural or a general truth detector. The denial detector deliberately
defers when matching subjective evidence exists, rather than silently correcting
Patrick against the operator's private record. World proposals can still need manual
quality evaluation even when they satisfy schema and syntax. No silent fallback
fills rejected world developments with a scripted event.

## Final verification

- Regression suite excluding the two long soak files: **755 tests and 91 subtests
  passed** (103.49 seconds).
- Nine-day natural-life soak: **1 test passed**, including restart/replay and
  distinct-day habit evidence (39.65 seconds).
- Authored 30-day simulation completed through 2026-01-31. After correcting the
  outdated occurrence quotas, **all final month assertions passed** against that
  retained history, including exact replay, bounds, source links and database-size
  limits. The assertions were rerun on the completed dataset rather than generating
  another month; this is not a claim that a single final full-suite invocation passed.
  Retained synthetic dataset: `/tmp/eidos-month-verified.UnKJjQ/month.sqlite3`.
- Changed-code lint and `git diff --check` passed.
- Final server check: original Qwen 14B / 14B / 7B workers restored on ports
  11434 / 11435 / 11436, each at 8192 context. Model-route file unchanged
  (SHA256 `1a10653e996ed18dec2c071e954680eb2e5ae30d67c659926327c699a6c97cac`).
  Live simulation remains paused at revision 4108, time
  `2026-01-07T23:12:27.335054+00:00`, with no runtime error.

Test tunnels are closed; the existing UI connection is preserved. No production
deployment, model promotion, simulation resume, or live-history mutation was made.
