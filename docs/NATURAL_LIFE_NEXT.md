# Natural life: implementation sequence and acceptance criteria

September 8, 2026. This is an ongoing programme, not a claim that all eight areas
are complete. See NATURAL_WORLD_PROGRESS.md for the local implementation record.

Newer follow-up: [Flexible mornings](FLEXIBLE_MORNINGS_2026_09_08.md) adds optional
preparation scales, proportional dishwashing output, current-location travel checks,
and controlled plus real-model morning comparisons. Motivation remains partial;
the real model still strongly follows the chore cue.

Latest follow-up: [Lived-day integration](LIVED_DAY_2026_09_08.md) adds staged work,
source-linked dish consequences, rescheduled effort carryover, bounded resumption
choices, actual journeys and phone-call duration, NPC-owned relationship context,
UI progress/unread support, and twelve-hour real-model replay evidence. The older
delivery sequence below describes the starting gaps; the dated report records
which portions are now implemented and which remain.

September 9 follow-up: [Bounded volition and lived consequences](VOLITION_2026_09_09.md)
adds limited attended impulses, explicit inaction, uncertain effort, switching costs,
engrossment and missed notifications, physical meal consequences, operator inspection,
and real-model evidence. A later calibration in the same report separates private
deliberation from practical scheduling, rejects motive substitution, and treats even
high-confidence duration estimates as fallible. The remaining items below should be
read in light of that newer status.

## Fixed commitments, flexible life around them

An accepted job can start at 09:00. That does not authorize a daily 07:00 wake-up,
07:10 shower and 07:30 breakfast script. Preparation depends on energy, hunger,
available supplies, what was left ready yesterday, attention and time after travel.
He can leave something out, linger, improvise, procrastinate or arrive late. Each
choice must leave its actual consequences. Variation is not a daily randomness quota.

Time measures duration, opening hours, bodily change and accepted commitments.
It should not silently invent decisions. A shorter morning should change what gets
done, not merely the generated description of an identical sequence.

## Delivery order

1. **Activities and time pressure — first local foundation implemented.**
   Personal choices allow fractional hours down to one minute. Planning, thought
   and speech receive available time after route cost. Separate execution records
   measure eligible elapsed effort. Sleep, absence, conversations and incident
   responses cannot be counted as work. Minute-scale accepted start/end boundaries
   do not accelerate hourly cognition. Multi-stage activities, variable preparation
   and physical travel now have local implementations. Remaining: richer resources
   per stage and lateness negotiation.

2. **Attention and interruptions — working local foundation.**
   Preserve partial effort and recognize a lost work window without erasing the
   intention, project or promise. Resume, defer and shorten choices now record
   differing switching costs; engrossment can delay phone awareness; estimated and
   actual work duration are separate. Remaining: voluntary abandonment and
   renegotiation across more activity families, plus behavioral calibration.

3. **Persistent consequences — partial.**
   Opportunities and unfinished effort survive their initial event. Remaining:
   completed activity stages affect inventory, dishes, borrowed objects and other
   people. Link a newly chosen work session to earlier partial work without
   double-counting it. A window ending is not a project failing or a promise fulfilled.

4. **Relationships with history — extend existing mechanics.**
   Use source-linked interactions and unmet commitments, not global friendship
   scores alone. Keep each person's interpretation private. Acceptance: a favour,
   repeated lateness and an attempted repair lead to different later encounters;
   forgiving someone does not erase the event, and one-sided trust is not reciprocity.

5. **Competing motivation — bounded local foundation.**
   A capacity-limited choice field now admits competing needs, habits, thoughts,
   opportunities, chores, momentum and inaction before private deliberation. Continue,
   wait, defer and do nothing are explicit outcomes. Only a selected impulse reaches a
   separate scheduling call, and deterministic alignment checks reject substitution.
   Continue connecting emotional state to effort estimates, initiation and switching
   decisions.
   No parameter should compel a scripted behaviour or clinical diagnosis. Acceptance:
   tired-but-lonely, energetic-but-short-of-time and unhurried states offer different
   plausible choices, including inaction, from the same opportunity.

6. **Fallible interpretation — extend existing recall and beliefs.**
   Keep exact operational ledgers out of autobiographical recall. Recent work can
   provide rough present context; older interpretations must use memory pathways.
   Acceptance: source confusion, high-confidence wrong recall and evidence-driven
   revision affect choices without leaking the director's hidden truth.

7. **Independent NPC unfinished business — extend natural NPC baseline.**
   Add activity-specific stages and durations, reciprocal invitations, declined
   approaches and later follow-ups driven by their own goals. Keep cheap distant
   continuity and richer near-field cognition. Acceptance: an NPC initiates for
   their own reason, remains consistent offscreen, and need not accommodate Pathos.

8. **Conversation and inspection — context connected; presentation remains.**
   Ground speech in recent actual effort and felt time pressure, not invented
   accomplishments. No mandatory insight, joke, question or emotional explanation.
   Remaining: evaluate live-model conversations in contrasting everyday conditions,
   and show current work, interruptions, journeys and unfinished threads in the UI.
   Inspection may show exact simulation state; interaction remains messaging/visits.

## Behavioural acceptance, beyond unit tests

- Compare the same accepted 09:00 commitment with 15, 40 and 90 minutes available.
  Inspect chosen scope and actual actions, not whether the prose sounds different.
- Interrupt an activity after five minutes, return ten minutes later, then compare
  it with uninterrupted work. Lost time must not become accomplishment.
- Compare one large explicit advance with minute-by-minute advances; equivalent
  evidence should produce equivalent effort, without extra model calls or randomness.
- Follow a borrowed book, failed promise and unfinished task across several days.
  Yesterday should matter without injecting perfect memory of yesterday.
- Allow a quiet afternoon. No event, plan, message or revelation is required.
- Audit conversations for repeated openings, generic empathy, forced questions,
  invented current activities and overly articulate explanations of every feeling.
- Run a saved-world copy with the actual deployed models before deployment. Offline
  contract tests are not evidence of humanlike dialogue or scientific human cognition.

The current change is local only. No server update, world migration, real-time clock
resume or alteration of existing saved obligations has been performed.
