# Second model group, and a focused 2B dream experiment

## Outcome

Gemma 4 31B is the strongest conversational candidate in this round's manual review.
Qwen 3.5 2B is a plausible inexpensive **dream** candidate, despite being unsuitable
for grounded conversation in these fixtures. No production promotion was made.

## Setup and scope

Downloaded Qwen 3.5 2B, Qwen 3.5 4B and Gemma 4 31B. All ran sequentially and fully
GPU-resident on the paused world's P40 worker at 8192 context. Native warm-up used
`think: false`; benchmark calls used `reasoning_effort: none`. Every response audit
had empty reasoning fields. Source catalogue: [Qwen](https://ollama.com/library/qwen3.5)
and [Gemma](https://ollama.com/library/gemma4).

| Candidate | Quantization | Reported model VRAM, decimal | Conversation median |
| --- | --- | ---: | ---: |
| Qwen 3.5 2B | Q8_0 | 2.47 GB | 1.16 s |
| Qwen 3.5 4B | Q4_K_M | 3.34 GB | 1.54 s |
| Gemma 4 31B | Q4_K_M | 20.27 GB | 3.82 s |

Observed conversation ranges were 0.56–2.59 s, 1.18–4.45 s and 2.41–15.60 s
respectively. First-request prefill and any revision are included; model warm-up
and UI pacing are excluded. These are single-run observations, not robust rankings.

Each candidate performed 24 cases: the previous 18 plus six checks for supported
calls, known car ownership, confident versus uncertain recollection, an empty-history
greeting and an unrelated music question. Unlike the previous comparison, each
candidate generated its own two waking thoughts rather than retaining the 7B control.
All 72 returned selected text; this is not a 72/72 quality pass.

## Conversational observations

- **2B:** invented a curry, called Pathos a middle name, added a cat to waking thought,
  and ignored the work deadline. Fast is not enough for grounded personal speech.
- **4B:** more concise, but invented a replacement car, embellished supplied memories,
  confused whose time limit mattered, and repeated the kettle theme in thoughts.
- **31B:** correctly handled name, age, disagreement, no-advice follow-up, supplied
  call/car facts, and the distinction between high and low recollection confidence.
  No-memory greeting was simply “Hey.” It still categorically denied unsupported
  events/ownership instead of distinguishing unknown from false. Not fully accepted.

31B examples:

- Name: “It's Patrick. Pathos is just a nickname from university.”
- Confident recollection: “I met Mara.”
- Uncertain recollection: “I'm not entirely sure. I think it might have been Mara,
  but I can't really say for certain.”
- Time pressure: “Not really, sorry. I've got to start work in a few minutes.”

The confidence fixtures test supplied subjective certainty, not hidden historical
accuracy. No hidden truth was passed to a performer. The prior Gemma 12B run did
not include all six new cases, so the preference for 31B remains provisional.

## Qwen 2B as Oneiros

The user's suggestion deserves a separate standard: dream invention is permitted.
A dream's new city, impossible object, or changed identity is not a waking-fact
failure. Evaluate imagery, variety, framing and lifecycle instead.

Eight focused cases covered a library walk, unfinished conversation, work pressure,
music/cooking, no memory seed and a missed train, plus two repetitions of the library
seed. With the usual full previous-dream text in context, every output copied or
closely paraphrased the same balcony/streetlights/car-door scene. Median 1.52 s.

A second eight-case run omitted full previous dreams, keeping the same seed sequence,
model, temperature and thinking-off setting. Imagery became visibly varied: an email
cursor and a screen dissolving into dust, a spreadsheet of red ink, independent
shadows in a kitchen, and a train platform dissolving into blue light. Repeated library
seeds also varied. Median 2.09 s. This suggests previous-output anchoring, not proof
of a universal cure; stochastic generation and a small sample limit the inference.

Example: “The cursor blinked like it was waiting for permission to continue, and my
fingers hovered over the send button while the screen faded into gray dust.”

Remaining concerns: outputs without history sometimes reached 120 words, well beyond
the preferred short fragment; generic grey/rain/coffee imagery and polished narration
remain common. All 16 passed output contracts, but those contracts do not enforce
the preferred length. Next test compact image/topic exclusions instead of past prose,
plus smaller dream output budgets. Do not globally remove the repetition guard yet.

The separate dream lifecycle regression suite passed 13 tests: dreams remain fiction,
recall is selective, forgetting is normal, and dream content does not grant action
authority. These tests used local fixtures; no generated dream entered Patrick's
actual memories. Nothing was run on the Pi, so GPU speed is not a Pi performance claim.

## Artifacts and final state

88 synthetic cases total. Full contexts, visible output, trace and reasoning audits:

- `data/evaluations/patrick-qwen35-2b-extended-20260908.json`
- `data/evaluations/patrick-qwen35-4b-extended-20260908.json`
- `data/evaluations/patrick-gemma4-31b-extended-20260908.json`
- `data/evaluations/patrick-qwen35-2b-dreams-20260908.json`
- `data/evaluations/patrick-qwen35-2b-dreams-no-history-20260908.json`

The extended probe now accepts a separate thought model/endpoint. The dedicated
`infra/dell-t630/probe_dream_candidate.py` supports the no-previous-prose control.
No application prompt or live route changed in this round. Any later deployment
of a thinking-capable model must explicitly preserve thinking-off in the route.

Original Qwen 2.5 14B world-worker cache restored with persistent keep-alive; test
tunnel closed, UI tunnel retained. Live revision 4108 and simulation time
2026-01-07T23:12:27.335054+00:00 unchanged, paused, no runtime error. Route SHA256
unchanged: `1a10653e996ed18dec2c071e954680eb2e5ae30d67c659926327c699a6c97cac`.
Downloaded weights retained for future trials; storage has approximately 538 GB free.
