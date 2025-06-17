# eidos_agent/features/firmament/tests/test_event_flow.py

import unittest
from collections import defaultdict
from unittest.mock import patch, mock_open # Added mock_open
import io # Not strictly needed with mock_open's read_data, but good for reference
import yaml # For loading mock YAML content if needed by tests directly

# Attempt to import necessary modules from Firmament.
try:
    from ..core.event_bus import EventBus
    from ..core import event_types as fevent_types
    from ..core.simulator import run_simulation_tick
    import eidos_agent.features.firmament.core.simulator as sim_module
    from ..integrations.subconscious_hook import handle_thought_trigger, register_thought_trigger_handler
    from ..integrations.chronos_adapter import _set_current_block_for_testing
    from ..core.event_handlers.impulse import handle_impulse, EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST
    from ..core.event_handlers.schedule import register_schedule_event_handlers
    from ..integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers, EVENT_ONEIROS_START_DREAM
    from ..core.event_handlers.random_events import maybe_trigger_random_event, register_world_event_logging_handler, EVENT_POOL
    # Imports for NPC testing
    from ..core.npc_controller import load_npc_profiles as npc_load_profiles, \
                                       register_npc_event_handlers as npc_register_handlers, \
                                       _npc_profiles_data as npc_profile_storage

except ImportError as e: # pragma: no cover
    print(f"ImportError in test_event_flow.py: {e}.")
    # Dummy definitions
    class EventBus: _instance = None; _subscribers = defaultdict(list); @classmethod def instance(cls): cls._instance = cls._instance or cls(); return cls._instance; subscribe = lambda s,e,h:None; publish = lambda s,e,d:None # type: ignore
    class fevent_types: THOUGHT_TRIGGER, WORLD_EVENT, SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, NPC_DIALOGUE, IMPULSE, SLEEP_REQUESTED = "dummy.tt", "dummy.we", "dummy.sbs", "dummy.sbe", "dummy.nd", "dummy.imp", "dummy.sr" # type: ignore
    EVENT_MEMORY_WRITE, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST, EVENT_ONEIROS_START_DREAM = "dummy.mw", "dummy.rfp", "dummy.lrr", "dummy.osds" # type: ignore
    def run_simulation_tick(): pass; class sim_module: _current_active_block_data = None # type: ignore
    def handle_thought_trigger(p): pass; def register_thought_trigger_handler(): pass # type: ignore
    def _set_current_block_for_testing(d=None): pass; def handle_impulse(d): pass # type: ignore
    def register_schedule_event_handlers(): pass; # type: ignore
    class OneirosAdapter: def generate_dream(self,c=None): return "dummy dream"; def handle_start_dream_request(self,d):pass # type: ignore
    def register_oneiros_event_handlers(a): pass # type: ignore
    def maybe_trigger_random_event(d=None): pass; register_world_event_logging_handler = lambda: None; EVENT_POOL = [] # type: ignore
    # Dummies for NPC testing
    npc_load_profiles = lambda fn='default': False; npc_register_handlers = lambda: None; npc_profile_storage = {} # type: ignore


MOCK_NPC_PROFILES_YAML_CONTENT_FOR_TOOL = """
mailman_bob:
  id: "mailman_bob"
  name: "Mailman Bob"
  description: "Test mailman."
  default_mood: "neutral"
  dialogue_lines:
    greeting_general: ["Hello from Bob!"]
    event_mail_delivery: ["Mail's here, says Bob!", "Package for you!"]
  presence_trigger_events: ["mail_delivery"]

neighbor_alice:
  id: "neighbor_alice"
  name: "Neighbor Alice"
  description: "Test neighbor."
  default_mood: "friendly"
  dialogue_lines:
    greeting_general: ["Hi, I'm Alice!", "Lovely day!"]
    event_gardening_event: ["Alice is gardening."]
    # No specific for loud_noise_nearby, will use general
  presence_trigger_events: ["gardening_event", "loud_noise_nearby"]
"""

class TestEventFlow(unittest.TestCase):

    def setUp(self):
        # print(f"\n--- Setting up for: {self._testMethodName} ---")
        if hasattr(EventBus, '_instance'): EventBus._instance = None
        self.event_bus = EventBus.instance()
        self.event_bus._subscribers = defaultdict(list)
        self.recorded_events = defaultdict(list)

        if hasattr(sim_module, '_current_active_block_data'):
            sim_module._current_active_block_data = None

        # Clear NPC profile storage before each test that might load them
        if 'npc_profile_storage' in globals() and isinstance(npc_profile_storage, dict):
            npc_profile_storage.clear()


        def generic_event_recorder(event_type_arg, data_arg):
            self.recorded_events[event_type_arg].append(data_arg)

        self.event_types_to_monitor = [
            fevent_types.THOUGHT_TRIGGER, fevent_types.WORLD_EVENT,
            fevent_types.SCHEDULE_BLOCK_STARTED, fevent_types.SCHEDULE_BLOCK_ENDED,
            EVENT_MEMORY_WRITE, fevent_types.NPC_DIALOGUE, fevent_types.IMPULSE,
            fevent_types.SLEEP_REQUESTED, EVENT_REQUEST_FOOD_PREP, EVENT_LOGOS_RESEARCH_REQUEST,
            EVENT_ONEIROS_START_DREAM
        ]
        for et in self.event_types_to_monitor:
            def create_handler(event_t_captured): return lambda data: generic_event_recorder(event_t_captured, data)
            self.event_bus.subscribe(et, create_handler(et))

        # Register all core handlers
        register_thought_trigger_handler()
        self.event_bus.subscribe(fevent_types.IMPULSE, handle_impulse)
        register_schedule_event_handlers()

        if 'OneirosAdapter' in globals() and callable(OneirosAdapter): # Check if not dummy
            self.oneiros_adapter = OneirosAdapter(oneiros_config={"test_mode": True})
            if 'register_oneiros_event_handlers' in globals() and callable(register_oneiros_event_handlers):
                 register_oneiros_event_handlers(self.oneiros_adapter)

        if 'register_world_event_logging_handler' in globals() and callable(register_world_event_logging_handler):
            register_world_event_logging_handler()

        # Register NPC handlers
        if 'npc_register_handlers' in globals() and callable(npc_register_handlers):
            npc_register_handlers()
        # print("Setup complete.")

    def tearDown(self):
        _set_current_block_for_testing(None)
        if hasattr(sim_module, '_current_active_block_data'):
             sim_module._current_active_block_data = None
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            EventBus._instance._subscribers = defaultdict(list)
        if 'npc_profile_storage' in globals() and isinstance(npc_profile_storage, dict): # Clear after tests too
            npc_profile_storage.clear()
        # print(f"--- Torn down: {self._testMethodName} ---")

    # --- Existing tests (abridged in prompt, kept full here) ---
    def test_simulation_tick_block_transition(self):
        print("Running: test_simulation_tick_block_transition")
        sim_module._current_active_block_data = None
        block_a_data = {"id": "blockA", "name": "Phase A", "type": "research"}
        _set_current_block_for_testing(block_a_data)
        run_simulation_tick()
        self.assertGreaterEqual(len(self.recorded_events.get(fevent_types.SCHEDULE_BLOCK_STARTED, [])), 1)
        sim_module._current_active_block_data = None
        print("Test Passed: Simulation tick block transitions (basic check).")

    def test_schedule_block_started_logs_to_memory(self):
        print("Running: test_schedule_block_started_logs_to_memory")
        test_block = {"id": "memlog_start_001", "name": "Logging Test Start", "type": "admin", "start_time_utc": "T09:00", "end_time_utc": "T10:00"}
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_STARTED, {"block": test_block})
        self.assertTrue(any(e["type"] == "activity_log_start" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Schedule block started logs to memory.")

    def test_schedule_block_ended_logs_to_memory(self):
        print("Running: test_schedule_block_ended_logs_to_memory")
        test_block = {"id": "memlog_end_002", "name": "Memory Logging Test End", "type": "review"}
        self.event_bus.publish(fevent_types.SCHEDULE_BLOCK_ENDED, {"block": test_block, "reason": "test_reason_completed"})
        self.assertTrue(any(e["type"] == "activity_log_end" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Schedule block ended logs to memory.")

    @patch.object(OneirosAdapter if 'OneirosAdapter' in globals() and callable(OneirosAdapter) else object, 'generate_dream', return_value="A mock dream about lucid coding.")
    def test_sleep_block_triggers_dream_sequence_and_logs_dream(self, mock_g):
        print("Running: test_sleep_block_triggers_dream_sequence_and_logs_dream")
        if not ('OneirosAdapter' in globals() and callable(OneirosAdapter)): self.skipTest("OneirosAdapter dummy used, skipping.") # Skip if dummy
        sim_module._current_active_block_data = None
        sleep_block = {"id": "sleep_test_001", "name": "Nightly Rest", "type": "sleep"}
        _set_current_block_for_testing(sleep_block)
        run_simulation_tick()
        self.assertIn(EVENT_ONEIROS_START_DREAM, self.recorded_events)
        self.assertTrue(any(e["type"] == "dream" for e in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        if hasattr(mock_g, 'assert_called_once'): mock_g.assert_called_once() # Check if mock_g is a real mock
        sim_module._current_active_block_data = None
        print("Test Passed: Sleep block triggers dream and logs dream.")

    def test_subconscious_thought_triggers_impulse_and_sleep_action(self):
        print("Running: test_subconscious_thought_triggers_impulse_and_sleep_action")
        tired_payload = {"content": "I should sleep.", "mood": "exhausted", "urgency": "high", "impulse_type": "tired"}
        handle_thought_trigger(tired_payload)
        self.assertIn(fevent_types.IMPULSE, self.recorded_events)
        self.assertIn(fevent_types.SLEEP_REQUESTED, self.recorded_events)
        print("Test Passed: Subconscious thought triggers impulse and sleep action.")

    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.5)
    def test_maybe_trigger_random_event_does_not_fire(self, mock_random_val):
        print("Running: test_maybe_trigger_random_event_does_not_fire")
        maybe_trigger_random_event()
        self.assertEqual(len(self.recorded_events.get(fevent_types.WORLD_EVENT, [])), 0)
        print("Test Passed: Random event correctly did not fire.")

    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice', return_value="sudden_gust_of_wind")
    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05)
    def test_maybe_trigger_random_event_fires_world_event_only_and_logs_it(self, mock_random_val, mock_random_choice):
        print("Running: test_maybe_trigger_random_event_fires_world_event_only_and_logs_it")
        maybe_trigger_random_event()
        self.assertTrue(any(e["event_name"] == "sudden_gust_of_wind" for e in self.recorded_events.get(fevent_types.WORLD_EVENT, [])))
        self.assertTrue(any(mw.get("type") == "observed_world_event" for mw in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Random event fired WORLD_EVENT only and it was logged.")

    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.choice', return_value="phone_buzzes_on_table")
    @patch('eidos_agent.features.firmament.core.event_handlers.random_events.random.random', return_value=0.05)
    def test_maybe_trigger_random_event_fires_world_event_and_thought_and_logs_world_event(self, mock_random_val, mock_random_choice):
        print("Running: test_maybe_trigger_random_event_fires_world_event_and_thought_and_logs_world_event")
        maybe_trigger_random_event()
        self.assertTrue(any(e["event_name"] == "phone_buzzes_on_table" for e in self.recorded_events.get(fevent_types.WORLD_EVENT, [])))
        self.assertTrue(any(e["trigger_event_name"] == "phone_buzzes_on_table" for e in self.recorded_events.get(fevent_types.THOUGHT_TRIGGER, [])))
        self.assertGreaterEqual(len(self.recorded_events.get(EVENT_MEMORY_WRITE, [])), 2) # For world event and thought
        print("Test Passed: Random event fired WORLD_EVENT, THOUGHT_TRIGGER, and world event was logged.")

    def test_handle_world_event_logging_creates_memory_entry_directly(self):
        print("Running: test_handle_world_event_logging_creates_memory_entry_directly")
        world_event_data = {"event_name": "direct_log_test_event", "source": "test_logging_direct"}
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_data)
        self.assertTrue(any(mw.get("type") == "observed_world_event" and mw["metadata"].get("original_world_event_name") == "direct_log_test_event"
                            for mw in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: Direct world event logging correctly created memory entry.")

    # --- New Tests for NPC Interactions ---
    @patch('builtins.open', new_callable=mock_open, read_data=MOCK_NPC_PROFILES_YAML_CONTENT_FOR_TOOL)
    def test_npc_load_profiles_with_mock_data(self, mock_file_open_method):
        print("Running: test_npc_load_profiles_with_mock_data")
        if not ('npc_load_profiles' in globals() and callable(npc_load_profiles) and npc_load_profiles.__module__ != __name__):
            self.skipTest("npc_load_profiles dummy used or not available, skipping.")

        npc_profile_storage.clear() # Ensure clean state for this test
        success = npc_load_profiles("any_filename_for_mock.yaml")

        self.assertTrue(success, "NPC profile loading failed using mock data.")
        self.assertIn("mailman_bob", npc_profile_storage, "mailman_bob profile not found in storage.")
        if "mailman_bob" in npc_profile_storage: # Avoid KeyError if previous assert fails
            self.assertEqual(npc_profile_storage["mailman_bob"]["name"], "Mailman Bob")
        self.assertIn("neighbor_alice", npc_profile_storage, "neighbor_alice profile not found.")
        mock_file_open_method.assert_called_once() # Check that open was called (it's mocked)
        print("Test Passed: NPC profiles loaded with mock data.")

    @patch('builtins.open', new_callable=mock_open, read_data=MOCK_NPC_PROFILES_YAML_CONTENT_FOR_TOOL)
    def test_npc_triggered_by_world_event_and_logs_presence(self, mock_file_open_method):
        print("Running: test_npc_triggered_by_world_event_and_logs_presence")
        if not ('npc_load_profiles' in globals() and callable(npc_load_profiles) and npc_load_profiles.__module__ != __name__):
            self.skipTest("npc_load_profiles dummy used or not available, skipping.")

        npc_profile_storage.clear()
        load_success = npc_load_profiles("mocked.yaml")
        self.assertTrue(load_success, "Pre-test NPC profile loading failed.")
        self.assertTrue(npc_profile_storage.get("mailman_bob"), "Mailman Bob profile not loaded for test.")

        world_event_data = {"event_name": "mail_delivery", "source": "test_suite_npc_trigger"}
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_data)

        npc_dialogues = self.recorded_events.get(fevent_types.NPC_DIALOGUE, [])
        self.assertEqual(len(npc_dialogues), 1, "Expected 1 NPC_DIALOGUE event for mail_delivery.")
        if npc_dialogues: # Check content only if event exists
            bob_dialogue = npc_dialogues[0]
            self.assertEqual(bob_dialogue["npc_id"], "mailman_bob")
            self.assertEqual(bob_dialogue["npc_name"], "Mailman Bob")
            # Ensure the chosen line is one of the possibilities for event_mail_delivery
            self.assertIn(bob_dialogue["line"], npc_profile_storage["mailman_bob"]["dialogue_lines"]["event_mail_delivery"])
            self.assertEqual(bob_dialogue["triggering_event_name"], "mail_delivery")

        npc_presence_logs = [
            e_data for e_data in self.recorded_events.get(EVENT_MEMORY_WRITE, [])
            if e_data.get("type") == "npc_presence" and e_data.get("metadata", {}).get("npc_id") == "mailman_bob"
        ]
        self.assertEqual(len(npc_presence_logs), 1, "Expected 1 npc_presence memory log for Mailman Bob.")
        if npc_presence_logs: # Check content only if log exists
            self.assertIn("Mailman Bob is present due to 'mail_delivery'", npc_presence_logs[0]["content"])
        print("Test Passed: NPC triggered by world event, dialogue published, presence logged.")

    @patch('builtins.open', new_callable=mock_open, read_data=MOCK_NPC_PROFILES_YAML_CONTENT_FOR_TOOL)
    def test_npc_dialogue_selection_event_specific_vs_general(self, mock_file_open_method):
        print("Running: test_npc_dialogue_selection_event_specific_vs_general")
        if not ('npc_load_profiles' in globals() and callable(npc_load_profiles) and npc_load_profiles.__module__ != __name__):
            self.skipTest("npc_load_profiles dummy used or not available, skipping.")
        npc_profile_storage.clear()
        npc_load_profiles("mocked.yaml")

        # Test 1: Mailman Bob - event_mail_delivery (specific)
        self.recorded_events.clear()
        world_event_mail = {"event_name": "mail_delivery", "source": "test_suite_dialogue_sel"}
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_mail)
        bob_dialogues = self.recorded_events.get(fevent_types.NPC_DIALOGUE, [])
        self.assertEqual(len(bob_dialogues), 1)
        self.assertEqual(bob_dialogues[0]["npc_id"], "mailman_bob")
        self.assertIn(bob_dialogues[0]["line"], npc_profile_storage["mailman_bob"]["dialogue_lines"]["event_mail_delivery"])

        # Test 2: Neighbor Alice - loud_noise_nearby (should use general greeting as no specific event_loud_noise_nearby dialogue)
        self.recorded_events.clear()
        world_event_noise = {"event_name": "loud_noise_nearby", "source": "test_suite_dialogue_sel"}
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_noise)
        alice_dialogues = self.recorded_events.get(fevent_types.NPC_DIALOGUE, [])
        self.assertEqual(len(alice_dialogues), 1)
        self.assertEqual(alice_dialogues[0]["npc_id"], "neighbor_alice")
        self.assertIn(alice_dialogues[0]["line"], npc_profile_storage["neighbor_alice"]["dialogue_lines"]["greeting_general"])
        print("Test Passed: NPC dialogue selection logic (event-specific vs general).")

    @patch('builtins.open', new_callable=mock_open, read_data=MOCK_NPC_PROFILES_YAML_CONTENT_FOR_TOOL)
    def test_npc_not_triggered_by_unrelated_world_event(self, mock_file_open_method):
        print("Running: test_npc_not_triggered_by_unrelated_world_event")
        if not ('npc_load_profiles' in globals() and callable(npc_load_profiles) and npc_load_profiles.__module__ != __name__):
            self.skipTest("npc_load_profiles dummy used or not available, skipping.")
        npc_profile_storage.clear()
        npc_load_profiles("mocked.yaml")

        world_event_unrelated = {"event_name": "birds_singing_peacefully", "source": "test_suite_unrelated"}
        self.event_bus.publish(fevent_types.WORLD_EVENT, world_event_unrelated)

        self.assertEqual(len(self.recorded_events.get(fevent_types.NPC_DIALOGUE, [])), 0)
        self.assertFalse(any(e_data.get("type") == "npc_presence" for e_data in self.recorded_events.get(EVENT_MEMORY_WRITE, [])))
        print("Test Passed: NPC not triggered by unrelated event.")


if __name__ == '__main__': # pragma: no cover
    unittest.main(verbosity=2)
