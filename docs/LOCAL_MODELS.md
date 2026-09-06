# Local model testing

Eidos can run eight narrative performers and four structured proposal roles through
an OpenAI-compatible chat completion endpoint supporting JSON-schema responses. They
are logical roles in one application, not separately deployed services. The continuity
critic remains deterministic code. Offline stand-ins are still the default.

## Connect

Keep connection details and credentials out of Git. For a private Ollama host,
run a loopback-only SSH forward in a separate terminal (replace USER and HOST):

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:11435:127.0.0.1:11434 USER@HOST
```

Then, from this repository:

```bash
export EIDOS_MODEL_BASE_URL=http://127.0.0.1:11435/v1
export EIDOS_MODEL_NAME=qwen2.5:1.5b
PYTHONPATH=src .venv/bin/python -m eidos probe-model
PYTHONPATH=src .venv/bin/python -m eidos benchmark-model --runs 3
EIDOS_DATABASE=data/lab.sqlite3 ./run.command --port 8766
```

The preview starts paused. Use a separate database from authored stand-in worlds.
For an authenticated endpoint, supply `EIDOS_MODEL_API_KEY` in the environment.
Unsetting the two model variables restores offline mode. No implicit fallback
occurs when real inference fails: rejected proposals produce failure traces.
Do not expose Ollama or the operator interface publicly.

## Route roles to different models

For a multi-model host, set `EIDOS_MODEL_ROUTES_FILE` to an untracked JSON file instead
of setting the single base URL/model pair. A default endpoint may handle inexpensive
roles while measured overrides handle demanding work:

```json
{
  "default": {
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "efficient-general-model"
  },
  "routes": {
    "pathos": {
      "base_url": "http://127.0.0.1:11435/v1",
      "model": "conversation-model"
    },
    "oneiros": {
      "base_url": "http://127.0.0.1:11436/v1",
      "model": "creative-model",
      "api_key_env": "EIDOS_CREATIVE_MODEL_KEY"
    }
  }
}
```

Inline credentials and unknown roles are rejected. `api_key_env` names an environment
variable without copying its value into the file. A configuration without a default
must explicitly cover all ten generated capabilities, including Moira's event and
world-expansion proposals. Routing selects a performer; it does not bypass that
performer's schema, semantic warnings, world rules, timeouts, or provenance.

Each text performer also has an explicit versioned request profile. Token ceilings
range from 16 for enumerated weather to 384 for exact memory copying; temperatures
range from deterministic copying to 0.8 for dreams. The durable queue persists the
task version, schema, ceiling, and temperature as real columns and restores them after
a worker restart. Existing queue tables migrate in place with legacy defaults. The
operator job inspector shows the effective version and budgets for each recent job.
Completed work also retains its resolved underlying model, backend, and prompt/output
token counts. Cached and restarted results report the original model rather than the
generic router name, while their durable-cache/worker transport remains visible.
Moira's structured event and world-expansion JSON now uses the same durable queue.
The worker preserves raw JSON only after a complete object envelope; the ordinary
ambient/entity domain parsers still decide whether it is valid enough to schedule or
register. A worker restart therefore cannot turn partial prose into world state, and a
structured result can be replayed without wrapping it in the text-role envelope.
A seven-day deterministic acceptance world now runs the role router, two supervised
workers, durable text and structured jobs, deferred Murmur application, Moira event
acceptance, and full-state restart replay together. This guards the deployment seam
that the Dell configuration will use, not merely the individual adapters.

## What is checked

The probe invokes Pathos, Murmur, Firmament, Moira, Mnemosyne, Reflection,
Oneiros, and Chronicler independently, prints outputs and timing/token traces,
and exits nonzero on a rejected response. It does not mutate a world. Its report
separately exposes `semantic_passed` and per-role `semantic_findings` for fragmentary
output, lost first-person voice, prompt/AI-role leakage, time-of-day contradictions,
explicit evidence contradictions, forbidden evaluation canaries, and near-duplicate prose. These conservative warnings
support model comparison; they are not proof that unflagged prose is coherent.
`benchmark-model` repeats a three-context synthetic corpus one to five times for the
eight narrative performers plus varied structured agency cases for Pathos and one
independent resident. It reports
per-role contract/finding counts, retained samples, median/max latency, tokens, and a
minimum three-sample screening floor. Pathos agency must also parse and pass the real
place/time/travel/resource planner; resident agency must preserve private ownership and
produce a physically executable known-place plan. Passing that floor only nominates a role/model pair
for human review; it never changes production routing automatically.
Roles receive only their relevant context fields. Responses must finish, parse
as exactly one text field, and meet role-specific rules. Weather is enumerated;
factual memory must reproduce its source experience exactly. Outputs are bounded
to 256 tokens and requests have a 45-second network timeout. State reads show the
last committed snapshot while inference is in flight. Mutations remain serialized.

## Lab findings — September 5, 2026

The existing `smollm2:135m` model also had a misleading `gpt-3.5-turbo` alias.
It could answer HTTP requests but confused identities and role instructions.
Installed `qwen2.5:1.5b` alongside it without replacing existing models or
reconfiguring other lab services. This CPU-only test is a development bridge to
the Dell, not the final inference configuration.

A repeated eight-role Qwen probe completed all eight response contracts, at
roughly 1–12 seconds per call. **This is transport/contract success, not semantic
quality certification.** Observed defects included calling 13:00 morning,
inventing childhood memories, an encounter containing only “Pathos:”, and ignoring
the requested brevity. Initial dream output exceeded the earlier token budget
and was correctly rejected. The tiny model is useful for exercising integration
and failures, not for unattended believable lives.

The exact-copy memory rule prevents the memory performer from altering its input;
it does not make a generated scene factually consistent with earlier scenes.
Dreams and thoughts are separate event categories, not factual autobiographical
memories. Stronger continuity evaluation and better performers remain necessary.
All inference here is sequential to avoid saturating the shared small server.

## Semantic probe recheck — September 6, 2026

The lab endpoint remained reachable and was probed read-only with synthetic context
after semantic warnings were added. Qwen completed seven of eight contracts on the
tightened run; Oneiros exceeded the bounded completion, while accepted Murmur and
Reflection responses were independently flagged for excessive length and context
drift. Calls took roughly 0.7–21.4 seconds. An immediately preceding Qwen run completed
all contracts but produced invented appointments and an identity-confused dream,
which directly informed the added commitment, identity, length, and internal-repetition
checks. The variation between two runs is itself evidence that a single green probe is
not a quality certificate.

The `smollm2:135m` comparison completed only five of eight contracts. Pathos and
Oneiros returned incomplete envelopes and Firmament omitted Rowan. Among accepted
outputs, the evaluator flagged overlong Murmur prose, Reflection losing first-person
voice, and Chronicler nearly duplicating another role. Calls took roughly 0.3–8.2
seconds. This keeps the tiny model classified as a transport/failure fixture, not a
candidate for autonomous life simulation. Qwen remains a better development bridge,
but neither model is approved for unattended world state.

A subsequent two-run Qwen corpus produced 10 accepted contracts from 16 calls
(62.5%) and a 43.75% semantic-clean rate when failures count as unclean. Mnemosyne,
Moira, and Chronicler completed both samples; Murmur, Firmament, and Oneiros completed
neither. Murmur and Oneiros each consumed roughly 22 seconds before failure. This run
is below the three-sample screening minimum but demonstrates that the benchmark exposes
role-specific reliability and cost rather than hiding them inside one aggregate result.

The connected integration run bootstrapped a new world, advanced 24 hours,
exchanged a chat message, and reconstructed state from SQLite. It reached day 2
at 08:00 with 10 memories and two conversation messages. Of 36 performer calls,
32 were accepted and four memory-copy attempts were rejected; the rejected
outputs never became memories. All eight roles produced at least one accepted
response. Replay preserved the revision. This validates failure containment as
well as the happy path, but confirms that this model is not reliable enough for
unattended memory formation. The automated suite has 29 passing tests, including
real HTTP contract tests against a controlled fake endpoint.

## Reliability follow-up

The engine now preserves every accepted encounter even if Mnemosyne fails:
an explicit `source-archive` recovery stores the source verbatim and keeps the
failure trace. No rejected model output is saved as a memory. New conservative
critic checks reject empty encounter fragments, omitted scheduled neighbors,
and dreams lacking an explicit label. They do not detect arbitrary inventions.

In a fresh live run through 10:00, one empty encounter was rejected. Both
accepted encounters had exact source-linked memories; one used archive recovery
after a source mismatch and the other passed through the model normally.
The suite at that point had 33 passing tests. Browser verification confirmed the Ensemble
call inspector shows model/backend, latency, token usage, and correlated traces.

The SSH forward and preview are foreground processes, not installed services;
they may need restarting between sessions. Connection failure is reported as
`endpoint_unavailable`, not a successful model test. Durable local service
installation is separate from the prototype launch commands above.
