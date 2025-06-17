# eidos_agent/features/firmament/tests/plugins/enabled/test_example_plugin.py

import unittest
from unittest.mock import MagicMock, patch, call # Added call
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

# Adjust import path for ExampleFirmamentPlugin and its dependencies
# This file: firmament/tests/plugins/enabled/test_example_plugin.py
# Plugin:    firmament/plugins/enabled/example_plugin.py
# Base:      firmament/plugins/plugin_base.py
# Core:      firmament/core/
# NPCs:      firmament/npcs/
try:
    # Path assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.plugins.enabled.example_plugin import ExampleFirmamentPlugin

    # Types needed for mocks and type hinting in plugin's setup method
    # These are forward declared in plugin_base, so actual classes are fine here for spec
    if TYPE_CHECKING: # pragma: no cover
        from eidos_agent.features.firmament.core.event_bus import EventBus
        from eidos_agent.features.firmament.npcs.npc_registry import NPCRegistry
    # Event types used by the plugin
    from eidos_agent.features.firmament.core.event_types import WORLD_EVENT, THOUGHT_TRIGGER, MOOD_UPDATED

except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not resolve imports for ExampleFirmamentPlugin test: {e}. Using dummy classes.")
    # Define dummy versions of all imported classes if imports fail
    class FirmamentPluginBaseDummy: # Renamed to avoid conflict if base is also dummied elsewhere
        def __init__(self,plugin_name,firmament_config=None,plugin_specific_config=None):
            self.plugin_name=plugin_name; self.plugin_specific_config=plugin_specific_config or {}
            self.firmament_config = firmament_config or {}
            self.logger=MagicMock(spec=logging.Logger); self.is_setup_complete=False
        def setup(self,eb,nr): self.is_setup_complete=True; return True
        def update_on_tick(self,t,ab=None):pass; def get_status(self):return{}; def shutdown(self):pass

    class ExampleFirmamentPlugin(FirmamentPluginBaseDummy): #type:ignore
        PLUGIN_NAME = "DummyExamplePluginForTest"
        PLUGIN_VERSION = "0.0.0-dummy"
        def __init__(self,plugin_name,firmament_config=None,plugin_specific_config=None):
            super().__init__(plugin_name,firmament_config,plugin_specific_config)
            self.event_bus=None; self.npc_registry=None
            self.events_handled_count=0; self.tick_updates_received=0
        def setup(self,eb,nr): self.event_bus=eb; self.npc_registry=nr; self.is_setup_complete=True; return True
        def handle_world_event(self,d):self.events_handled_count+=1
        def handle_thought_trigger_example(self,d):self.events_handled_count+=1
        def handle_mood_update_example(self,d):self.events_handled_count+=1
        def update_on_tick(self,t,ab=None):self.tick_updates_received+=1
        def get_status(self):return super().get_status()
        def shutdown(self):super().shutdown()

    EventBus=MagicMock(name="DummyEventBusForExamplePluginTest") #type:ignore
    NPCRegistry=MagicMock(name="DummyNPCRegistryForExamplePluginTest") #type:ignore
    WORLD_EVENT="dummy.world_event_example"; THOUGHT_TRIGGER="dummy.thought_trigger_example"; MOOD_UPDATED="dummy.mood_updated_example" #type:ignore


class TestExampleFirmamentPlugin(unittest.TestCase):

    def setUp(self):
        # Create fresh mocks for each test
        self.mock_event_bus = MagicMock(spec=EventBus if 'EventBus' in globals() and EventBus.__name__ != 'MagicMock' else object)
        self.mock_npc_registry = MagicMock(spec=NPCRegistry if 'NPCRegistry' in globals() and NPCRegistry.__name__ != 'MagicMock' else object)

        self.plugin_name_for_test = "TestExamplePluginInstance007"
        self.firmament_config_for_test = {"global_setting": "firmament_wide_value_for_test"}
        self.plugin_specific_config_for_test = {
            "target_world_event_for_reaction": "phone_buzzes_on_table",
            "subscribe_to_mood_updates": True,
            "reaction_mood": "curious_plugin_reaction",
            "log_tick_frequency": 5 # Test with a different frequency
        }

        # Instantiate the actual plugin (or its dummy if imports failed)
        self.plugin = ExampleFirmamentPlugin(
            plugin_name=self.plugin_name_for_test, # Pass the name, PluginManager would use PLUGIN_NAME or class name
            firmament_config=self.firmament_config_for_test,
            plugin_specific_config=self.plugin_specific_config_for_test
        )
        # print(f"Setup for {self.plugin.plugin_name}")

    def test_plugin_initialization(self):
        print("Running: test_plugin_initialization (ExamplePlugin)")
        self.assertEqual(self.plugin.plugin_name, self.plugin_name_for_test)
        self.assertEqual(self.plugin.firmament_config, self.firmament_config_for_test)
        self.assertEqual(self.plugin.plugin_specific_config, self.plugin_specific_config_for_test)
        self.assertFalse(self.plugin.is_setup_complete)
        self.assertEqual(self.plugin.events_handled_count, 0)
        self.assertEqual(self.plugin.tick_updates_received, 0)
        self.assertIsNotNone(self.plugin.logger)
        # The logger name is set in FirmamentPluginBase init
        self.assertEqual(self.plugin.logger.name, f"firmament.plugin.{self.plugin_name_for_test}")
        print("Test Passed: ExamplePlugin initialized correctly.")

    def test_setup_subscribes_to_events_based_on_config(self):
        print("Running: test_setup_subscribes_to_events_based_on_config (ExamplePlugin)")
        setup_result = self.plugin.setup(self.mock_event_bus, self.mock_npc_registry)

        self.assertTrue(setup_result, "Plugin setup should return True.")
        self.assertTrue(self.plugin.is_setup_complete, "is_setup_complete should be True after setup.")
        self.assertEqual(self.plugin.event_bus, self.mock_event_bus, "EventBus instance not stored in plugin.")

        expected_calls = [
            call(WORLD_EVENT, self.plugin.handle_world_event),
            call(THOUGHT_TRIGGER, self.plugin.handle_thought_trigger_example)
        ]
        if self.plugin_specific_config_for_test.get("subscribe_to_mood_updates"):
            expected_calls.append(call(MOOD_UPDATED, self.plugin.handle_mood_update_example))

        self.mock_event_bus.subscribe.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(self.mock_event_bus.subscribe.call_count, len(expected_calls),
                         "Incorrect number of event subscriptions.")
        print(f"Test Passed: ExamplePlugin setup subscribed to {len(expected_calls)} events as per config.")


    def test_handle_world_event_reacts_to_configured_target_event(self):
        print("Running: test_handle_world_event_reacts_to_configured_target_event (ExamplePlugin)")
        self.plugin.setup(self.mock_event_bus, self.mock_npc_registry) # Call setup to store event_bus

        target_event_name = self.plugin_specific_config_for_test.get("target_world_event_for_reaction")
        world_event_data_target = {"event_name": target_event_name, "detail": "A specific test buzz"}

        self.plugin.handle_world_event(world_event_data_target)

        self.assertEqual(self.plugin.events_handled_count, 1)
        # Check if it published a THOUGHT_TRIGGER for the target event
        self.mock_event_bus.publish.assert_called_once()
        published_event_type, published_data = self.mock_event_bus.publish.call_args[0]

        self.assertEqual(published_event_type, THOUGHT_TRIGGER)
        self.assertIn(target_event_name, published_data.get("content", ""))
        self.assertEqual(published_data.get("source"), self.plugin.plugin_name) # Plugin name should be from instance
        self.assertEqual(published_data.get("mood"), self.plugin_specific_config_for_test.get("reaction_mood"))
        print("Test Passed: handle_world_event reacted to target and published a thought.")

    def test_handle_world_event_no_reaction_for_other_event(self):
        print("Running: test_handle_world_event_no_reaction_for_other_event (ExamplePlugin)")
        self.plugin.setup(self.mock_event_bus, self.mock_npc_registry) # Call setup

        other_event_data = {"event_name": "some_other_unrelated_event", "detail": "Nothing special"}
        self.plugin.handle_world_event(other_event_data)

        self.assertEqual(self.plugin.events_handled_count, 1)
        self.mock_event_bus.publish.assert_not_called() # Should NOT publish for an unrelated event
        print("Test Passed: handle_world_event correctly ignored an unrelated event.")


    def test_update_on_tick_logging_and_counter_with_config_frequency(self):
        print("Running: test_update_on_tick_logging_and_counter_with_config_frequency (ExamplePlugin)")
        log_freq = self.plugin_specific_config_for_test.get("log_tick_frequency", 10)
        num_ticks = log_freq * 2 + 1 # e.g., if freq is 5, run 11 ticks to get 2 logs (at tick 5, 10)

        with patch.object(self.plugin.logger, 'info') as mock_log_info_ontick:
            for i in range(1, num_ticks + 1): # Ticks are 1-indexed for logging in example
                self.plugin.update_on_tick(f"2023-01-01T00:00:{i:02d}Z", None)

        self.assertEqual(self.plugin.tick_updates_received, num_ticks)

        # Check how many times the specific periodic log message occurred
        periodic_log_count = 0
        for call_arg_tuple in mock_log_info_ontick.call_args_list:
            logged_message = call_arg_tuple[0][0] # First positional argument of the call
            if f"received tick update #" in logged_message:
                periodic_log_count += 1

        expected_periodic_logs = num_ticks // log_freq
        self.assertEqual(periodic_log_count, expected_periodic_logs,
                         f"Expected {expected_periodic_logs} periodic log messages for {num_ticks} ticks with freq {log_freq}.")
        print(f"Test Passed: update_on_tick increments counter and logs periodically ({periodic_log_count} times).")

    def test_get_status_includes_plugin_specifics_and_version(self):
        print("Running: test_get_status_includes_plugin_specifics_and_version (ExamplePlugin)")
        self.plugin.is_setup_complete = True
        self.plugin.events_handled_count = 7
        self.plugin.tick_updates_received = 23

        status = self.plugin.get_status()

        self.assertEqual(status.get("plugin_name"), self.plugin_name_for_test)
        self.assertTrue(status.get("is_setup_complete"))
        self.assertEqual(status.get("version"), ExampleFirmamentPlugin.PLUGIN_VERSION) # Check version
        self.assertEqual(status.get("events_handled_count"), 7)
        self.assertEqual(status.get("tick_updates_received"), 23)
        self.assertIn(self.plugin_specific_config_for_test.get("target_world_event_for_reaction"),
                      status.get("target_world_event_for_reaction", ""))
        self.assertIn("operational and monitoring", status.get("custom_message", ""))
        print("Test Passed: get_status includes all expected fields including version.")

    def test_shutdown_logs_messages_from_base_and_concrete(self):
        print("Running: test_shutdown_logs_messages_from_base_and_concrete (ExamplePlugin)")
        with patch.object(self.plugin.logger, 'info') as mock_log_info_shutdown_test:
            self.plugin.shutdown()

            logged_messages = [args[0] for args, kwargs in mock_log_info_shutdown_test.call_args_list]
            # Base class (via super) logs: "Plugin '{self.plugin_name}' shutdown method called."
            self.assertTrue(any(f"Plugin '{self.plugin.plugin_name}' shutdown method called" in msg for msg in logged_messages),
                            "Base class shutdown log missing.")
            # Concrete class logs: "'{self.plugin_name}' specific shutdown actions completed (if any)."
            self.assertTrue(any(f"'{self.plugin.plugin_name}' specific shutdown actions completed" in msg for msg in logged_messages),
                            "Concrete plugin shutdown log missing.")
        print("Test Passed: shutdown method logs correctly from both base and concrete plugin.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    # To see DEBUG logs from the plugin itself during test:
    # logging.getLogger(f"firmament.plugin.{TestExampleFirmamentPlugin().plugin_name_for_test}").setLevel(logging.DEBUG) # Needs instance name or hardcode
    # Or more generally for all plugin loggers:
    # logging.getLogger('firmament.plugin').setLevel(logging.DEBUG)
    unittest.main(verbosity=2)
