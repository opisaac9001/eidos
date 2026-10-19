# Flexible mornings — September 8, 2026

First delivery from the next natural-life queue: optional scales of preparation,
competing needs in agency context, proportional household consequences and a
repeatable morning comparison. Local implementation only; not a complete morning,
attention or cooking simulation.

## Implementation

- The personal agency prompt now receives optional small-batch, medium and longer
  dish sessions when Patrick is home and a pile is noticeable. They are examples,
  not a closed action vocabulary, default choice, checklist or new scheduler.
- Available time is still calculated after travel to his accepted commitment.
  Estimates include a rough range; low energy widens the range. They are not
  enforcement rules or guarantees of speed. Energy, hunger and wanting company
  appear as potentially conflicting considerations; no highest-need winner is forced.
- No-change remains valid. Nothing in this context performs a chore, moves an
  appointment, satisfies hunger, or guarantees another person's availability.
- Washing output now scales with elapsed washing-stage effort. A one-minute
  reservation cannot clear the same pile as thirty minutes. The calibrated maximum
  remains 0.55 load per session; a large backlog can remain even after a long session.
  Output is applied once at the wash-stage boundary, with its existing causal link.
  It is not yet a continuous per-dish physical simulation.
- Positive start delays now also require enough time to reach a proposed location;
  the previous application check only rejected an immediate start elsewhere.
- Personal agency proposal profile is now version 7. HTTP context filtering retains
  the preparation field. No extra periodic cognition or automatic wake-up was added.

## Controlled acceptance tests

The explicit **test-choice gateway** selects 5, 15 and 30 minutes of washing when
15, 40 and 90 minutes are available before departure. With initial dish load 0.8,
the remaining loads are approximately 0.7083, 0.525 and 0.25. Each test reaches the
same workshop appointment at 09:00. These tests demonstrate execution and
consequences, not an LLM's ability to choose naturally.

Additional cases cover no change while tired/lonely, rejecting an overlong choice
without silently shortening it, rejecting a one-minute-away start at a distant
place, only noticing domestic alternatives at home, fatigue-dependent estimates,
and 1/5/15/30-minute proportional output. Coarse/fine execution and repeated polling
cannot duplicate a short batch's cleaning effect.

Final focused tests: **43 passed, 10 subtests passed in 11.92 seconds**. The broader
regression run passed **788 tests and 91 subtests in 490.93 seconds**, excluding
only `test_month_soak.py`. It includes the nine-day natural-life replay test. Five
additional short-session/tick-invariance cases were added after that run collected
tests and passed in the focused run; these are separate results, not a claim that
one final monolithic run covered all 793 tests. No fresh month soak was run for
this pass. Scoped Ruff and `git diff --check` passed.

## Real-model evidence, not scripted choices

`infra/morning_trial.py` builds independent synthetic histories and sends the real
agency request through its normal parser, feasibility validation and natural
journey/activity executor. It never reads the live database. Each trial makes one
agency decision; the subsequent execution window does not simulate all intervening
thoughts, bodily changes, messages or opportunities. These are controlled agency
comparisons, not full-day Life runs or isolated proof of an energy effect.

Qwen 2.5 14B on the existing P40 worker: three repeats of each 15/40/90-minute case,
plus three tired-and-lonely 40-minute cases. Thinking was requested off. Median
request time was 8.42 seconds, not human-facing delivery time.

- **11 of 12 proposals accepted.** One 15-minute-window proposal delayed starting
  by 15 minutes and then booked another 15; the travel constraint rejected it.
- Accepted sessions varied from 3 to 15 minutes, with genuinely different cleaning
  consequences. The tired/lonely samples selected 7.5, 6 and 7.8 minutes.
- The three 90-minute samples all chose to start thirty minutes later. This records
  a delayed choice; it is not proof that he consciously procrastinated or rested.
- Every case reached the unchanged work appointment at 09:00, including the rejected
  optional chore. No failure generated an automatic substitute task.
- **All twelve proposed dishes. None chose no change.** The fixture explicitly
  notices the pile and the available examples concern dishes, so this does not
  demonstrate broad motivational diversity. Do not force different activity names
  or bigger sessions merely to make this comparison look varied.

Raw requests, responses and execution summaries:
`data/evaluations/morning-choices-20260908-v1/results.json`.

## Remaining work

Compare weaker and absent chore cues, personal interests and competing opportunities
without inserting a compulsory choice. Expand genuine supported activities such as
food preparation and laundry; their resource effects must exist before narration
can claim them. Add uncertain task duration and deeper interruption/attention
decisions. This patch does not fix the earlier past-completion wording over-rejection
in agency motivations, and the observed travel-planning error remains a model-quality
limitation caught by validation rather than an automatically repaired answer.

No production deployment, live history changes or model promotion. After testing,
the used Qwen 14B worker was re-warmed at its original 8192-token context with
indefinite keep-alive, and the temporary SSH forward was closed. Live revision
remained 4108, time `2026-01-07T23:12:27.335054+00:00`, paused, with no runtime error.
