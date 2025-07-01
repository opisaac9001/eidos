# eidos_agent/features/firmament/integrations/oneiros_adapter.py

# This module serves as an adapter to interface with the Oneiros dream generation module.
# It will be responsible for triggering dream generation based on context (e.g., recent
# memories, current mood, current sleep block) and retrieving the generated dream content,
# then logging this dream to memory.

import logging # Added: logging import
import random
from datetime import datetime, timezone # For timestamp in memory log
# Updated: typing imports to ensure all required types are present
from typing import Optional, Dict, Any, List, AsyncGenerator, Union

# Attempt to import core Eidos components.
try:
    # Absolute imports for core components (fixed from relative to resolve "split-brain" issue)
    from eidos_agent.core.config import Config, LLMConfig
    from eidos_agent.llm_integrations.llm_client import LLMClient
    from eidos_agent.core.http_client_manager import HTTPClientManager
    from eidos_agent.core.event_bus import EventBus # Corrected path for EventBus
    from eidos_agent.persona_logic.ethos_core.core import EthosCore
    from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
    from eidos_agent.persona_logic.chronos_engine import PATHOS_USER_ID
except ImportError: # pragma: no cover
    print("Warning: OneirosAdapter could not import core Eidos components. Using dummy versions.")
    # Define dummy versions for parsing and basic type hinting
    # Modeled after npc_improviser.py and existing dummies

    LLMConfig = Dict[str, Any]  # type:ignore # Alias for LLM configuration, typically a TypedDict

    class Config:  # type:ignore
        @staticmethod
        def get_llm_config(role_name: str) -> Optional[LLMConfig]:
            print(f"DummyConfig: get_llm_config called for role {role_name}")
            if role_name == "FIRMAMENT_PRIMARY": # Example role
                return {"role": role_name, "model": "dummy_model", "url": "http://dummy.url", "timeout": 10.0}
            return None
        # Add other static methods if Config is used for more by this adapter

    class LLMClient:  # type:ignore
        def __init__(self, http_client: Any): # http_client can be a dummy/mock
            self.http_client = http_client
            self._logger = logging.getLogger(__name__) # Use standard logger
            self._logger.info("DummyLLMClient initialized.")

        async def call_llm_api(
            self, llm_config: LLMConfig, messages: List[Dict[str, str]],
            stream: bool = False, **kwargs: Any
        ) -> Union[AsyncGenerator[str, None], str]:
            self._logger.info(f"DummyLLMClient: call_llm_api called with config {llm_config}, stream={stream}")
            if stream:
                async def dummy_stream():
                    yield "Dummy streamed response chunk 1."
                    yield "Dummy streamed response chunk 2."
                return dummy_stream()
            return "Dummy non-streamed LLM response."
        # Add other methods if LLMClient is used for more by this adapter

    class HTTPClientManager:  # type:ignore
        _instance = None
        def __init__(self):
            self._logger = logging.getLogger(__name__)
            self._logger.info("DummyHTTPClientManager __init__ called (should be singleton).")

        @classmethod
        def instance(cls):
            if cls._instance is None:
                cls._instance = cls()
                # Logger in __init__ will confirm creation
            return cls._instance

        def get_client(self) -> Optional[Any]: # Ideally Optional[httpx.AsyncClient]
            # In a dummy, can return None or a mock httpx.AsyncClient
            # For simplicity, returning None as OneirosAdapter should handle it
            self._logger.info("DummyHTTPClientManager: get_client called, returning None.")
            return None

        async def startup(self):
            self._logger.info("DummyHTTPClientManager: startup called.")

        async def shutdown(self):
            self._logger.info("DummyHTTPClientManager: shutdown called.")

    # Existing dummy types that might still be needed if other parts of the file use them
    MemoryEntry = Dict[str, Any] # type: ignore
    PATHOS_USER_ID = "pathos_dummy_user_id_if_import_fails" # Dummy value

    class EthosCore: # type: ignore
        def __init__(self, config: Any = None): # Added default to config
            self._logger = logging.getLogger(__name__)
            self._logger.info("DummyEthosCore initialized.")
        async def get_memories_for_dream_seeding(self, user_id: str, lookback_days: int, limit: int, memory_types: Optional[List[str]] = None) -> List[MemoryEntry]:
            self._logger.info(f"DummyEthosCore.get_memories_for_dream_seeding called for user {user_id}")
            return [{"type": "dummy_interaction", "content": "Dummy memory content from EthosCore.", "timestamp": datetime.now(timezone.utc).isoformat()}]
        def get_current_mood(self) -> Dict[str, Any]:
             self._logger.info("DummyEthosCore.get_current_mood called.")
             return {"name": "dummy_mood", "valence": 0, "arousal": 0}

    class EventBus: # type: ignore
        _instance = None; _subscribers = {} # type: ignore
        def __init__(self):
            self._logger = logging.getLogger(__name__)
            self._logger.info("DummyEventBus __init__ called (should be singleton).")

        @classmethod
        def instance(cls): # type: ignore
            if not cls._instance: cls._instance = cls() # type: ignore
            return cls._instance # type: ignore
        def subscribe(self, et, h): self._logger.info(f"DummyEventBus: Subscribed handler to {et}") # type: ignore
        def publish(self, et, d): self._logger.info(f"DummyEventBus (Oneiros): Published {et} with {d}") # type: ignore


# Define event type strings used by this adapter
EVENT_ONEIROS_START_DREAM = "oneiros.start_dream_sequence" # Event this adapter listens to
EVENT_MEMORY_WRITE = "memory.write"                     # Event this adapter publishes to


class OneirosAdapter:
    # EthosCore is removed from __init__ params. If needed, it should be set via a dedicated setter method
    # by the Firmament bootstrap process, similar to other adapters.
    def __init__(self,
                 http_client_manager: Optional[HTTPClientManager] = None,
                 llm_role_name: str = "FIRMAMENT_PRIMARY",
                 oneiros_config: Optional[Dict[str, Any]] = None):
        """
        Initializes the OneirosAdapter.
        This adapter can use an LLM to enhance dream generation if configured.

        Args:
            http_client_manager (Optional[HTTPClientManager], optional): Manager for HTTP clients. Defaults to None.
            llm_role_name (str, optional): The LLM role name to use for LLM-driven features. Defaults to "FIRMAMENT_PRIMARY".
            oneiros_config (Optional[Dict[str, Any]], optional): Configuration for the Oneiros module. Defaults to None.
        """
        self.logger = logging.getLogger(__name__)
        self.adapter_config = oneiros_config if oneiros_config is not None else {} # Ensure {} if None
        self.http_client_manager = http_client_manager
        self.llm_role_name = llm_role_name
        # self.llm_config: Optional[LLMConfig] = None # Declaration moved slightly for clarity
        self.ethos_core: Optional[EthosCore] = None # Initialize as None, to be set by a setter if used

        if http_client_manager: # Only try to get LLM config if a client manager is provided
            self.llm_config: Optional[LLMConfig] = Config.get_llm_config(self.llm_role_name) # type: ignore
            if not self.llm_config:
                self.logger.error(f"OneirosAdapter: LLM config for role '{self.llm_role_name}' not found.")
                # self.llm_config remains None if not found, which is desired.
            else:
                self.logger.info(f"OneirosAdapter initialized for LLM role '{self.llm_role_name}'. Model: {self.llm_config.get('model')}")
        else: # No http_client_manager, so no LLM operations possible
            self.llm_config = None
            self.logger.info("OneirosAdapter initialized without HTTPClientManager. LLM operations will be disabled.")

        # EthosCore is no longer passed in __init__.
        # If an EthosCore instance is needed, it should be provided via a setter method
        # by the Firmament system after OneirosAdapter initialization.
        # Example: oneiros_adapter.set_ethos_core(ethos_core_instance)

        self.model_loaded = False # Existing attribute, relevance might change with more LLM focus
        self._initialize_oneiros_engine() # Existing method call, might also adapt over time
        # Updated log message to be slightly more concise if EthosCore is not part of init status
        self.logger.info(f"OneirosAdapter initialized. LLM Role: '{self.llm_role_name}'. Model Loaded: {self.model_loaded}. Config: {self.adapter_config}")


    # It's anticipated that EthosCore will be set using a setter method by Firmament core.
    # Example:
    # def set_ethos_core(self, ethos_core_instance: EthosCore):
    #     self.ethos_core = ethos_core_instance
    #     self.logger.info("EthosCore instance set on OneirosAdapter.")

    async def _get_recent_memories_for_dream_context(self) -> List[str]:
        if not self.ethos_core:
            self.logger.warning("OneirosAdapter: EthosCore not available (has it been set via setter?). Returning default placeholder memories.")
            return ["Pathos recalls a day of quiet contemplation.", "A fleeting thought about the color blue."]

        try:
            # Configuration for fetching memories - could be made configurable later
            lookback_days = self.adapter_config.get("dream_memory_lookback_days", 3)
            memory_limit = self.adapter_config.get("dream_memory_limit", 5)

            # Assuming PATHOS_USER_ID is accessible or a constant.
            # For now, let's hardcode it or assume it's available via a config/constant import.
            # If not, this needs to be passed in or made available.
            # Let's assume a placeholder for now if direct import isn't clean.
            # pathos_user_id = self.adapter_config.get("pathos_user_id", "pathos_default_user") # Placeholder REMOVED
            # Use the imported PATHOS_USER_ID constant directly
            user_id_for_memories = PATHOS_USER_ID

            self.logger.debug(f"Fetching memories for dream context. User: {user_id_for_memories}, Lookback: {lookback_days} days, Limit: {memory_limit}")

            # Define specific memory types relevant for dreams
            dream_memory_types = [
                'interaction', 'firmament_activity_log', 'received_subconscious_intention',
                'npc_dialogue_event', 'reflection_insight', 'learned_correction', 'feedback', 'dream'
            ]

            # Call the new EthosCore method
            recent_memory_entries: List[MemoryEntry] = await self.ethos_core.get_memories_for_dream_seeding(
                user_id=user_id_for_memories, # Use the constant
                lookback_days=lookback_days,
                limit=memory_limit,
                memory_types=dream_memory_types
            )

            if not recent_memory_entries:
                self.logger.info("No recent memories returned from EthosCore for dream context.")
                return ["The day's events are a blur.", "A sense of quiet anticipation."]

            # Format memories into strings for the prompt
            formatted_memories = []
            for mem_entry in recent_memory_entries:
                content = str(mem_entry.get('content', ''))
                # Simple summarization: take first N chars. More sophisticated summarization could be added.
                snippet = (content[:75] + '...') if len(content) > 75 else content
                type_info = mem_entry.get('type', 'memory')
                # Optional: add timestamp or salience if useful for the dream LLM
                # ts_info = datetime.fromisoformat(mem_entry.get('timestamp', '')).strftime('%H:%M') if mem_entry.get('timestamp') else ''
                # formatted_memories.append(f"A {type_info} from {ts_info}: {snippet}")
                formatted_memories.append(f"A recent {type_info}: {snippet}")


            self.logger.info(f"Returning {len(formatted_memories)} formatted memories for dream prompt.")
            return formatted_memories

        except Exception as e:
            self.logger.error(f"Error fetching or processing memories for dream context: {e}", exc_info=True)
            return ["A vague recollection of the day's events.", "An echo of a distant thought."]

    def _initialize_oneiros_engine(self):
        """
        Placeholder for loading dream generation models or setting up the engine.
        """
        if self.adapter_config.get("model_path") or self.adapter_config.get("use_default_model", True):
            self.logger.debug(f"OneirosAdapter: Initializing Oneiros engine with config: {self.adapter_config} (simulated)")
            self.model_loaded = True
        else:
            self.logger.info("OneirosAdapter: No model configuration. Dream generation will be very basic.")
        return self.model_loaded

    async def generate_dream(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Simulates generating a dream narrative via the Oneiros module.

        Args:
            context (Optional[Dict[str, Any]], optional): Contextual information that might influence
                                      dream generation. This could include keys like
                                      'name' (of sleep block), 'type', etc. Defaults to None.

        Returns:
            str: The generated dream content as a string narrative.
        """
        self.logger.debug(f"OneirosAdapter: generate_dream() called. Context provided: {bool(context)}")
        if context:
            self.logger.debug(f"  Context details for dream gen: {str(context)[:200]}{'...' if len(str(context)) > 200 else ''}")

        # Extract context for prompt
        block_data = context.get("block_data", {}) if context else {}
        block_name = block_data.get("name", "an unknown activity")

        # Fetch current mood from EthosCore
        current_mood_name = "neutral" # Default mood
        if self.ethos_core:
            try:
                mood_data = self.ethos_core.get_current_mood() # This is a synchronous method in EthosCore
                if mood_data and isinstance(mood_data, dict) and "name" in mood_data:
                    current_mood_name = mood_data["name"]
                    # Ensure valence and arousal are numbers before formatting
                    valence_val = mood_data.get('valence', 'N/A')
                    arousal_val = mood_data.get('arousal', 'N/A')
                    valence_str = f"{valence_val:.2f}" if isinstance(valence_val, (int, float)) else str(valence_val)
                    arousal_str = f"{arousal_val:.2f}" if isinstance(arousal_val, (int, float)) else str(arousal_val)
                    self.logger.debug(f"Fetched current mood for dream context: {current_mood_name} (Valence: {valence_str}, Arousal: {arousal_str})")
                else:
                    self.logger.warning(f"Failed to get valid mood name from EthosCore. Mood data: {mood_data}. Using default '{current_mood_name}'.")
            except Exception as e_mood:
                self.logger.error(f"Error fetching mood from EthosCore: {e_mood}", exc_info=True)
                self.logger.info(f"Using default mood '{current_mood_name}' due to error.")
        else:
            self.logger.warning(f"EthosCore not available (has it been set via setter?). Using default mood '{current_mood_name}'.")

        # Get recent memories for dream context
        recent_memories_list = await self._get_recent_memories_for_dream_context()
        memories_summary = "\n".join(recent_memories_list) if recent_memories_list else "No specific recent memories noted."


        prompt_parts = [
            "You are a dream weaver, skilled in crafting surreal and symbolic narratives.",
            f"Pathos is currently in a state of '{block_name}'.",
            f"Pathos's current mood is '{current_mood_name}'.",
            f"Recent experiences or thoughts include: '{memories_summary}'.",
            "Generate a dream narrative, 2-4 sentences long.",
            "Make it surreal, abstract, or symbolic, reflecting these recent experiences or current mood.",
            "Output only the dream text, with no additional commentary or conversational elements."
        ]
        prompt_text = "\n".join(prompt_parts)
        self.logger.debug(f"Constructed dream prompt:\n{prompt_text}")

        # Attempt to use LLM for dream generation if configured
        use_llm = self.adapter_config.get("use_llm_if_available", False) and self.llm_config and self.http_client_manager
        if use_llm:
            try:
                shared_httpx_client = self.http_client_manager.get_client() # type: ignore
                if not shared_httpx_client:
                    self.logger.warning("OneirosAdapter: LLM use enabled, but HTTP client not available. Falling back to basic dream generation.")
                else:
                    llm_api_client = LLMClient(http_client=shared_httpx_client)
                    messages = [{"role": "user", "content": prompt_text}]

                    self.logger.info(f"OneirosAdapter: Calling LLM for dream generation (Role: {self.llm_role_name}).")
                    response_data = await llm_api_client.call_llm_api(
                        llm_config=self.llm_config, # type: ignore
                        messages=messages,
                        stream=False # Assuming non-streaming for dream content for now
                    )

                    if isinstance(response_data, str) and response_data.strip():
                        dream_content = response_data.strip()
                        self.logger.info(f"OneirosAdapter: Dream generated by LLM: \"{dream_content[:100]}{'...' if len(dream_content) > 100 else ''}\"")
                        return dream_content
                    elif isinstance(response_data, dict) and response_data.get("type") == "error_chunk": # Check for error structure from LLMClient dummy
                        self.logger.error(f"OneirosAdapter: LLM API error: {response_data.get('payload')}. Falling back.")
                    else:
                        self.logger.warning(f"OneirosAdapter: LLM returned empty or unexpected response: {response_data}. Falling back.")

            except Exception as e:
                self.logger.error(f"OneirosAdapter: Error during LLM call for dream generation: {e}", exc_info=True)
                self.logger.info("Falling back to basic dream generation due to LLM error.")

        # Fallback logic:
        # This section is reached if LLM was not used (use_llm is false)
        # OR if the LLM call was attempted but failed (and did not return a dream_content).

        # This check can be relevant if, for instance, http_client_manager was not provided at all,
        # making LLM use impossible from the start.
        if not use_llm and not self.http_client_manager:
             self.logger.warning("OneirosAdapter: LLM operations disabled (no HTTPClientManager). Cannot generate LLM dream.")
        # The self.model_loaded check might be less relevant now if LLM is primary,
        # but can be kept if there's a non-LLM "engine" concept that could be "not loaded".
        # For now, we simplify: if LLM failed or wasn't used, provide a static placeholder.

        # If LLM was attempted (meaning use_llm was true) but failed, it would have logged the specific error.
        # Now, we log that we're using a placeholder.
        if use_llm: # Implies an LLM attempt was made but failed to return content
            self.logger.info("OneirosAdapter: LLM dream generation failed or returned no content. Using static placeholder dream.")
        else: # LLM was not attempted (e.g. use_llm_if_available was false, or no llm_config)
            self.logger.info("OneirosAdapter: LLM not configured or not enabled. Using static placeholder dream.")

        # Static placeholder dream
        dream_content = "Pathos had a fleeting, indistinct dream."
        self.logger.info(f"OneirosAdapter: Using static placeholder: \"{dream_content}\"")
        return dream_content

    async def handle_start_dream_request(self, data: Dict[str, Any]):
        """
        Handles the request to start a dream sequence (typically from EVENT_ONEIROS_START_DREAM),
        generates a dream, and logs it to memory. This is now an async method.

        Args:
            data (Dict[str, Any]): The event data, expected to contain 'block_data' with details
                                   of the sleep schedule block that triggered the dream.
        """
        self.logger.info(f"OneirosAdapter: Entered handle_start_dream_request for {EVENT_ONEIROS_START_DREAM} event.") # MODIFIED
        if data:
            self.logger.debug(f"  Event Data for handle_start_dream_request: {str(data)[:200]}{'...' if len(str(data)) > 200 else ''}") # MODIFIED

        # block_data provides context for dream generation (e.g., from the sleep schedule block)
        block_data: Dict[str, Any] = data.get("block_data", {}) # type: ignore
        if not isinstance(block_data, dict): # Ensure block_data is a dict if it exists
            self.logger.warning(f"Received block_data is not a dict: {type(block_data)}. Using empty context.")
            block_data = {}

        # Generate the dream content using the provided context
        dream_content = await self.generate_dream(context=block_data) # Ensure context is Dict[str, Any] or None

        # Prepare the payload for writing the dream to memory
        memory_payload: Dict[str, Any] = {
            "type": "dream", # Categorizes this memory entry as a dream
            "content": dream_content,
            "metadata": {
                "source_event_type": EVENT_ONEIROS_START_DREAM, # What triggered this dream log
                "sleep_block_id": block_data.get("id"),
                "sleep_block_name": block_data.get("name"),
                "sleep_block_type": block_data.get("type"),
                "dream_generation_config": self.adapter_config, # Store config used, if any
                "dream_timestamp_utc": datetime.now(timezone.utc).isoformat() # Timestamp of dream generation
            }
        }

        # Publish the dream to memory
        try:
            self.logger.info(f"OneirosAdapter: About to publish dream to EventBus. Type: {EVENT_MEMORY_WRITE}, Content: {dream_content[:60]}...") # MODIFIED
            EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)
            self.logger.info(f"OneirosAdapter: Successfully published dream content to memory via '{EVENT_MEMORY_WRITE}'. Dream: '{dream_content[:60]}...'") # MODIFIED
        except Exception as e: # pragma: no cover
            self.logger.error(f"OneirosAdapter Error: Failed to publish dream to EventBus. Exception: {e}", exc_info=True)


def register_oneiros_event_handlers(adapter_instance: OneirosAdapter):
    """
    Subscribes OneirosAdapter's event handlers to the global EventBus.

    Args:
        adapter_instance (OneirosAdapter): The instance of the OneirosAdapter whose
                                           handlers need to be registered.
    """
    # Assuming logger is available or passed if this function is outside a class with self.logger
    # For simplicity, using print here if global logger not easily accessible.
    # If this function were part of a class, self.logger would be used.
    global_logger = logging.getLogger(__name__) # Or pass logger as an argument
    try:
        event_bus = EventBus.instance()
        event_bus.subscribe(EVENT_ONEIROS_START_DREAM, adapter_instance.handle_start_dream_request)
        global_logger.info(f"OneirosAdapter: Successfully registered 'handle_start_dream_request' for {EVENT_ONEIROS_START_DREAM} events.")
    except Exception as e: # pragma: no cover
        global_logger.error(f"OneirosAdapter Error: Failed to register event handlers with EventBus. Exception: {e}", exc_info=True)


if __name__ == '__main__':
    import asyncio # Required for running async functions in __main__
    from collections import defaultdict # For MockEventBus

    # Setup basic logging for the __main__ block if not already configured
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_logger = logging.getLogger(__name__ + ".__main__") # Specific logger for main test

    # Basic test setup for OneirosAdapter event handling
    _test_events_captured_oneiros: List[Dict[str, Any]] = [] # Stores {"type": event_type, "data": data_arg}
    def capture_event_for_oneiros_test(event_type_captured: str, data_captured: Dict[str, Any]): # Unique name
        main_logger.info(f"    [CaptureOneirosTest] Event: {event_type_captured}, Relevant Data: {str(data_captured.get('content', data_captured.get('reason', data_captured)))[:80]}")
        _test_events_captured_oneiros.append({"type": event_type_captured, "data": data_captured})

    # Mock EventBus for isolated testing of this adapter's event interactions
    class MockEventBusForOneiros(EventBus): # type: ignore
        def __init__(self):
            self._subscribers: Dict[str, List[Any]] = defaultdict(list) # Initialize subscribers
            self._logger = logging.getLogger(__name__) # Added logger initialization
            main_logger.info("MockEventBusForOneiros initialized.")

        def subscribe(self, event_type: str, handler: Any): # Added subscribe override
            self._subscribers[event_type].append(handler)
            self._logger.info(f"MockEventBusForOneiros: Subscribed handler {handler.__name__} to {event_type}")

        def clear_subscribers(self): # Added method to clear subscribers
            self._subscribers.clear()
            self._logger.info("MockEventBusForOneiros: All subscribers cleared.")

        async def publish_async(self, event_type: str, data: Dict[str, Any]): # Renamed to avoid conflict if sync publish is also used
            main_logger.debug(f"MockEventBusForOneiros: Async Publishing {event_type}...")
            # Crucially, call the capture function to log what this adapter would publish
            capture_event_for_oneiros_test(event_type, data) # Assuming capture_event is sync

            # Then, simulate dispatch to actual subscribers that were registered on this mock instance
            # This is important for testing if the handler *itself* works when an event comes in.
            for handler in self._subscribers.get(event_type, []):
                if asyncio.iscoroutinefunction(handler):
                    await handler(data) # Await async handlers
                else:
                    handler(data) # Call sync handlers directly
            for handler in self._subscribers.get("*", []): # Wildcard listeners
                if asyncio.iscoroutinefunction(handler): # Assuming wildcard handlers could also be async
                    await handler(event_type, data)
                else:
                    handler(event_type, data)

        # Keep a sync publish if other parts of the system use it, or if EventBus supports both
        def publish(self, event_type: str, data: Dict[str, Any]):
            main_logger.debug(f"MockEventBusForOneiros: Sync Publishing {event_type}...")
            capture_event_for_oneiros_test(event_type, data)
            for handler in self._subscribers.get(event_type, []):
                if not asyncio.iscoroutinefunction(handler): # Only call sync handlers
                    handler(data)
            for handler in self._subscribers.get("*", []):
                 if not asyncio.iscoroutinefunction(handler):
                    handler(event_type, data)


    async def main_async_test_runner():
        # Monkey patch EventBus.instance() for this test run
        original_event_bus_instance_method = EventBus.instance # type: ignore
        mock_bus_instance_oneiros = MockEventBusForOneiros() # type: ignore
        EventBus.instance = lambda: mock_bus_instance_oneiros # type: ignore

        # Create an instance of the adapter and register its handlers on the mock bus
        # Test with and without HTTPClientManager
        main_logger.info("\n--- Testing OneirosAdapter with HTTPClientManager (dummy) ---")
        dummy_http_client_manager = HTTPClientManager.instance() # Get dummy instance


        # MockEthosCore for testing purposes. In a real scenario, Firmament would inject this.
        class MockEthosCoreForOneirosTest(EthosCore): # Inherits from dummy or real EthosCore
            def __init__(self):
                super().__init__(config=None) # Call parent __init__ if necessary
                main_logger.info("MockEthosCoreForOneirosTest initialized for testing.")

            async def get_memories_for_dream_seeding(self, user_id, lookback_days, limit, memory_types):
                main_logger.info(f"MockEthosCoreForOneirosTest.get_memories_for_dream_seeding called for user {user_id} (should be PATHOS_USER_ID: {PATHOS_USER_ID})")
                assert user_id == PATHOS_USER_ID, f"MockEthosCore expected user_id {PATHOS_USER_ID}, got {user_id}"
                return [
                    {"type": "interaction", "content": "Had a pleasant chat about the weather.", "timestamp": "2023-01-01T10:00:00Z", "salience": 0.7},
                    {"type": "firmament_activity_log", "content": "Pathos was working on a creative project.", "timestamp": "2023-01-01T14:00:00Z", "salience": 0.5}
                ]

            def get_current_mood(self) -> Dict[str, Any]: # This is synchronous
                main_logger.info("MockEthosCoreForOneirosTest.get_current_mood called.")
                return {
                    "valence": 0.5,
                    "arousal": 0.3,
                    "name": "content", # Example mood name
                    "simulation_disabled": False,
                    "hexus_snapshot": {"joy": 0.6, "stress": 0.1} # Dummy hexus snapshot
                }

        mock_ethos_core_instance = MockEthosCoreForOneirosTest()

        oneiros_adapter_with_llm = OneirosAdapter(
            http_client_manager=dummy_http_client_manager, # type: ignore
            llm_role_name="FIRMAMENT_PRIMARY",
            oneiros_config={"model_type": "test_llm_enhanced", "allow_basic_fallback": True, "use_llm_if_available": True}
            # ethos_core is NOT passed in __init__ anymore
        )
        # Simulate setting ethos_core via a setter (method would need to be added to OneirosAdapter)
        oneiros_adapter_with_llm.ethos_core = mock_ethos_core_instance # type: ignore # Direct set for test
        if hasattr(oneiros_adapter_with_llm, 'set_ethos_core'): # If a setter exists
             # oneiros_adapter_with_llm.set_ethos_core(mock_ethos_core_instance) # type: ignore
             pass # Call actual setter if it was added

        register_oneiros_event_handlers(adapter_instance=oneiros_adapter_with_llm)

        # --- Test for LLM-enabled instance ---
        main_logger.info("\n--- Testing OneirosAdapter's handle_start_dream_request via Event (for LLM-enabled instance) ---")
        # This part of the test uses the handlers registered above (for oneiros_adapter_with_llm)
        # It's assumed that at this point, only oneiros_adapter_with_llm's handlers are (or should be) active for this test sequence.
        # However, due to how MockEventBus was structured, both might have been registered if not careful.
        # The fix to MockEventBus.subscribe and the later clear_subscribers call address this.

        # To be absolutely sure for the LLM test, we could clear and re-register ONLY the LLM adapter's handlers
        # For now, the issue was that the *basic* test was polluted by the LLM adapter's events.

        sleep_block_trigger_data_llm: Dict[str, Any] = { # Renamed for clarity
            "reason": "schedule_block_sleep_started",
            "block_data": {
                "id": "sleep_block_test_001_llm",
                "name": "REM Sleep Cycle (LLM)",
                "type": "sleep_rem",
                "start_time_utc": "2023-01-01T23:00:00Z",
                "end_time_utc": "2023-01-02T00:00:00Z"
            },
            "trigger_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        _test_events_captured_oneiros.clear()
        await mock_bus_instance_oneiros.publish_async(EVENT_ONEIROS_START_DREAM, sleep_block_trigger_data_llm)

        found_dream_memory_event_llm = False
        # Iterate through captured events to find the one from the LLM adapter.
        # This might require more specific checks if both adapters' events are still captured.
        for evt in _test_events_captured_oneiros:
            if evt["type"] == EVENT_MEMORY_WRITE and evt["data"].get("type") == "dream":
                dream_metadata = evt["data"].get("metadata", {})
                # Check if this event is from the LLM adapter based on sleep_block_id
                if dream_metadata.get('sleep_block_id') == "sleep_block_test_001_llm":
                    found_dream_memory_event_llm = True
                    main_logger.info(f"  Verified dream memory event (LLM instance):")
                    main_logger.info(f"    Dream Content: '{evt['data']['content'][:70]}...'")
                    main_logger.info(f"    Sleep Block ID: {dream_metadata.get('sleep_block_id')}")
                    main_logger.info(f"    Config used: {dream_metadata.get('dream_generation_config')}")
                    assert dream_metadata.get('dream_generation_config', {}).get("model_type") == "test_llm_enhanced"
                    break # Found the specific event for the LLM test
        assert found_dream_memory_event_llm, f"Expected LLM-enabled OneirosAdapter to publish '{EVENT_MEMORY_WRITE}' (dream) for its specific trigger."


        # --- Test for basic instance (no LLM) ---
        main_logger.info("\n--- Testing OneirosAdapter without HTTPClientManager or EthosCore (Basic Instance Test) ---")
        mock_bus_instance_oneiros.clear_subscribers() # Clear handlers from the LLM adapter test
        _test_events_captured_oneiros.clear() # Clear captured events from previous test run

        oneiros_adapter_no_llm = OneirosAdapter(
            oneiros_config={"model_type": "test_basic", "allow_basic_fallback": True}
        )
        register_oneiros_event_handlers(adapter_instance=oneiros_adapter_no_llm)


        main_logger.info("\n--- Testing OneirosAdapter's handle_start_dream_request via Event (for basic instance) ---")

        # This is the data that the `schedule` handler would publish for a sleep block
        sleep_block_trigger_data: Dict[str, Any] = {
            "reason": "schedule_block_sleep_started", # From schedule.py
            "block_data": { # This is the 'block_data' passed to generate_dream context
                "id": "sleep_block_test_001_llm",
                "name": "REM Sleep Cycle (LLM)",
                "type": "sleep_rem",
                "start_time_utc": "2023-01-01T23:00:00Z",
                "end_time_utc": "2023-01-02T00:00:00Z" # Example duration
            },
            "trigger_timestamp_utc": datetime.now(timezone.utc).isoformat() # From schedule.py
        }

        # Simulate the EVENT_ONEIROS_START_DREAM event being published on the bus.
        # This should trigger oneiros_adapter_with_llm.handle_start_dream_request
        _test_events_captured_oneiros.clear() # Clear events before this test
        # Use the new async publish method
        await mock_bus_instance_oneiros.publish_async(EVENT_ONEIROS_START_DREAM, sleep_block_trigger_data)

        # Verify that handle_start_dream_request (when triggered) published a "dream" memory event
        found_dream_memory_event_llm = False
        for evt in _test_events_captured_oneiros:
            if evt["type"] == EVENT_MEMORY_WRITE and evt["data"].get("type") == "dream":
                found_dream_memory_event_llm = True
                dream_metadata = evt["data"].get("metadata", {}) # type: ignore
                main_logger.info(f"  Verified dream memory event (LLM instance):")
                main_logger.info(f"    Dream Content: '{evt['data']['content'][:70]}...'") # type: ignore
                main_logger.info(f"    Sleep Block ID: {dream_metadata.get('sleep_block_id')}") # type: ignore
                main_logger.info(f"    Config used: {dream_metadata.get('dream_generation_config')}") # type: ignore
                assert dream_metadata.get('sleep_block_id') == "sleep_block_test_001_llm", "Sleep block ID mismatch (LLM)." # type: ignore
                assert dream_metadata.get('dream_generation_config', {}).get("model_type") == "test_llm_enhanced" # type: ignore
                break
        assert found_dream_memory_event_llm, f"Expected LLM-enabled OneirosAdapter to publish '{EVENT_MEMORY_WRITE}' (dream)."


        main_logger.info("\n--- Testing OneirosAdapter's handle_start_dream_request via Event (for basic instance) ---")
        sleep_block_trigger_data_basic: Dict[str, Any] = {
            "reason": "schedule_block_sleep_started",
            "block_data": {
                "id": "sleep_block_test_002_basic",
                "name": "Deep Slumber Cycle (Basic)",
                "type": "sleep_deep",
            },
            "trigger_timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        _test_events_captured_oneiros.clear() # Clear events before this test
        await mock_bus_instance_oneiros.publish_async(EVENT_ONEIROS_START_DREAM, sleep_block_trigger_data_basic)

        found_dream_memory_event_basic = False
        for evt in _test_events_captured_oneiros:
            if evt["type"] == EVENT_MEMORY_WRITE and evt["data"].get("type") == "dream":
                found_dream_memory_event_basic = True
                dream_metadata = evt["data"].get("metadata", {}) # type: ignore
                main_logger.info(f"  Verified dream memory event (Basic instance):")
                main_logger.info(f"    Dream Content: '{evt['data']['content'][:70]}...'") # type: ignore
                main_logger.info(f"    Sleep Block ID: {dream_metadata.get('sleep_block_id')}") # type: ignore
                main_logger.info(f"    Config used: {dream_metadata.get('dream_generation_config')}") # type: ignore
                assert dream_metadata.get('sleep_block_id') == "sleep_block_test_002_basic", "Sleep block ID mismatch (Basic)." # type: ignore
                assert dream_metadata.get('dream_generation_config', {}).get("model_type") == "test_basic" # type: ignore
                break
        assert found_dream_memory_event_basic, f"Expected basic OneirosAdapter to publish '{EVENT_MEMORY_WRITE}' (dream)."


        # Restore original EventBus class method
        EventBus.instance = original_event_bus_instance_method # type: ignore
        main_logger.info("\n--- OneirosAdapter event handling testing finished ---")

if __name__ == '__main__':
    asyncio.run(main_async_test_runner())
