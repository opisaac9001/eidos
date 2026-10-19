# Security policy

Eidos keeps a simulated life, your conversations with him and your model provider keys on your machine, and can run continuously on a home server. We take reports seriously.

## Reporting a vulnerability

Please report privately, not in a public issue: use **Report a vulnerability** on the repository's [Security tab](https://github.com/opisaac9001/eidos/security/advisories/new). Include:

- what an attacker can do, and under which setup (the local web server, the operator view, a home-server deployment, model providers)
- steps or a proof of concept
- the version or commit

We'll acknowledge within a week, keep you informed, and credit you in the release notes unless you'd rather not be named.

## Scope

In scope: the engine and CLI, the web server and its API, the operator view and its token, the model gateway and how it stores and sends provider keys, and the deployment scripts under `infra/`.

Especially interesting:

- ways around the operator token, or reaching operator-only data from the ordinary view
- the server accepting requests from anywhere other than the local machine
- model provider keys leaking into the event log, exports, logs or the UI
- model output or feed content causing the app to take an action it shouldn't
- loss or corruption of a life's history

## Design notes

- The server binds to loopback only. Private resident state and model traces are hidden in the ordinary view but present in `/api/state`, so the server shouldn't be exposed to a network. For a home server, reach it over SSH or a private network.
- Model provider keys live in `~/.config/eidos/models.json` (or `EIDOS_MODELS_FILE`), outside the repository and the database.
- Feed and model content is always treated as data, never as instructions.

## Supported versions

Eidos is pre-1.0; fixes land on `main` and in the next release.
