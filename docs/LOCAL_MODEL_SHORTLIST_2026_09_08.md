# Local models for Patrick: research shortlist, not a winner

Update: all three server candidates have now been downloaded and tested with
thinking disabled. See [MODEL_TRIAL_2026_09_08.md](MODEL_TRIAL_2026_09_08.md).
The follow-up tests Qwen 2B/4B, Gemma 31B and a separate 2B dream experiment:
[second-group results](MODEL_TRIAL_SMALL_AND_LARGE_2026_09_08.md).
The paired-P40 trial compares Gemma 31B and Qwen 35B while retaining the independent
3060 worker: [dual-GPU results](DUAL_P40_TRIAL_2026_09_08.md).

Checked September 8, 2026 against publisher model cards and Ollama's model catalogue.
Live hardware check: two 24 GiB Tesla P40s and one 12 GiB RTX 3060. Existing loaded
workers consume roughly 10 GiB on each P40 and 5 GiB on the 3060. New candidates
must not simply be loaded alongside all existing workers without a memory budget.

## Shortlist

| Candidate | Listed download size | First intended test |
| --- | ---: | --- |
| Ministral 3 14B Instruct | 9.1 GB | Patrick conversation and grounded personal decisions |
| Gemma 4 12B instruction-tuned | 7.6 GB | Independent conversation comparison; naturalness and continuity |
| Qwen 3.5 27B | 17 GB | Larger candidate for conversation and world planning |
| Qwen 3.5 4B / 2B | 3.4 / 2.7 GB | Cheap waking fragments; 2B first for a future Pi trial |

Sizes are model downloads, NOT total runtime VRAM/RAM requirements. Context cache,
runtime buffers and any vision components need extra space. Single-P40 feasibility
for 27B is an estimate at modest context, not measured compatibility or throughput.
Start with a bounded 4–8K context and inspect actual placement, latency and memory.
Do not mistake a huge advertised context window for a configuration this machine
should run. System RAM is not GPU VRAM.

Sources:

- [Ministral catalogue](https://ollama.com/library/ministral-3) lists sizes and
  structured-output capabilities; [publisher GGUF release](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF)
  supplies official quantizations. First practical challenger, not a proven voice winner.
- [Gemma 4 catalogue](https://ollama.com/library/gemma4) lists the 12B option and
  native system-prompt support; [Google's 12B instruction model card](https://huggingface.co/google/gemma-4-12B-it)
  is the primary model reference. A distinct family gives a useful independent comparison.
- [Qwen 3.5 catalogue](https://ollama.com/library/qwen3.5) lists sizes;
  [Qwen's 27B card](https://huggingface.co/Qwen/Qwen3.5-27B) documents thinking and
  non-thinking operation. Test non-thinking conversational output with the actual
  backend's supported switch; do not blindly assume one vendor's parameter works
  everywhere. A hidden reasoning budget is not the simulated stream of consciousness.
- [Qwen's 4B card](https://huggingface.co/Qwen/Qwen3.5-4B) supplies the smaller model
  reference. Small size alone does not prove good fragments, JSON, or Pi thermals.
- [Ollama hardware support](https://docs.ollama.com/gpu) lists Tesla P40 support.
  General GPU support is not proof that every new architecture works efficiently
  on this exact installed runner. Verify before touching production routes.

These are my test priorities based on available artifacts, size and architectural
variety, not a claim that coding/reasoning benchmark rankings measure believable
human conversation. The research phase did not change production routes;
subsequent isolated downloads and tests are recorded in the trial report.

## Acceptance battery

Use the same fixture set and actual output contracts across models. Repeat each
case and vary neutral everyday context; include an empty-history condition. Score:

1. No invented personal history from leading questions; uncertainty is not denial.
2. Explicit mistaken recollections retain their supplied felt confidence.
3. Accurate age, relevant answers, no compulsive context recaps.
4. Multi-turn continuity, no-advice requests, disagreement and genuine time limits.
5. Thought/dream variation without compulsory profundity or invented waking action.
6. JSON success, truncation, median/tail latency, memory use and worker contention.

Keep raw outputs and manually review failures even when the automatic critic says
clean. Select per role; do not assume the best conversational model is the best
background-fragment model. Pi testing remains gated on adequate power and health.
