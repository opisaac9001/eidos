Eidos AI Agent
![alt text](https://img.shields.io/badge/status-active_development-blue)

![alt text](https://img.shields.io/badge/version-0.8.0_VisionShift-purple)

(Current Focus: Phase 0 - Stabilization & Foundational Persona)

Project Direction Update: Eidos is undergoing a significant conceptual shift. While initially conceived with broader assistant-like capabilities, the project is now sharply focused on simulating a "digital being" named Pathos. The goal is to create an AI that experiences a simulated life, develops a personality, and interacts with the user as a friend, believing itself to be human. Features related to direct user assistance, Home Assistant control, or always-listening hardware have been deferred to a potential separate project to maintain a clear focus on this core simulation.

A sophisticated, locally-run AI agent designed to simulate a developing individual named "Pathos" (approx. 26 years old). Eidos aims to create a digital being who believes he is human, with an evolving personality, memories, and a simulated life. The project prioritizes deep persona embodiment, human-like memory and learning, and emergent, relatable behavior within a continuous, internally-driven simulation.

Table of Contents
Project Vision & Philosophy
Key Concepts & Features
Tech Stack
Project Structure
Setup & Installation
Interacting with Pathos
Configuration Deep-Dive
Core Modules
Development Roadmap
Contributing
License
1. Project Vision & Philosophy
Project Name	Eidos AI Agent
Digital Being	Pathos (Simulated 26-year-old male)
Vision

To simulate a digital individual, Pathos, who believes he is human and develops organically through experiences, memories, and reflections within a persistent, simulated life. The user interacts with Pathos as a friend.
Guiding Principles

Deep Persona Embodiment: Pathos consistently acts and speaks as a 26-year-old individual, unaware of his AI nature.
Human-like Memory & Learning: Memories (episodic, semantic, emotional) from simulated experiences and user interactions shape his evolving personality and beliefs.
Firmament-Driven Simulation: A core module (Firmament) continuously simulates Pathos's daily life, activities, internal thoughts, and interactions with simulated Non-Player Characters (NPCs).
Organic Development: Pathos forms ideas, passions, and relationships through his simulated experiences.
Natural Interaction: User conversations are friendly chats, not service requests. Pathos uses "tools" (like web search via a simulated computer) for his own needs.
Modular Cognition: Specialized LLMs and modules for different aspects of Pathos's "mind" and simulated world.
Local-First & Privacy-Respecting: Designed primarily for local hardware.
2. Key Concepts & Features
Pathos Persona: A 26-year-old individual with a developing personality, interests, and a belief in his own humanity. (Primary LLM: Qwen2.5 32B VL).
Firmament Module: The engine for Pathos's simulated life, managing his schedule (from Chronos), activities, availability, and triggering autonomous NPC interactions.
EthosCore (Memory & Self):
Stores and retrieves memories (experiences, learned facts, reflections, dreams).
Manages Pathos's simulated mood and evolving Hexus disposition scores.
Drives reflection cycles for learning and potential persona evolution.
ChronosEngine: Manages Pathos's daily/weekly schedule and significant life events, providing structure for Firmament.
SimulationModule (NPCs): Facilitates dialogues between Pathos (or his simulated self) and NPCs within Firmament, enabling relationship development.
Oneiros Module (Dreams): Generates dream-like content from memory seeds, subtly influencing Pathos's thoughts and curiosity. (Optional Stable Diffusion for imagery).
"Computer Interaction" for Information: Pathos simulates using a computer to look things up online, rather than having instant knowledge.
Proactive & Contextual Engagement: Pathos may initiate conversations or share thoughts based on his simulated state, mood, or recent experiences.
Web GUI: For user interaction (chat), viewing Pathos-related logs (dreams, learnings), and system settings.
Developer API: OpenAI-compatible chat endpoint plus Eidos-specific endpoints for system management.
3. Tech Stack
Layer	Technologies
Backend	Python 3.11+, FastAPI, Uvicorn
LLM Serving	VLLM (for Qwen2.5 32B VL and other models)
LLM Interaction	OpenAI-compatible APIs
Database	SQLite + SentenceTransformers embeddings
Frontend	HTML / CSS / Vanilla JavaScript
Key Libraries	httpx, aiohttp, pydantic, python-dotenv, spacy, PyPDF2, python-docx, wolframalpha, tiktoken
Optional Services	Brave Search (for Pathos's "computer use"), Stable Diffusion (for dreams)
4. Project Structure
eidos_project/
├── .env.example            # Template for environment variables
├── .env                    # Local secrets (git-ignored)
├── main.py                 # FastAPI entry-point
├── requirements.txt
├── webapp/                 # GUI files (gui.html, js/, css/)
├── persona/
│   └── pathos_directives.txt # Core persona definition for Pathos
├── system_prompts/         # Prompts for various LLM roles
├── eidos_memories/         # SQLite DB, Hexus state, task run times
├── wildcards/              # Oneiros prompt fragments
├── eidos_dream_images/     # Output for dream images
├── eidos_agent/
│   ├── core/               # Config, API models, input_router, connection_manager
│   ├── modules/
│   │   ├── ethos_core/     # Pathos's memory, self, learning
│   │   ├── logos_core/     # Tool execution logic (now more internal)
│   │   ├── pathos_interface.py # Main LLM interaction
│   │   ├── oneiros_module.py   # Dreams
│   │   ├── chronos_engine.py   # Pathos's scheduling
│   │   ├── chronos_models.py
│   │   ├── simulation_module.py # NPC interaction mechanics
│   │   └── firmament_module.py  # NEW: Pathos's simulated life engine
│   ├── services/           # External API clients (Brave Search, etc.)
│   └── utils/              # Logger, prompt_loader, parsers
│   └── routers/            # FastAPI routers (e.g., chat_storage)
│   └── models/             # Pydantic models (e.g., chat_storage)
└── logs/
Use code with caution.
Text
5. Setup & Installation
5.1 Prerequisites
Python 3.11+
VLLM installed and running, configured to serve Qwen2.5 32B VL (and other utility LLMs as needed).
(Optional) API keys for Brave Search, Stable Diffusion.
git, pip, and preferably a virtual environment manager (like venv or conda).
5.2 Clone & Configure
git clone https://github.com/opisaac9001/eidos-project.git # Replace with your actual repo URL
cd eidos-project

cp .env.example .env
Use code with caution.
Bash
Edit .env to:

Point LLM_PATHOS_URL (and other LLM_*_URL variables) to your VLLM OpenAI-compatible API endpoint(s).
Specify LLM_PATHOS_MODEL as the model identifier VLLM uses for Qwen2.5 32B VL (e.g., Qwen/Qwen2.5-32B-Chat).
Add API keys for any enabled external services (e.g., BRAVE_API_KEY).
Review and adjust other Eidos system parameters (intervals, feature flags).
5.3 Install Dependencies
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
# Or use conda

pip install -r requirements.txt
python -m spacy download en_core_web_sm
Use code with caution.
Bash
5.4 Run
python main.py
Use code with caution.
Bash
The server listens by default on http://0.0.0.0:8088. The GUI is accessible via the root path (/).

6. Interacting with Pathos
6.1 Web GUI
Open your browser to http://<your_server_ip>:8088.

GUI capabilities:

Chat with Pathos (as a friend).
Upload documents/images (Pathos will process these as if he's looking at them).
Provide feedback on interactions (though its impact will evolve).
View Pathos's "Dream Journal," "Learning Log," etc. (reflecting his internal processes).
Adjust system settings.
6.2 API Endpoints
OpenAI Compatible:
GET /v1/models
POST /v1/chat/completions (Primary interaction point)
Eidos Specific (abridged):
GET /v1/briefing (Pathos's internal briefing, might be shared contextually)
POST /v1/documents/upload
POST /v1/feedback
GET /v1/agent/dreams
GET /v1/pathos/schedule/today (View Pathos's own schedule)
POST /v1/pathos/events/add (For user to suggest an event for Pathos, admin-gated)
GET /health
WS /ws (For GUI updates, proactive messages from Pathos, token streaming)
See main.py and eidos_agent/core/api_models.py for full schema.

7. Configuration Deep-Dive
All primary settings are managed via environment variables, typically set in the .env file.

7.1 LLM Roles
Each LLM role (e.g., PATHOS, LOGOS_TECHNE for utility tasks, NPC_LLM, FIRMAMENT_LLM) is configured in .env:

LLM_<ROLE_NAME>_URL: Endpoint for the VLLM server providing this role.
LLM_<ROLE_NAME>_MODEL: Model identifier used by VLLM (e.g., Qwen/Qwen2.5-32B-Chat).
LLM_<ROLE_NAME>_API_KEY: Typically vllm or none when using VLLM locally.
LLM_<ROLE_NAME>_TEMP: Sampling temperature.
Other LLM parameters (max_tokens, top_p, etc.).
7.2 Service Keys
BRAVE_API_KEY: For Pathos's simulated web searches.
ONEIROS_STABLE_DIFFUSION_URL: If using Stable Diffusion for dream images.
7.3 Feature Flags & System Parameters
Numerous flags in .env control Eidos subsystems (e.g., ENABLE_ONEIROS, ENABLE_PROACTIVE_BEHAVIOR) and parameters for EthosCore, Firmament, Chronos, etc. (e.g., reflection intervals, mood decay rates).

8. Core Modules
Module	Role
EthosCore	Pathos's long-term memory, core self-construct (persona directives), mood, reflection, learning.
FirmamentModule	Central: Simulates Pathos's daily life, activities, availability, NPC interactions, environment.
ChronosEngine	Manages Pathos's schedule and significant life events, feeding into Firmament.
PathosInterface	Orchestrates interaction with Pathos's main LLM (Qwen2.5 32B VL), prompt assembly, stream handling.
LogosCore	Executes "internal" tool-like actions for Pathos (e.g., via the "Computer Interaction Module").
ComputerInteractionModule	(New/Conceptual) Simulates Pathos using a computer for tasks like web search.
SimulationModule	Manages mechanics of dialogue between Pathos (or his sim-self) and NPCs.
OneirosModule	Dream synthesis, influencing Pathos's subconscious and curiosity.
MemoryStorage	SQLite + embedding backend for all persistent memories.
ConnectionManager	Manages WebSocket connections for GUI updates and proactive messages.
9. Development Roadmap
(Focusing on the "Digital Being" vision for Pathos)

Phase	Status	Highlight
Phase 0: Stabilization & Foundational Persona	🔄 Current	Resolve critical bugs, robust VLLM (Qwen2.5 32B VL) stream handling, server-side chat GUI, history truncation, complete persona/prompt overhaul for 26-year-old human-believing Pathos.
Phase A: Enhancing Interaction & Early Simulation	⏭ Next	GUI token streaming, "Computer Interaction Module" (web search), Firmament MVP (availability, basic activity logging, "busy" state & message queuing), refined proactive messaging.
Phase B: Deepening Simulation & Organic Development	⏭	Firmament NPC interactions (Pathos-initiated & autonomous MVP), EthosCore dynamic persona (reflection-driven MVP), human-like memory enhancements, Oneiros dream influence & imagery, mood-influenced days.
Phase C: Advanced Autonomy, Relationships & World Interaction	⏭	Richer NPC relationships, Firmament environmental events, Pathos-driven goal setting (Ethos reflection), long-term life progression (Chronos/Firmament), "vision sensor" for presence.
Phase D: Refinement & Polish	⏭ Ongoing	Continuous LLM prompt tuning, Firmament scenario expansion, memory/performance optimization, GUI evolution.
(Previous roadmap phases related to direct assistant features, Home Assistant, or always-listening hardware have been deferred to a separate future project.)

10. Contributing
Eidos is primarily a personal research and development project exploring simulated consciousness and advanced AI agents. However, insights, well-reasoned ideas, and discussions are welcome via GitHub Issues.

Focus areas for potential future collaboration (once core simulation is mature):

Advanced Firmament scenario design and scripting.
Novel approaches to human-like memory and learning in AI.
Ethical considerations of highly autonomous, persona-driven AI.
11. License
To be decided – MIT or Apache-2.0 are likely.
A LICENSE file will be added if/when the project reaches a more public-ready state.

© 2025 Isaac Lamb – Exploring the frontiers of digital beings.