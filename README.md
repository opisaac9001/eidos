# Eidos AI Agent

![Status](https://img.shields.io/badge/status-active-blue) 
![Version](https://img.shields.io/badge/version-0.7.0-yellow)  
*(Phase 6/7 – Initial UX complete, Phase 7 in progress)*

A sophisticated, **locally‑run** AI assistant with a lifelike, evolving persona (“**Pathos**”).
Eidos combines persistent memory, modular cognition and rich tool‑use to act as a privacy‑respecting, on‑device companion.

---

## Table of Contents

1. [Project Overview & Philosophy](#1-project-overview--philosophy)
2. [Key Features](#2-key-features)
3. [Tech Stack](#3-tech-stack)
4. [Project Structure](#4-project-structure)
5. [Setup & Installation](#5-setup--installation)
6. [Using the Agent](#6-using-the-agent)
7. [Configuration Deep‑Dive](#7-configuration-deep‑dive)
8. [Core Modules](#8-core-modules)
9. [Roadmap](#9-roadmap)
10. [Contributing](#10-contributing)
11. [License](#11-license)

---

## 1. Project Overview & Philosophy

|                  |                    |
| ---------------- | ------------------ |
| **Project Name** | **Eidos AI Agent** |
| **Eidos**      | *Pathos*           |

**Vision**

> Build a privacy‑first AI agent that feels alive, remembers, reasons, and grows alongside its user.

**Guiding Principles**

* **Persistent & evolving memory** – conversations, documents, dreams and world‑facts are embedded and stored locally.
* **Rich contextual awareness** – user, time, location, sensors & news shape every reply.
* **Modular cognition** – separate “souls” for memory (Ethos), reasoning/tools (Logos), conversation (Pathos) and subconscious dreaming (Oneiros).
* **Tool‑driven agency** – seamless use of web search, weather, math, vision, etc.
* **Local‑first** – everything can run on your own hardware; cloud services are optional.
* **Emergent, relatable behaviour** – mood, curiosity and reflection create a non‑static personality.

---

## 2. Key Features

* **Persona‑driven conversation** (Pathos) with mood simulation & Hexus disposition scores.
* **Persistent memory (EthosCore)**

  * Semantic search & RAG over SQLite memory.
  * Internal reflection cycles & self‑correction.
* **Sophisticated tool framework (LogosCore)** – web search, weather, Wolfram Alpha, PDF/RAG, vision, etc.
* **Oneiros “dream” cycle** – synthesises memories into textual insights (+ optional Stable Diffusion imagery) that fuel curiosity‑driven learning.
* **Daily briefing** – Markdown panel with local weather & top news.
* **Proactive behaviours** – greetings, follow‑ups, research proposals.
* **Web GUI** – chat, uploads, settings, logs (dreams / learning / knowledge upkeep).
* **Developer‑friendly API** – OpenAI‑compatible plus Eidos‑specific endpoints.

---

## 3. Tech Stack

| Layer                 | Technologies                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Backend**           | Python 3.11, FastAPI, Uvicorn                                                                                 |
| **LLM interaction**   | Local providers (LM Studio, Ollama) via OpenAI‑compatible APIs                                                |
| **Database**          | SQLite + SentenceTransformers embeddings                                                                      |
| **Frontend**          | HTML / CSS / Vanilla JS                                                                                       |
| **Key libs**          | `httpx`, `aiohttp`, `pydantic`, `python‑dotenv`, `spacy`, `PyPDF2`, `python‑docx`, `wolframalpha`, `tiktoken` |
| **Optional services** | Brave Search, TheNewsAPI, OpenWeatherMap, Wolfram Alpha, Stable Diffusion, Home Assistant, ElevenLabs TTS     |

---

## 4. Project Structure

```text
eidos_project/
├── .env.example            # Template for environment variables
├── .env                    # Local secrets (git‑ignored)
├── main.py                 # FastAPI entry‑point
├── requirements.txt
├── gui.html                # Web interface
├── Dockerfile.txt
├── persona/
│   └── pathos_directives.txt
├── eidos_memories/         # SQLite DB & Hexus state
├── wildcards/              # Oneiros prompt fragments
├── eidos_dream_images/
├── eidos_agent/
│   ├── core/               # Config, router, API models…
│   ├── modules/
│   │   ├── ethos_core/
│   │   ├── logos_core/
│   │   ├── pathos_interface.py
│   │   └── oneiros_module.py
│   ├── interfaces/         # TTS, vision, hardware I/O
│   ├── services/           # External API clients
│   └── utils/
└── logs/
```

---

## 5. Setup & Installation

### 5.1 Prerequisites

* Python **3.11+**
* Running local LLM endpoints (e.g. LM Studio, Ollama)
* (Optional) API keys for any external tools you enable
* `git`, `pip`, and preferably `virtualenv`

### 5.2 Clone & configure

```bash
git clone https://github.com/opisaac9001/eidos-project.git
cd eidos-project

cp .env.example .env      # populate with your values
```

Edit `.env` to point `LLM_PATHOS_URL`, `LLM_LOGOS_TECHNE_URL`, etc. at your local LLM servers and add any API keys.


### 5.3 Install dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

Or just use conda. Guys conda is so much better. Just use conda.

pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 5.4 Run

```bash
python main.py
```

The server listens by default on **[http://0.0.0.0:8088](http://0.0.0.0:8088)** and prints the GUI/API URLs.

---

## 6. Using the Agent

### 6.1 Web GUI

Open `gui.html`


**GUI capabilities**

* Chat with Pathos
* Upload documents / images
* Provide feedback
* Inspect dream journal, learning log, knowledge upkeep log
* Adjust per‑user settings

### 6.2 API Endpoints

*OpenAI compatible*

```
GET  /v1/models
POST /v1/chat/completions
```

*Eidos specific* (abridged)

```
GET  /v1/briefing
GET  /v1/weather
POST /v1/documents/upload
POST /v1/feedback
GET  /v1/agent/dreams
GET  /health
WS   /ws        # proactive pushes
```

See `main.py` for full schema.

---

## 7. Configuration Deep‑Dive

All primary settings live in `.env`.

### 7.1 LLM roles

Each role (PATHOS, LOGOS\_TECHNE, LOGOS\_VISION\_CONTEXT, LOGOS\_DEEP\_RESEARCH, ONEIROS\_DREAM) has:

```
*_URL      # endpoint
*_MODEL    # model ID (optional)
*_API_KEY  # e.g. "lm-studio", "ollama", or real key
*_TEMP     # sampling temperature
```

### 7.2 Service keys

```
BRAVE_SEARCH_API_KEY=...
NEWS_API_KEY=...
OPENWEATHERMAP_KEY=...
WOLFRAM_APP_ID=...
```

### 7.3 Feature flags

Toggle major subsystems:

```
ENABLE_WEB_SEARCH=True
NEWS_API_ENABLED=True
ONEIROS_ENABLE_IMAGE_DREAMS=False
...
```

---

## 8. Core Modules

| Module                | Role                                                |
| --------------------- | --------------------------------------------------- |
| **EthosCore**         | Long‑term memory, persona, mood, reflection         |
| **LogosCore**         | Tool execution, document parsing, fact verification |
| **PathosInterface**   | Prompt orchestration & conversation                 |
| **OneirosModule**     | Dream synthesis & curiosity triggers                |
| **MemoryStorage**     | SQLite + embedding DAO                              |
| **ConnectionManager** | WebSocket push notifications                        |

*Planned*: **AisthesisClient** for sensor / Home Assistant integration.

---

## 9. Roadmap

| Phase | Status         | Highlight                                        |
| ----- | -------------- | ------------------------------------------------ |
| 1‑5   | ✅ Complete     | Core architecture, memory, basic tools           |
| 6     | ✅ Complete     | GUI v1, reflection, knowledge‑upkeep             |
| **7** | 🔄 In progress | High‑quality TTS, richer UX, autonomous research |
| 8     | ⏭              | Persona/LLM split architecture                   |
| 9     | ⏭              | Home Assistant & vision sensors                  |
| 10    | ⏭              | Distributed satellite devices                    |
| 11    | ⏭              | Eidos‑Evolve v0.1 self‑improvement               |
| 12+   | ⏭              | Always‑listening ambient awareness               |

---

## 10. Contributing

Eidos is a personal passion project, but **issues, ideas and PRs are welcome**.

Focus areas:

* NLP & retrieval improvements
* New LogosCore tools
* EthosCore reflection heuristics
* Local TTS/STT integrations
* Hardware designs for satellite sensors

---

## 11. License

*To be decided* – MIT or Apache‑2.0 are likely.
A `LICENSE` file will be added before the first public release.

---

> © 2025 Isaac Lamb – Built with curiosity and a stack of GPUs.
