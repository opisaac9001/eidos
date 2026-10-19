# Fleeting thoughts and dreams — September 8 local work

## Behaviour, not a permanent inner diary

The observer's event archive is not Pathos's accessible memory. Ordinary thoughts
remain inspectable without being copied indefinitely into the model context.

- Direct inner-stream context holds at most three owned thoughts younger than
  30 simulated minutes. Old, future and other residents' private thoughts are excluded.
  Thought-triggered planning uses the same 30-minute cutoff so a discarded thought
  is not resurrected from the archive merely to solicit a plan.
- Thought workspace salience halves every ten minutes and drops out below a small
  threshold, with a 45-minute maximum. Associations and recalled dream fragments
  fade on a separate shorter-than-before timescale. Reading context does not renew it.
- In normal Life, waking dream processing requires being awake rather than 07:00.
  Most dreams leave no recalled scene. Mood residue can remain without memory.
- Replay-stable, per-dream selections separately decide fragment recall, memory
  retention and fleeting inspiration. A retained memory is a bounded dream fragment,
  explicitly non-factual and lower-confidence, not an automatic verbatim dream archive.
  An inspiration expires after 45 minutes and gets no guaranteed workspace seat.
- None of these events creates a booking or action. Existing action/outreach gates
  remain separate; their salience calibration still deserves further evaluation.
- Explicit authored-scenario fixtures retain the old guaranteed dream-recall path.
  Previously saved records are not deleted, rewritten or migrated.

The durations, decay rates and selection probabilities are tunable simulation design
choices, not measured claims about human psychology. Deliberately remembering,
rehearsing or acting on a thought requires a separate lifecycle; this change does not
implement a full model of human forgetting.

## Performer corrections

Murmur v7 asks for short private waking fragments, not messages or speeches. Certainty
can follow supplied memory confidence without making the belief true. Imagination is
allowed as possibility; completed actions and other people's feelings are not invented
as waking facts. A short fragment need not contain the pronoun I.

Oneiros v6 permits mundane or impossible dream scenes, without demanding symbolism,
a moral or an explanation. Dream fiction remains labeled. The HTTP adapter previously
dropped time/recent_dreams and clamped dream temperature to 0.2 despite the 0.8 role
profile. It now forwards those fields and allows the intended dream temperature.
Memory copying remains at temperature zero. Dream length guidance is separate from
the waking thought budget.

## Actual role probe — not a live-world run

Five disposable requests used the real HTTP gateway, schemas, role prompts and
completion validation. They covered time pressure, a missed call, an uncertain letter
memory, an uneasy dream and a quiet dream. No simulation events were committed.

| Existing worker | Contract result | Observed limitations |
| --- | --- | --- |
| Pi, qwen2.5:1.5b | 2/5 | Two incomplete responses, one unmarked dream; the valid waking output repeated uncertainty and the valid dream was only a tiny fragment. |
| Dell, qwen2.5:7b | 5/5 | Short, more coherent output; one dream still reused the supplied earlier dream's stairs/letter image. Contract success is not proof of naturalness. |

The five Dell requests took approximately 0.32–0.73 seconds each. Pi requests took
approximately 1.86–13.53 seconds on the completed five-case run. An earlier initial Pi
request also failed the complete-response check. This is a small comparison, not a
statistical model ranking or finished acceptance evaluation.

Pi power/throttle flags stayed 0x0 and sampled temperature reached 65.3 C. No service
restarts occurred. The Pi model was unloaded afterward (47.7 C at the post-test check),
and the two temporary Mac test tunnels were closed. The existing Dell-to-Pi service
tunnel and all live model routes were left alone.

`infra/raspberry-pi5/role_probe.py` reproduces the comparison through explicit local
test tunnels and monitors Pi health while waiting. It does not create those tunnels
or change routing itself. Recheck power first and unload the Pi model afterward.

Next: more seeds and ordinary situations, stronger checks for repetition and invented
actions, deliberate rehearsal versus passive exposure, and a calibrated path from an
occasionally salient thought to attention and only then a possible action.

Verification: 735 regression tests and 68 subtests passed (month soak excluded).
After the final fragment-warning and thought-to-planning expiry refinements, 73
focused lifecycle, planning, outreach, dream and semantic checks passed. Static
checks passed for the two new lifecycle changes. All changes remain local.
