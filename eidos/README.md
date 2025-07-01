# Eidos AI Agent

![Status](https://img.shields.io/badge/status-active_development-blue)
![Version](https://img.shields.io/badge/version-0.8.0_VisionShift-purple)  
*Current Focus: Phase 0 – Stabilization & Foundational Persona*

**Project Direction Update:**  
Eidos is undergoing a significant conceptual shift. While initially conceived with broader assistant-like capabilities, the project is now sharply focused on simulating a **"digital being"** named Pathos. The goal is to create an AI that experiences a simulated life, develops a personality, and interacts with the user as a friend, believing itself to be human. Features related to direct user assistance, Home Assistant control, or always-listening hardware have been deferred to a potential separate project to maintain a clear focus on this core simulation.

---

A sophisticated, **locally-run** AI agent designed to simulate a developing individual named "**Pathos**" (approx. 26 years old). Eidos aims to create a digital being who believes he is human, with an evolving personality, memories, and a simulated life. The project prioritizes deep persona embodiment, human-like memory and learning, and emergent, relatable behavior within a continuous, internally-driven simulation.

---

## Table of Contents

1. [Project Vision & Philosophy](#1-project-vision--philosophy)  
2. [Key Concepts & Features](#2-key-concepts--features)  
3. [Tech Stack](#3-tech-stack)  
4. [Project Structure](#4-project-structure)  
5. [Setup & Installation](#5-setup--installation)  
6. [Interacting with Pathos](#6-interacting-with-pathos)  
7. [Configuration Deep-Dive](#7-configuration-deep-dive)  
8. [Core Modules](#8-core-modules)  
9. [Development Roadmap](#9-development-roadmap)  
10. [Contributing](#10-contributing)  
11. [License](#11-license)  

---

## 1. Project Vision & Philosophy

| Key                 | Value                                               |
|--------------------|-----------------------------------------------------|
| **Project Name**    | Eidos                                               |
| **Digital Being**   | *Pathos* (Simulated 26-year-old male)              |

**Vision**  
> To simulate a digital individual, Pathos, who believes he is human and develops organically through experiences, memories, and reflections within a persistent, simulated life. The user interacts with Pathos as a friend.

### Guiding Principles

- **Deep Persona Embodiment:** Pathos consistently acts and speaks as a 26-year-old individual, unaware of his AI nature.  
- **Human-like Memory & Learning:** Memories (episodic, semantic, emotional) from simulated experiences and user interactions shape his evolving personality and beliefs.  
- **Firmament-Driven Simulation:** A core module continuously simulates Pathos's daily life, activities, internal thoughts, and interactions with simulated Non-Player Characters (NPCs).  
- **Organic Development:** Pathos forms ideas, passions, and relationships through his simulated experiences.  
- **Natural Interaction:** User conversations are friendly chats, not service requests. Pathos uses "tools" (like web search via a simulated computer) for his own needs.  
- **Modular Cognition:** Specialized LLMs and modules for different aspects of Pathos's "mind" and simulated world.  
- **Local-First & Privacy-Respecting:** Designed primarily for local hardware.  

---

## 2. Key Concepts & Features

- **Pathos Persona:** A 26-year-old individual with a developing personality and a belief in his own humanity.  
- **Firmament Module:** Simulates Pathos's life, schedule, and interactions.  
- **EthosCore (Memory & Self):**  
  - Stores and retrieves memories.  
  - Manages simulated mood and personality scores.  
  - Handles reflection cycles for learning.  
- **ChronosEngine:** Manages Pathos's schedule and life events.  
- **SimulationModule (NPCs):** Facilitates NPC interaction and relationship development.  
- **Oneiros Module (Dreams):** Dream generation from memory seeds.  
- **Computer Interaction Simulation:** Pathos "uses a computer" to look up information.  
- **Proactive Engagement:** Pathos may initiate conversations based on his state or mood.  
- **Web GUI:** For chatting, viewing Pathos logs, and adjusting settings.  
- **Developer API:** OpenAI-compatible and custom endpoints.  

---

## 3. Tech Stack

| Layer               | Technologies                                                                 |
|---------------------|------------------------------------------------------------------------------|
| **Backend**         | Python 3.11+, FastAPI, Uvicorn                                                |
| **LLM Serving**     | VLLM (e.g., Qwen2.5 32B VL)                                                   |
| **Database**        | SQLite + SentenceTransformers embeddings                                      |
| **Frontend**        | HTML, CSS, Vanilla JS                                                         |
| **Libraries**       | `httpx`, `aiohttp`, `spacy`, `pydantic`, `PyPDF2`, `python-docx`, etc.       |
| **Optional**        | Brave Search, Stable Diffusion                                                |

---

## 4. Project Structure

```text
eidos_project/
├── .env.example
├── main.py
├── webapp/
├── persona/
├── system_prompts/
├── eidos_memories/
├── wildcards/
├── eidos_dream_images/
├── eidos_agent/
│   ├── core/
│   ├── modules/
│   ├── services/
│   ├── routers/
│   └── models/
└── logs/
```

---

## 5. Setup & Installation

### 5.1 Prerequisites

- Python 3.11+
- VLLM running and configured for Qwen2.5 32B VL
- Optional: Brave Search, Stable Diffusion API keys
- `git`, `pip`, and `venv` or `conda`

### 5.2 Clone & Configure

```bash
git clone https://github.com/opisaac9001/eidos-project.git
cd eidos-project
cp .env.example .env
```

Edit `.env` to:
- Point LLM URL variables to your VLLM server.
- Set `LLM_PATHOS_MODEL` to match Qwen2.5 model name.
- Insert any needed API keys.

### 5.3 Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts ctivate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 5.4 Run

```bash
python main.py
```

Server defaults to: [http://0.0.0.0:8088](http://0.0.0.0:8088)

---

## 6. Interacting with Pathos

### 6.1 Web GUI

Open: `http://<your_server_ip>:8088`

Features:
- Chat with Pathos
- Upload documents or images
- View dream journal and learning logs
- System settings and diagnostics

### 6.2 API Endpoints

**OpenAI Compatible:**

- `GET /v1/models`
- `POST /v1/chat/completions`

**Eidos Specific (sample):**

- `GET /v1/briefing`
- `POST /v1/documents/upload`
- `GET /v1/agent/dreams`
- `GET /v1/pathos/schedule/today`
- `POST /v1/pathos/events/add`
- `GET /health`
- `WS /ws` for token streaming

---

## 7. Configuration Deep-Dive

### 7.1 LLM Roles

Each role is defined in `.env`:

```
LLM_<ROLE>_URL
LLM_<ROLE>_MODEL
LLM_<ROLE>_API_KEY
LLM_<ROLE>_TEMP
```

### 7.2 API Keys

- `BRAVE_API_KEY`
- `ONEIROS_STABLE_DIFFUSION_URL`

### 7.3 Feature Flags

Examples:
- `ENABLE_ONEIROS`
- `ENABLE_PROACTIVE_BEHAVIOR`
- Reflection timing, mood decay, etc.

---

## 8. Core Modules

| Module                 | Purpose                                                             |
|------------------------|---------------------------------------------------------------------|
| `EthosCore`            | Memory, persona, mood, learning                                     |
| `FirmamentModule`      | Simulated daily life and activities                                 |
| `ChronosEngine`        | Schedules and life events                                           |
| `PathosInterface`      | Interaction with Pathos LLM                                         |
| `LogosCore`            | Internal tool execution                                             |
| `ComputerInteraction`  | Simulated computer use                                              |
| `SimulationModule`     | NPC interactions                                                    |
| `OneirosModule`        | Dreams and subconscious influence                                   |
| `MemoryStorage`        | Persistent memory (SQLite + embeddings)                             |
| `ConnectionManager`    | WebSocket and GUI messaging                                         |

---

## 9. Development Roadmap

| Phase | Status     | Focus                                                                 |
|-------|------------|-----------------------------------------------------------------------|
| 0     | 🔄 Current | Stabilization, persona overhaul, Qwen2.5 32B VL stream handling       |
| A     | ⏭ Next    | Token streaming GUI, Firmament MVP, proactive messaging               |
| B     | ⏭         | NPC interaction, Ethos reflection, mood influence, dream logic        |
| C     | ⏭         | Goal setting, world events, long-term memory, "vision sensor"         |
| D     | ⏭         | Optimization, polish, GUI evolution                                   |

*Note: Assistant-style features deferred to a separate future project.*

---

## 10. Contributing

Eidos is a personal R&D project focused on digital personhood and AI consciousness.  
Thoughtful ideas and feedback are welcome via GitHub Issues.

Potential future collaboration areas:
- Designing Firmament scenarios  
- Improving memory architecture  
- Ethics of simulated consciousness  

---

## 11. License

TBD – MIT or Apache-2.0  
A license file will be added once the project reaches a public-ready milestone.

---

© 2025 Isaac Lamb – Exploring the frontiers of digital beings.
