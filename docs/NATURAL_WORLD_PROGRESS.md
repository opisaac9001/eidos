# From scheduled stories to causal simulation

Deployment update: the checked source was installed on the Dell as
`natural20260908a` on September 8. The live clock remains paused and saved events
were preserved. See [deployment record](DEPLOYMENT_2026_09_08.md). Earlier
"local-only" notes below describe the status at those earlier checkpoints.

## Rule

Only Pathos's explicit choice (or an agreement he accepts) authorizes a personal
calendar booking. A thought, desire, place registration or broken object is not
a booking. Time measures change and duration; it does not write his itinerary.

## Implemented locally

- Normal Life runs without the authored daily itinerary, opening-story projects,
  automatic object outings/maintenance bookings or weekly community-event palette.
  Historical fixture tests opt into `authored_scenario=True` explicitly. This
  developer-only option is off by default and is not exposed as a user control.
- Exploration registration and adopted intentions no longer make the scheduler
  pick tomorrow's first available hour. The compatibility entry point emits nothing.
- Activity and project planning respond to fresh thoughts/experiences rather than
  every-other-day or fortnightly appointments with the model. Pathos can leave the
  idea unplanned. A deliberate plan includes his selected time and duration.
  Activity planning also permits starting now, but only if he is already there.
- The life loop does not ask for these plans while asleep or in an active scene.
  Existing calendar, resource, travel and consent validation remains in place.
- World improvisation responds to fresh arrivals, NPC activity or object-condition
  changes at the cause's location. No change is valid. Accepted developments happen
  now, not at a fabricated future start. A cause is considered once, including on
  rejection. Arrival-driven catalog expansion retains the same ordinary/no-change option.
- New causal world threads do not advance invented stories on a timer. Expiry ends
  an operator observation window with outcome unknown; it creates no NPC promises,
  success, perception or personal memory. Actual action-driven aftermath remains
  further work.
- Present-moment thoughts are retained even without a memory to associate with.
  Deferred thought generation works without manufacturing a source memory; applied
  results remain private, non-factual, and deduplicated.

## Preserved

Historical events and existing appointments are unchanged. Legacy world-thread
events still replay. No old bookings have been cancelled automatically; review a
saved-state copy before changing obligations derived from them. The Alderwick
blueprint has not been imported and the live clock has not been advanced.

## Remaining work — not claimed complete

### Fleeting thought/dream lifecycle and real-model probes

The direct inner-stream context no longer replays the last eight thoughts forever.
Short-lived owned thoughts fade from working context; normal dreams no longer all
become permanent verbatim memories plus inspirations. Occasional fragments and
inspirations are separate, replay-stable selections with no booking authority.
Normal waking recall follows awake state rather than a hard-coded 07:00 check.
Observer history is preserved. See [Thought/dream evaluation](THOUGHT_DREAM_EVALUATION.md)
for the implemented policy, actual Pi/Dell comparison and remaining limitations.

### Flexible time and actual effort follow-up

Personal activity proposals now support fractional hours (one-minute minimum) rather
than a one-to-four-hour minimum block. The agency, Murmur and conversation contexts
receive the next accepted plan, route time and remaining free minutes. Instructions
permit shorter choices, skipping optional preparation, lingering or doing nothing;
they do not create a morning checklist or claim any preparation happened.

Normal Life records actual activity starts and eligible elapsed effort separately
from calendar reservations. Minute-scale boundaries work without multiplying hourly
body or model updates. Absence, sleep, conversations and incident responses do not
count as effort. Completion requires evidence; a missed window retains unfinished
work without automatically abandoning the intention/project or fulfilling a promise.
The authored scenario keeps legacy execution for historical fixtures.

Snapshot inspection exposes detailed effort; personal context gets rough, bounded
recent activity descriptions, not an exact permanent autobiographical ledger. Actual
started activity can ground speech; a merely planned title cannot establish doing it.

Limits: this is still interval-based activity, not a sequence of cooking/repair/etc.
stages. Every reserved second is currently required, so lateness tolerance and task
scope changes need explicit rules. Resumption within an accepted window is basic,
not a separate deliberative choice. Cross-session partial-work carryover, continuous
Pathos travel, UI presentation and live-model dialogue evaluation remain unfinished.
Existing Pathos planned travel still uses the older coarse resolver; no claim is made
that the time-budget context alone solves physical departure/preparation.

All eight areas and behavioural gates are tracked in [Natural life next](NATURAL_LIFE_NEXT.md).
Final regression: 729 tests and 68 subtests passed (month soak excluded). The focused
cross-system run passed 61 tests and two subtests; after adding restart verification,
all 16 activity/time-budget tests passed. Changed-file lint and diff checks pass.
Five directly changed application/domain modules pass static typing. Checking Life
also reports the pre-existing untyped city_map call; this pass does not claim a clean
whole-application type check. No deployment, migration or live clock changes.

### NPC movement and persistent opportunities follow-up

Normal NPC updates now keep recorded positions instead of assigning stock locations
by the hour. Their private plans produce departure records, route-duration arrivals
and a separate work interval before completion. Fractional Life advances process
arrivals between hourly cognition checks. The authored path is retained only for
explicit scenario tests. Unplanned time creates no fabricated activity record.

The richer NPC planner no longer waits for day 11 or 19:00; it considers fresh owned
need evidence. Residents can leave it unplanned, and equivalent pressure bands are
not retried on every update. Plans allow same-day choices and any hour, while model
calls remain limited to residents promoted by proximity/attention. Low-detail
need planning no longer requires 19:00 in normal mode.

Opportunities are persisted from Pathos-owned observations, with source links and
no action authority. They feed his activity context without creating bookings.
An observed duration supplies a bounded availability horizon; this is not proof of
a world event's outcome. Expired possibilities stay in history, not active context.
Private observations belonging to other residents do not create his opportunities.

Limits: this is NPC travel, not yet Pathos's continuous travel. Work duration is a
one-hour baseline. Private homes still use a coarse home anchor, never shared
co-presence. Need drift is sampled at least 15 minutes apart; its rates are based
on elapsed time. Richer interrupted journeys, activity-specific durations, explicit
opportunity decisions/withdrawal and UI presentation remain further work.

Verification: 713 regression tests and 68 subtests passed (month soak excluded).
The subsequently added fractional-Life-arrival integration check passed with the
four focused NPC/opportunity checks. No live deployment or saved-world edits.

### Other remaining work

- The main simulation still evaluates many systems on hourly boundaries. Movement
  and activity duration need finer-grained execution and interruption handling.
- NPC background movement, bodily rhythms, weather checks and some older response
  systems still contain clock-based rules. They need separate causal audits.
- Build richer durable opportunities (invitations, errands, observed problems) and
  let actual participants' actions advance incident aftermath.
- Catalog registration is not yet a full source-aware personal discovery system.
  The director knows the catalog for continuity; that must remain separate from
  what Pathos actually knows.
- Calibrate stochastic rates against elapsed time and world conditions, not number
  of model calls. This change removes script triggers; it does not yet implement a
  complete probabilistic town economy or population.
- A fresh source prompts consideration, not necessarily a meaningful new decision.
  Further salience filtering should avoid repeatedly reconsidering equivalent thoughts.

## Verification

Focused checks cover no booking from desire, quiet decisions, source deduplication,
invalid/stale/future causes, immediate world developments, no fabricated aftermath,
deferred thoughts without memories, explicit plans, and default un-scripted life.
The historical acceptance scenario is tested explicitly rather than silently
enabled in normal runs. Live-model behaviour and the month-long soak remain unverified.

Final regression run: 708 tests and 68 subtests passed, excluding the month soak.
The latest focused causal-opportunity run passed all seven checks, including the
subsequently added project-decline trace check. Type checks passed for the six
changed causal/planning application modules; changed-file lint and diff checks passed.
No server deployment or live saved-state migration was performed.
