# eidos_agent/features/firmament/tests/test_event_flow.py

import unittest
from collections import defaultdict
# import importlib # To help with reloading if necessary for tests, though usually not needed with good setUp/tearDown

# Attempt to import necessary modules from Firmament.
try:
    from ..core.event_bus import EventBus
    # Import all known event types
    from ..core import event_types as fevent_types # fevent_types to avoid conflict
    from ..core.simulator import run_simulation_tick
    from ..integrations.subconscious_hook import handle_thought_trigger, register_thought_trigger_handler
    from ..integrations.chronos_adapter import _set_current_block_for_testing # Using the testing utility
    # Import the impulse handler and its specific event type strings
    from ..core.event_handlers.impulse import handle_impulse, EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST
    # Import NPC controller for other tests if they are re-enabled
    from ..core.npc_controller import register_npc_event_listeners


except ImportError as e:
    print(f"ImportError in test_event_flow.py: {e}. Some tests may fail or not run correctly.")
    # Define dummy classes/functions if imports fail
    class EventBus: # type: ignore
        _instance = None # type: ignore
        _subscribers = defaultdict(list) # type: ignore
        @classmethod
        def instance(cls): # type: ignore
            if not cls._instance: cls._instance = cls() # type: ignore
            return cls._instance # type: ignore
        def subscribe(self, et, h): pass # type: ignore
        def publish(self, et, d): print(f"DummyEventBus: Published {et} with {d}") # type: ignore

    class fevent_types: # type: ignore
        THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, NPC_DIALOGUE, IMPULSE, SLEEP_REQUESTED = ( # type: ignore
            "dummy.tt", "dummy.we", "dummy.sbs", "dummy.nd", "dummy.imp", "dummy.sr")

    EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST = ( # type: ignore
        "dummy.mw", "dummy.rfp", "dummy.lrr")

    def run_simulation_tick(): pass # type: ignore
    def handle_thought_trigger(p): pass # type: ignore
    def register_thought_trigger_handler(): pass # type: ignore
    def _set_current_block_for_testing(d=None): pass # type: ignore
    def handle_impulse(d): pass # type: ignore
    def register_npc_event_listeners(): pass # type: ignore


class TestEventFlow(unittest.TestCase):

    def setUp(self):
        print(f"\n--- Setting up for: {self._testMethodName} ---")
        # Ensure a fresh EventBus instance for each test
        if hasattr(EventBus, '_instance'):
            EventBus._instance = None
        self.event_bus = EventBus.instance()
        self.event_bus._subscribers = defaultdict(list) # Clear subscribers

        self.recorded_events = defaultdict(list)

        def generic_event_recorder(event_type_arg, data_arg): # Renamed args
            # print(f"    [EventRecorded] Type: {event_type_arg}, Data: {str(data_arg)[:150]}...")
            self.recorded_events[event_type_arg].append(data_arg)

        # Event types to monitor
        self.event_types_to_monitor = [
            fevent_types.THOUGHT_TRIGGER, fevent_types.WORLD_EVENT, fevent_types.SCHEDULE_BLOCK_STARTED,
            EVENT_MEMORY_WRITE, fevent_types.NPC_DIALOGUE, fevent_types.IMPULSE,
            fevent_types.SLEEP_REQUESTED, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST
        ]
        for et in self.event_types_to_monitor:
            # Using a factory to ensure event_t is captured correctly by the lambda
            def create_handler(event_t_captured):
                return lambda data: generic_event_recorder(event_t_captured, data)
            self.event_bus.subscribe(et, create_handler(et))

        # Register core handlers that mediate between events
        register_thought_trigger_handler() # Subscribes handle_thought_trigger to THOUGHT_TRIGGER
        self.event_bus.subscribe(fevent_types.IMPULSE, handle_impulse) # Subscribe impulse handler

        # Register NPC event listeners for other tests if they are active
        # register_npc_event_listeners()

        print("Setup complete. EventBus ready and core handlers (thought_trigger, impulse) registered.")

    def tearDown(self):
        _set_current_block_for_testing(None) # Reset Chronos adapter mock
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance._subscribers = defaultdict(list)
        print(f"--- Torn down: {self._testMethodName} ---")

    # --- Existing test methods (can be kept or adapted) ---
    def test_simulation_tick_starts_schedule_block_event(self):
        print("Running: test_simulation_tick_starts_schedule_block_event")
        test_block_data = {"id": "tsbs001", "name": "SimTick Block", "type": "work"}
        _set_current_block_for_testing(test_block_data)
        run_simulation_tick()
        self.assertIn(fevent_types.SCHEDULE_BLOCK_STARTED, self.recorded_events, "SCHEDULE_BLOCK_STARTED event not found.")
        self.assertGreater(len(self.recorded_events[fevent_types.SCHEDULE_BLOCK_STARTED]), 0)
        self.assertEqual(self.recorded_events[fevent_types.SCHEDULE_BLOCK_STARTED][0]['block']['id'], "tsbs001")
        print("Test Passed: Simulation tick.")

    def test_direct_thought_trigger_leads_to_memory_write(self): # Renamed for clarity
        print("Running: test_direct_thought_trigger_leads_to_memory_write")
        # This test focuses only on subconscious_hook's direct handling of a thought leading to memory,
        # not the full impulse flow that might follow.
        thought_payload = {
            "content": "A car pulled into the driveway then reversed. Weird.",
            "mood": "confused",
            "urgency": "low" # subconscious_hook expects urgency
        }
        # Directly call handle_thought_trigger as it's the entry point from (e.g.) random_events
        handle_thought_trigger(thought_payload)

        self.assertIn(EVENT_MEMORY_WRITE, self.recorded_events, f"{EVENT_MEMORY_WRITE} not found in recorded events.")

        thought_memory_events = [e for e in self.recorded_events[EVENT_MEMORY_WRITE] if e.get("type") == "thought"]
        self.assertGreater(len(thought_memory_events), 0, "No 'thought' type memory event recorded.")

        memory_event = thought_memory_events[0]
        self.assertIn("car's behavior", memory_event.get("content", "").lower(), "Memory content seems unrelated.")
        self.assertEqual(memory_event.get("raw_trigger_content"), thought_payload["content"])
        print("Test Passed: Direct thought trigger to memory write.")

    # --- New tests for impulse handling flow ---
    def test_subconscious_thought_triggers_impulse_and_sleep_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_sleep_action")
        tired_payload = {
            "content": "I'm feeling incredibly tired and should sleep.",
            "mood": "exhausted",
            "urgency": "high",
            "impulse_type": "tired" # Helps subconscious_hook categorize the IMPULSE
        }
        # Step 1: subconscious_hook processes the raw thought
        handle_thought_trigger(tired_payload)

        # Expected flow:
        # 1. handle_thought_trigger -> LLM -> memory.write (elaborated thought)
        # 2. handle_thought_trigger -> publishes IMPULSE event
        # 3. handle_impulse (subscribed to IMPULSE) -> publishes SLEEP_REQUESTED
        # 4. handle_impulse -> publishes memory.write (action taken)

        # Check for memory.write (elaborated thought from subconscious_hook)
        elaborated_thought_mem_events = [
            e for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e.get("type") == "thought" and e.get("raw_trigger_content") == tired_payload["content"]
        ]
        self.assertTrue(len(elaborated_thought_mem_events) >= 1, "No 'thought' memory write for tired impulse's elaborated thought.")

        # Check for IMPULSE event
        self.assertIn(fevent_types.IMPULSE, self.recorded_events, "IMPULSE event not published.")
        impulse_event_data_list = self.recorded_events[fevent_types.IMPULSE]
        self.assertTrue(any(ied.get("type") == "tired" and ied.get("original_thought_content") == tired_payload["content"]
                            for ied in impulse_event_data_list), "Correct 'tired' IMPULSE event not found.")

        # Check for SLEEP_REQUESTED event (published by handle_impulse)
        self.assertIn(fevent_types.SLEEP_REQUESTED, self.recorded_events, "SLEEP_REQUESTED event not published.")
        self.assertTrue(any(sr.get("reason") == "tired_impulse_response"
                            for sr in self.recorded_events[fevent_types.SLEEP_REQUESTED]), "Correct SLEEP_REQUESTED event not found.")

        # Check for memory.write (action taken for impulse, by handle_impulse)
        action_memory_events = [
            e for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e.get("type") == "impulse_response_action" and "Scheduled sleep" in e.get("content", "") and
               e.get("metadata", {}).get("triggering_original_thought") == tired_payload["content"]
        ]
        self.assertTrue(len(action_memory_events) >= 1, "No 'impulse_response_action' memory write for tired impulse action.")
        print("Test Passed: Tired impulse flow (thought -> IMPULSE -> sleep request -> memory log) verified.")

    def test_subconscious_thought_triggers_impulse_and_hunger_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_hunger_action")
        hungry_payload = {
            "content": "I'm really hungry, I need to eat something soon.",
            "mood": "cranky",
            "urgency": "high",
            "impulse_type": "hunger"
        }
        handle_thought_trigger(hungry_payload)

        self.assertIn(fevent_types.IMPULSE, self.recorded_events, "IMPULSE event for hunger not published.")
        self.assertTrue(any(ied.get("type") == "hunger" for ied in self.recorded_events[fevent_types.IMPULSE]))

        self.assertIn(EVENT_REQUEST_FOOD_PREP, self.recorded_events, f"{EVENT_REQUEST_FOOD_PREP} not published.")
        self.assertTrue(any(fr.get("urgency") == "high" for fr in self.recorded_events[EVENT_REQUEST_FOOD_PREP]))

        action_memory_events = [
            e for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e.get("type") == "impulse_response_action" and "Requested food preparation" in e.get("content", "")
        ]
        self.assertTrue(len(action_memory_events) >=1, "No 'impulse_response_action' memory write for hunger impulse.")
        print("Test Passed: Hunger impulse flow verified.")

    def test_subconscious_thought_triggers_impulse_and_curiosity_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_curiosity_action")
        curious_payload = {
            "content": "I should learn about quantum physics.", # This phrase implies action
            "mood": "inquisitive",
            "urgency": "medium",
            "impulse_type": "curiosity" # Explicit type for subconscious_hook
        }
        handle_thought_trigger(curious_payload)

        self.assertIn(fevent_types.IMPULSE, self.recorded_events, "IMPULSE event for curiosity not published.")
        self.assertTrue(any(ied.get("type") == "curiosity" for ied in self.recorded_events[fevent_types.IMPULSE]))

        self.assertIn(EVENT_LOGOS_RESEARCH_REQUEST, self.recorded_events, f"{EVENT_LOGOS_RESEARCH_REQUEST} not published.")
        research_requests = [rr for rr in self.recorded_events[EVENT_LOGOS_RESEARCH_REQUEST] if rr.get("query_topic") == "quantum physics"]
        self.assertTrue(len(research_requests) >= 1, "No research request for 'quantum physics' found.")

        action_memory_events = [
            e for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e.get("type") == "impulse_response_action" and
               "Initiated research request" in e.get("content", "") and
               "quantum physics" in e.get("content", "")
        ]
        self.assertTrue(len(action_memory_events) >=1, "No 'impulse_response_action' memory write for curiosity impulse.")
        print("Test Passed: Curiosity impulse flow verified.")


if __name__ == '__main__':
    unittest.main(verbosity=2)
