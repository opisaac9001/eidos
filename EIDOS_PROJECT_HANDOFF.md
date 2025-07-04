## Eidos Project Handoff Document

**Date:** July 4, 2025
**Project Lead (AI):** Jules
**Handing Off To:** Next AI Agent

**Overall Project Goal:**
The primary goal of the Eidos project is to create a virtual person, "Pathos," who perceives himself as real and exists within a simulated world called "Firmament." Pathos is intended to have memories, a personality, moods (tracked via a "Hexus" system), a schedule (managed by "ChronosEngine"), and the ability to engage in dynamic interactions with Non-Player Characters (NPCs) and his environment. The project aims for a high degree of naturalism in Pathos's behavior, thoughts, and conversations. The system utilizes multiple LLMs for different cognitive functions: a main LLM for Pathos's core thinking and user/NPC communication, a "Subconscious Node" LLM for continuous background thought-streaming, and LLMs within Firmament for NPC improvisation and world simulation aspects.

**Architectural Vision & Key Components:**
The project is being refactored towards a modular architecture. Key components include:
*   **`main.py`**: Main application entry point.
*   **`eidos_agent/`**: The core Python package for all agent logic.
    *   **`schemas/`**: Centralized Pydantic models for data structures.
    *   **`core/`**: Core components like `Config`, global managers.
    *   **`llm_integrations/`**:
        *   `LLMClient`: Standardized client for all LLM API calls.
        *   `PathosInterface`: Primary orchestrator for the Main Pathos LLM, handling context gathering, LLM invocation, response parsing (dialogue, tools, NPC actions), and interaction logging.
        *   `PromptBuilder`: Constructs prompts for the Main Pathos LLM.
    *   **`persona_logic/`**: Houses the "brain" components of Pathos.
        *   `EthosCore`: Manages Pathos's core self: memory (via `MemoryStorage`), Hexus mood state (via `MoodEngine`), personality traits (via `TraitsEngine`), and cognitive cycles like reflection and aspiration generation.
        *   `LogosCore`: Handles execution of tools requested by Pathos's LLM.
        *   `ChronosEngine`: Manages Pathos's schedule and calendar events.
    *   **`features/`**: Contains major functional units.
        *   `FirmamentModule`: Simulates Pathos's life, environment, and NPC interactions. Includes `NPCController` and `NPCImproviser`. Uses `ChronosAdapter` to get schedule information.
        *   `BookshelfFeature`: (Details TBD, but `BookshelfHandler` is a component).
        *   `OneirosModule`: (Intended for dream generation/management - not yet deeply refactored).
    *   **`integrations/`**: For clients to external services/nodes.
        *   `SubconsciousNodeClient`: Interface to the external Subconscious Node LLM.
    *   **`services/`**: Smaller, specific services (e.g., `OpenWeatherMapService`, TTS, WebSearch).
    *   **`api/`**: FastAPI routers for web interface interaction.

**Summary of Refactoring and Fixes Performed by Jules:**

The project underwent a significant "zero-basing" refactor to align the codebase with the architectural vision and improve inter-module communication, especially for LLM interactions.

**Phase 1: Design & Foundational Setup**
1.  **Core Interaction Scenario Defined:** Detailed the flow for "Pathos has a conversation with an NPC (influenced by subconscious thought), aware of his mood/schedule." This guided interface design.
2.  **Pydantic Schemas Centralized:** Created `eidos_agent/schemas/` and populated it with Pydantic models for consistent data structures (e.g., `MainLLMPromptContext`, `LLMOutput`, `SimulationContext`, `MoodState`, `EthosMemory`, `ActivitySlot`, `PathosEvent`, `ToolResult`). Ensured `eidos_agent/schemas/__init__.py` exists.
3.  **Standardized `LLMClient`:** Refactored `eidos_agent/llm_integrations/llm_client.py` to use a shared `HTTPClientManager` and return a standardized `LLMResponsePayload`.

**Phase 2: Core Module Refactoring**
4.  **`PathosInterface` Refactor (`eidos_agent/llm_integrations/pathos_interface.py`):**
    *   Overhauled to act as the primary orchestrator for the Main Pathos LLM.
    *   Implemented methods for context gathering (`gather_context_for_main_llm`), LLM invocation (`invoke_main_llm`), response parsing (`_parse_raw_llm_response`), and the main interaction loop (`process_user_interaction`) to handle dialogue, tool use, and NPC interactions.
    *   Integrated `FirmamentModule` calls for NPC interactions (via `interact_with_npc` tool which `LogosCore` dispatches to `FirmamentModule`).
    *   Enhanced context gathering to include NPC-initiated dialogue and target-NPC-specific memories.
5.  **`PromptBuilder` Update (`eidos_agent/llm_integrations/prompt_builder.py`):**
    *   Adapted to accept `MainLLMPromptContext` and handle token counting/truncation.
6.  **`EthosCore` Refactor (`eidos_agent/persona_logic/ethos_core/core.py`):**
    *   Updated to use new schemas from `ethos_schemas.py`.
    *   Implemented defined access patterns (e.g., `get_current_mood_state`, `get_relevant_memories`, `get_persona_profile`, `record_interaction_event`).
    *   Standardized its internal LLM calls (for reflection, summarization, aspiration generation) to use the shared `LLMClient`.
    *   Integrated `MoodEngine`, `ReflectionEngine`, `TraitsEngine`.
7.  **`FirmamentModule` Refactor (`eidos_agent/features/firmament/module.py` & `npcs/`):**
    *   Updated `NPCImproviser` to use `LLMClient`.
    *   Implemented `FirmamentModule`'s public interface methods (`get_current_simulation_context`, `process_pathos_utterance_to_npc`) using new Firmament schemas.
    *   `process_pathos_utterance_to_npc` now handles dialogue turns with NPCs, including updating NPC state and generating responses (potentially via `NPCController` and `NPCImproviser`).
8.  **`LogosCore` Refactor (`eidos_agent/persona_logic/logos_core/handler.py`):**
    *   Updated to use `LLMClient` for its internal LLM needs.
    *   Implemented `execute_tools` as the primary method for dispatching tool calls based on `LLMToolCall` objects from `PathosInterface`, returning `ToolResult` objects.
    *   Adapted individual `execute_X_tool` methods for standardized dictionary returns.
    *   Ensured integration with `BookshelfHandler`.
9.  **`SubconsciousNodeClient` Implementation (`eidos_agent/integrations/subconscious_node_client.py`):**
    *   Created the client class with methods to interact with the Subconscious Node API (get thoughts, inject context, set state) using `HTTPClientManager` and new schemas.
10. **`ChronosEngine` Refactor (`eidos_agent/persona_logic/chronos_engine/engine.py` & `models.py`):**
    *   Updated to use new `ActivitySlot` and `PathosEvent` Pydantic schemas.
    *   Ensured methods like `get_current_activity_for_user` and `add_planned_event` align with these schemas.
    *   Addressed circular dependency with `MemoryStorage` by moving `MemoryStorage` import to `TYPE_CHECKING` block in `engine.py`.

**Bug Fixes During Refactoring:**
*   **`IndentationError` in `pathos_interface.py` (around line 832):** Persisted through multiple attempts. The final fix involved a comprehensive re-indentation of the entire `send_sentence_to_tts_and_notify_client` method to ensure consistent 4-space indentation. (Branch: `fix/pathos-interface-indentation-v2`)
*   **`ImportError` for `MemoryEntry` (from `ethos_core`):** Caused by `MemoryEntry` import being nested in an unrelated `except` block in `eidos/eidos_agent/persona_logic/ethos_core/__init__.py`. Fixed by moving the import out of the `except` block. (Branch: `fix/memory-entry-import-error`)
*   **`ModuleNotFoundError` for `eidos_agent.features.bookshelf`:** Caused by an incorrect absolute import path in `logos_core/handler.py`. Corrected to `from eidos_agent.features.bookshelf_feature.handler import BookshelfHandler`. Also updated nearby relative imports to absolute. (Branch: `fix/bookshelf-import-error`)
*   **`ModuleNotFoundError` for `eidos_agent.schemas`:** Caused by a missing `__init__.py` file in the `eidos/eidos_agent/schemas/` directory. Fixed by creating the `__init__.py` file. (Branch: `fix/schemas-import-error`)
*   **`ImportError` for `PathosEvent` (from `chronos_engine.models` into `memory_storage.py`):** Identified as a circular dependency. `memory_storage.py` imports `chronos_engine.models`, while `chronos_engine.engine.py` (which uses `models.py`) imported `memory_storage.py`. Fixed by moving the `MemoryStorage` import in `chronos_engine.engine.py` into a `TYPE_CHECKING` block. (Branch: `fix/pathos-event-import-error`)
*   **`SyntaxError` in `chronos_engine/engine.py` (line 324):** An `if ZoneInfo: try:` statement had the `try` on the same line. Fixed by moving `try` to a new, indented line. (Branch: `fix/chronos-engine-syntax-error`)

**Known Persistent Issue:**
*   **Environment: "No space left on device" (`OSError: [Errno 28]`)**: This error occurred repeatedly during attempts to run `pip install -r requirements.txt`. It prevented full installation of dependencies (e.g., `httpx`, `opencv-python`). Consequently, runtime testing of fixes was severely hampered. The application would often fail early due to missing modules before reaching the code sections with the intended fixes. **This environment issue needs to be resolved before further debugging or development can reliably proceed.**

**Current Status (as of last error encountered before this handoff):**
The last error encountered was an `ImportError: cannot import name 'PathosEvent' from 'eidos_agent.persona_logic.chronos_engine.models'`, which was addressed by fixing the circular dependency. The very next error (if the `PathosEvent` fix works and assuming dependencies could be installed) is unknown.

**Recommendations for Next Steps:**
1.  **RESOLVE THE DISK SPACE ISSUE** in the execution environment to allow full installation of `requirements.txt`. This is critical.
2.  After resolving the disk space issue, run `pip install -r eidos/requirements.txt` (or `requirements.txt` if it's at the root and `eidos/` is the working dir).
3.  Attempt to run `python eidos/main.py` (or `python main.py` from within the `eidos/` directory).
4.  Address any subsequent startup errors. These could be further import issues, configuration problems, or runtime errors in the initialization sequence of the modules.
5.  **Verify Directory Structure**: Confirm that there isn't a duplicate or conflicting `eidos_agent/` directory at the repository root. All primary package code should reside within `eidos/eidos_agent/`. If a root-level `eidos_agent/` was created by me and contains essential, unique files, those should be carefully merged into `eidos/eidos_agent/` and the root-level one removed or confirmed to be a benign symlink. The user has indicated they performed a merge which resolved one `ModuleNotFoundError`, so this might be less of an issue now, but good to double-check.
6.  **Systematically Test Core Interactions**: Once the application starts, begin testing the core interaction flow designed earlier (Pathos talking to an NPC, context gathering, tool usage, etc.) to ensure the refactored components work together as intended.
7.  **Review `TODOs` and Placeholders**: Many refactored methods have placeholder comments for future enhancements or full implementations (e.g., `SubconsciousNodeClient` integration, advanced LLM output parsing). These should be reviewed.

This handoff should provide a comprehensive overview for the next AI agent to continue debugging and development. Good luck!
---
