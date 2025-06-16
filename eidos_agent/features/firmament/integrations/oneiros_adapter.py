# eidos_agent/features/firmament/integrations/oneiros_adapter.py

# This module serves as an adapter to interface with the Oneiros dream generation module.
# It will be responsible for triggering dream generation based on context (e.g., recent
# memories, current mood, current sleep block) and retrieving the generated dream content,
# then logging this dream to memory.

import random
from datetime import datetime, timezone # For timestamp in memory log

# Attempt to import EventBus. If this adapter is part of a larger system,
# EventBus should be accessible via the Python path.
try:
    from ..core.event_bus import EventBus
except ImportError: # pragma: no cover
    print("Warning: OneirosAdapter could not import EventBus. Event handling will not work unless EventBus is provided.")
    # Define a dummy EventBus if import fails, so the file can be parsed for basic testing of generate_dream
    class EventBus: # type: ignore
        _instance = None; _subscribers = {} # type: ignore
        @classmethod
        def instance(cls): # type: ignore
            if not cls._instance: cls._instance = cls() # type: ignore
            return cls._instance # type: ignore
        def subscribe(self, et, h): pass # type: ignore
        def publish(self, et, d): print(f"DummyEventBus (Oneiros): Published {et} with {d}") # type: ignore


# Define event type strings used by this adapter
EVENT_ONEIROS_START_DREAM = "oneiros.start_dream_sequence" # Event this adapter listens to
EVENT_MEMORY_WRITE = "memory.write"                     # Event this adapter publishes to


class OneirosAdapter:
    def __init__(self, oneiros_config: dict = None):
        """
        Initializes the OneirosAdapter.
        In a real implementation, this might load dream generation models or
        connect to an Oneiros service.

        Args:
            oneiros_config (dict, optional): Configuration for the Oneiros module.
                                             Defaults to None.
        """
        self.config = oneiros_config if oneiros_config else {}
        self.model_loaded = False
        self._initialize_oneiros_engine()
        # print(f"OneirosAdapter initialized. Model Loaded: {self.model_loaded}. Config: {self.config}")

    def _initialize_oneiros_engine(self):
        """
        Placeholder for loading dream generation models or setting up the engine.
        """
        if self.config.get("model_path") or self.config.get("use_default_model", True):
            # print(f"OneirosAdapter: Initializing Oneiros engine with config: {self.config} (simulated)")
            self.model_loaded = True
        # else:
            # print("OneirosAdapter: No model configuration. Dream generation will be very basic.")
        return self.model_loaded

    def generate_dream(self, context: dict = None) -> str:
        """
        Simulates generating a dream narrative via the Oneiros module.

        Args:
            context (dict, optional): Contextual information that might influence
                                      dream generation. This could include keys like
                                      'name' (of sleep block), 'type', etc. Defaults to None.

        Returns:
            str: The generated dream content as a string narrative.
        """
        # print(f"OneirosAdapter: generate_dream() called. Context provided: {bool(context)}")
        # if context:
            # print(f"  Context details for dream gen: {str(context)[:200]}{'...' if len(str(context)) > 200 else ''}")

        if not self.model_loaded and not self.config.get("allow_basic_fallback", True):
            return "Dream generation engine not available or not loaded."

        dream_themes = ["flying over abstract landscapes", "being chased by geometric shapes",
                        "falling through colorful voids", "discovering hidden rooms in a familiar place",
                        "solving ethereal puzzles with no clear rules", "meeting mysterious figures who speak in riddles"]
        dream_settings = ["a surreal, shifting cityscape", "a strangely distorted version of home",
                          "a library containing books with blank pages", "a dark, endless forest",
                          "an underwater realm of glowing flora"]

        chosen_theme = random.choice(dream_themes)
        chosen_setting = random.choice(dream_settings)
        dream_content = f"Pathos dreamt of {chosen_theme} in {chosen_setting}."

        if context:
            block_name = context.get("name", "an unknown activity")
            block_type = context.get("type", "unknown_type")
            dream_content += f" The dream seemed subtly influenced by the preceding '{block_name}' ({block_type}) block."
            if "Deep Slumber" in block_name: # Example of specific context influence
                 dream_content += " Whispers of forgotten code echoed in the depths of the dream."

        # print(f"OneirosAdapter: Dream generated (simulated): \"{dream_content[:100]}{'...' if len(dream_content) > 100 else ''}\"")
        return dream_content

    def handle_start_dream_request(self, data: dict):
        """
        Handles the request to start a dream sequence (typically from EVENT_ONEIROS_START_DREAM),
        generates a dream, and logs it to memory.

        Args:
            data (dict): The event data, expected to contain 'block_data' with details
                         of the sleep schedule block that triggered the dream.
        """
        # print(f"OneirosAdapter: Received {EVENT_ONEIROS_START_DREAM} event.")
        # if data:
            # print(f"  Event Data: {str(data)[:200]}{'...' if len(str(data)) > 200 else ''}")

        # block_data provides context for dream generation (e.g., from the sleep schedule block)
        block_data = data.get("block_data", {})
        if not isinstance(block_data, dict): # Ensure block_data is a dict if it exists
            block_data = {}

        # Generate the dream content using the provided context
        dream_content = self.generate_dream(context=block_data)

        # Prepare the payload for writing the dream to memory
        memory_payload = {
            "type": "dream", # Categorizes this memory entry as a dream
            "content": dream_content,
            "metadata": {
                "source_event_type": EVENT_ONEIROS_START_DREAM, # What triggered this dream log
                "sleep_block_id": block_data.get("id"),
                "sleep_block_name": block_data.get("name"),
                "sleep_block_type": block_data.get("type"),
                "dream_generation_config": self.config, # Store config used, if any
                "dream_timestamp_utc": datetime.now(timezone.utc).isoformat() # Timestamp of dream generation
            }
        }

        # Publish the dream to memory
        try:
            EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)
            # print(f"OneirosAdapter: Published dream content to memory via '{EVENT_MEMORY_WRITE}'. Dream: '{dream_content[:60]}...'")
        except Exception as e: # pragma: no cover
            print(f"OneirosAdapter Error: Failed to publish dream to EventBus. Exception: {e}")


def register_oneiros_event_handlers(adapter_instance: OneirosAdapter):
    """
    Subscribes OneirosAdapter's event handlers to the global EventBus.

    Args:
        adapter_instance (OneirosAdapter): The instance of the OneirosAdapter whose
                                           handlers need to be registered.
    """
    try:
        event_bus = EventBus.instance()
        event_bus.subscribe(EVENT_ONEIROS_START_DREAM, adapter_instance.handle_start_dream_request)
        # print(f"OneirosAdapter: Successfully registered 'handle_start_dream_request' for {EVENT_ONEIROS_START_DREAM} events.")
    except Exception as e: # pragma: no cover
        print(f"OneirosAdapter Error: Failed to register event handlers with EventBus. Exception: {e}")


if __name__ == '__main__':
    from collections import defaultdict # For MockEventBus

    # Basic test setup for OneirosAdapter event handling
    _test_events_captured_oneiros = [] # Stores {"type": event_type, "data": data_arg}
    def capture_event_for_oneiros_test(event_type_captured, data_captured): # Unique name
        print(f"    [CaptureOneirosTest] Event: {event_type_captured}, Relevant Data: {str(data_captured.get('content', data_captured.get('reason', data_captured)))[:80]}")
        _test_events_captured_oneiros.append({"type": event_type_captured, "data": data_captured})

    # Mock EventBus for isolated testing of this adapter's event interactions
    class MockEventBusForOneiros(EventBus):
        def __init__(self):
            self._subscribers = defaultdict(list) # Initialize subscribers
            print("MockEventBusForOneiros initialized.")

        def publish(self, event_type: str, data: dict):
            # print(f"MockEventBusForOneiros: Publishing {event_type}...")
            # Crucially, call the capture function to log what this adapter would publish
            capture_event_for_oneiros_test(event_type, data)

            # Then, simulate dispatch to actual subscribers that were registered on this mock instance
            # This is important for testing if the handler *itself* works when an event comes in.
            for handler in self._subscribers.get(event_type, []):
                handler(data)
            for handler in self._subscribers.get("*", []): # Wildcard listeners
                handler(event_type, data)

    # Monkey patch EventBus.instance() for this test run
    original_event_bus_instance_method = EventBus.instance
    mock_bus_instance_oneiros = MockEventBusForOneiros()
    EventBus.instance = lambda: mock_bus_instance_oneiros

    # Create an instance of the adapter and register its handlers on the mock bus
    oneiros_adapter_test_instance = OneirosAdapter(oneiros_config={"model_type": "test_model_v1", "allow_basic_fallback": True})
    register_oneiros_event_handlers(adapter_instance=oneiros_adapter_test_instance)

    print("\n--- Testing OneirosAdapter's handle_start_dream_request via Event ---")

    # This is the data that the `schedule` handler would publish for a sleep block
    sleep_block_trigger_data = {
        "reason": "schedule_block_sleep_started", # From schedule.py
        "block_data": { # This is the 'block_data' passed to generate_dream context
            "id": "sleep_block_test_001",
            "name": "Deep Slumber Cycle 1",
            "type": "sleep",
            "start_time_utc": "2023-01-01T22:00:00Z",
            "end_time_utc": "2023-01-02T01:00:00Z" # Example duration
        },
        "trigger_timestamp_utc": datetime.now(timezone.utc).isoformat() # From schedule.py
    }

    # Simulate the EVENT_ONEIROS_START_DREAM event being published on the bus.
    # The mock bus's publish will call our capture_event_for_oneiros_test AND
    # dispatch to oneiros_adapter_test_instance.handle_start_dream_request.
    mock_bus_instance_oneiros.publish(EVENT_ONEIROS_START_DREAM, sleep_block_trigger_data)

    # Verify that handle_start_dream_request (when triggered) published a "dream" memory event
    found_dream_memory_event = False
    for evt in _test_events_captured_oneiros:
        if evt["type"] == EVENT_MEMORY_WRITE and evt["data"].get("type") == "dream":
            found_dream_memory_event = True
            dream_metadata = evt["data"].get("metadata", {})
            print(f"  Verified dream memory event was published by OneirosAdapter:")
            print(f"    Dream Content: '{evt['data']['content'][:70]}...'")
            print(f"    Sleep Block ID in metadata: {dream_metadata.get('sleep_block_id')}")
            assert dream_metadata.get('sleep_block_id') == "sleep_block_test_001", "Sleep block ID mismatch in dream metadata."
            assert dream_metadata.get('source_event_type') == EVENT_ONEIROS_START_DREAM, "Source event type mismatch."
            break
    assert found_dream_memory_event, f"Expected OneirosAdapter to publish an '{EVENT_MEMORY_WRITE}' event with type 'dream', but it was not found in captured events."

    # Restore original EventBus class method
    EventBus.instance = original_event_bus_instance_method
    print("\n--- OneirosAdapter event handling testing finished ---")
