# Running Patrick on real models

Out of the box, Eidos runs offline on written stand-ins (templates). They are enough to
watch the simulation work, but Patrick only really comes alive on a language model. You
can use local models (Ollama, LM Studio, vLLM), paid services (OpenRouter, OpenAI,
Anthropic, Gemini, Groq, Mistral, DeepSeek, Together), or a mix, with backups and a daily
budget.

## The quick way: the Models page

1. Start the server with `eidos serve`, and open the `/operator?token=…` link it prints.
2. Go to **Models**.
3. **Add a provider.** Choose its kind; the address is filled in for you, so change it
   only for a server somewhere else. For a paid service, paste your API key, or name an
   environment variable that holds it.
4. **Add a model.** Pick the provider, click **List this provider's models**, and choose
   one. For OpenRouter, prices fill in automatically. Give it a short name.
5. Click **Test** on the model. It sends one small real request and checks the answer
   comes back as valid structured JSON.
6. **Assign roles.** The first model you add becomes the default for everything. You can
   give each part of his life its own first choice and backup:

   | Group | Roles |
   |---|---|
   | His voice | conversation, and messages he sends you |
   | His inner life | passing thoughts, reflection, dreams, selfhood questions, deliberation, the daybook |
   | Narrating his life | re-telling the rule-written moments of his life in his own words |
   | His choices and what he learns | plans, projects, notes about you, reading your advice, his take on the news |
   | The world | weather, town events, townsfolk, residents' plans and histories |

7. **Set a daily budget** for paid services (dollars and/or calls), then **Save**.

Changes apply from his next thought. You don't need to restart, and a world that was
running offline switches over as soon as a model is saved.

## What happens when a model fails

For each role, Eidos tries the first-choice model, then its backup, then the group's and
the default's. A model is skipped if it:
- is unreachable;
- returns an error (after retrying rate limits and outages);
- answers with something that fails validation;
- is a paid model and today's budget is spent.

Local models are never stopped by the budget. If every model fails, that one step of his
life is skipped and the failure is visible in the operator's model-call trace. Nothing is
invented to fill the gap.

## The settings file

Everything on the Models page lives in one JSON file:
- by default `~/.config/eidos/models.json`;
- or wherever `EIDOS_MODELS_FILE` points.

It sits outside the repository and outside the world database, and is written readable only
by you, because it can hold API keys. Keys are never sent back to the page. Today's usage
is kept beside it in `usage.json`. You can edit the file by hand:

```json
{
  "providers": {
    "dell": {"kind": "ollama", "base_url": "http://127.0.0.1:11435/v1"},
    "openrouter": {"kind": "openrouter", "api_key_env": "OPENROUTER_API_KEY"}
  },
  "models": {
    "qwen14": {"provider": "dell", "model": "qwen2.5:14b"},
    "sonnet": {
      "provider": "openrouter",
      "model": "anthropic/claude-sonnet-4.5",
      "price_in": 3.0,
      "price_out": 15.0
    },
    "thinker": {
      "provider": "openrouter",
      "model": "deepseek/deepseek-r1",
      "max_tokens": 4000
    }
  },
  "roles": {
    "default": ["qwen14"],
    "voice": ["sonnet", "qwen14"],
    "pathos_news_take": ["sonnet", "qwen14"]
  },
  "budget": {"daily_usd": 2.0, "daily_requests": 2000}
}
```

- **`providers`:**
  - `kind` is one of `ollama`, `lmstudio`, `vllm`, `openrouter`, `openai`, `anthropic`,
    `gemini`, `groq`, `mistral`, `deepseek`, `together`, `custom`.
  - `base_url` is optional for known kinds and required for `custom`.
  - Give a key either as `api_key` or as `api_key_env` (an environment variable name).
  - `structured` is optional and overrides how JSON is requested: `json_schema`,
    `json_object`, `prompt` or `auto`.
  - `timeout` is in seconds.
- **`models`:**
  - `model` is the provider's own model name.
  - `max_tokens` raises the output ceiling; thinking models need it because their
    reasoning counts.
  - `price_in` and `price_out` are dollars per million tokens, used for the budget.
  - `reasoning_effort` is optional.
- **`roles`:** keys are a role name (e.g. `pathos`, `oneiros`), a group name (`voice`,
  `inner`, `narration`, `life`, `world`) or `default`. A role's own entry wins over its
  group's, and a group's over the default. Each value is a list of models to try in order.
- **`budget`:** `daily_usd` counts priced models only. `daily_requests` counts every call to
  a paid (non-local) provider.

## From the command line

```bash
eidos models status          # what's configured, which model each role will use, today's usage
eidos models test            # one small real request to each model
eidos models test qwen14     # ...or just one
eidos models remote openrouter   # list a provider's models (with prices where published)
eidos probe-model            # run every role once against your setup
```

The older ways still work: `EIDOS_MODEL_BASE_URL` with `EIDOS_MODEL_NAME` for a single
endpoint, and `EIDOS_MODEL_ROUTES_FILE` for a routing file (see
[LOCAL_MODELS.md](LOCAL_MODELS.md)). If either is set, it takes precedence over the settings
file.

## Provider notes

- **Structured output:** providers differ. Eidos asks for strict JSON schema first where a
  provider supports it. On `auto` it steps down to JSON mode, then to a prompt-only
  request whose JSON it extracts from the reply, the first time a provider refuses. The
  answer is always validated.
- **Rate limits and outages:** these are retried up to twice with backoff, honouring
  `Retry-After`.
- **Anthropic** is used through its OpenAI-compatible endpoint, with JSON requested in the
  prompt.
- **Gemini** uses Google's OpenAI-compatible endpoint.
- **OpenRouter** gets an identifying `HTTP-Referer` and `X-Title` header, as it asks.
- **Model size:**
  - Smaller local models (around 7B and below) are fine for his inner monologue and much
    of the world.
  - Conversation and the structured roles do noticeably better at 14B and up, or on a
    strong hosted model.
  - A 1.5B model is too small for his thoughts.

## Choosing where to spend

A sensible mix:
- **A strong model for his voice,** local or paid, since that's what you talk to.
- **A capable local model for his choices, what he learns, and the world.**
- **A small, fast local model for his inner life,** which is frequent and cheap.

Re-telling his life (narration) is up to four short calls an hour when something happens;
point it at a local model if cost matters.

## Security

- Keys live only in the settings file (permissions `600`) or in your environment, never in
  the world database, exports or backups.
- The Models page needs the operator token, and the server only listens on this machine.
- Provider error messages are shown with anything that looks like a key removed.
