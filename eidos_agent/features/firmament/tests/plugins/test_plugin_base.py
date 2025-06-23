# eidos_agent/features/firmament/tests/plugins/test_plugin_base.py

import unittest
import logging
from unittest.mock import MagicMock, patch # Added patch
from typing import Dict, Any, Optional # For type hints

# Adjust import path based on actual file structure
# Assuming tests/plugins/ is a subdir of tests/, and firmament/plugins/ is features/firmament/plugins/
try:
    # Path assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.plugins.plugin_base import FirmamentPluginBase
    # For type hinting if needed by concrete example. These are Any in base, so not strictly needed here
    # but good for completeness if the concrete example uses them with specific types.
    from eidos_agent.features.firmament.core.event_bus import EventBus
    from eidos_agent.features.firmament.npcs.npc_registry import NPCRegistry
except ImportError: # pragma: no cover
    print("CRITICAL: Could not resolve imports for FirmamentPluginBase test. Using dummy class.")
    # Define a dummy FirmamentPluginBase and other types if imports fail, to allow parsing.
    class FirmamentPluginBase: #type:ignore
        def __init__(self, plugin_name: str, firmament_config: Optional[Dict[str, Any]]=None, plugin_specific_config: Optional[Dict[str, Any]]=None):
            self.plugin_name = plugin_name
            self.firmament_config = firmament_config if firmament_config is not None else {}
            self.plugin_specific_config = plugin_specific_config if plugin_specific_config is not None else {}
            self.is_setup_complete = False
            self.logger = MagicMock(spec=logging.Logger)
            self.logger.name = f"firmament.plugin.{plugin_name}" # Simulate logger name
            # self.logger.info(f"Dummy FirmamentPluginBase '{plugin_name}' initialized.")

        def setup(self, event_bus: Any, npc_registry: Any) -> bool:
            self.logger.info("Dummy FirmamentPluginBase setup called.")
            self.is_setup_complete = True # Dummy setup always succeeds
            return True

        def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
            self.logger.debug(f"Dummy FirmamentPluginBase update_on_tick for {self.plugin_name}.")
            pass

        def get_status(self) -> Dict[str, Any]:
            return {"plugin_name": self.plugin_name, "is_setup_complete": self.is_setup_complete, "status_message": "Dummy base status."}

        def shutdown(self) -> None:
            self.logger.info(f"Dummy FirmamentPluginBase shutdown for {self.plugin_name}.")
            pass

    EventBus = MagicMock(name="MockEventBusForBaseTest") #type:ignore
    NPCRegistry = MagicMock(name="MockNPCRegistryForBaseTest") #type:ignore


# A concrete implementation for testing purposes
class ConcreteTestPlugin(FirmamentPluginBase):
    """A concrete plugin implementation for testing FirmamentPluginBase."""
    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        # Call super's setup if it had any logic, though it's abstract in base
        # For this test, we'll assume base setup does nothing if called.
        # super().setup(event_bus, npc_registry) # Not strictly needed as base is abstract
        self.logger.info(f"ConcreteTestPlugin '{self.plugin_name}' setup method called.")
        self.is_setup_complete = True # Mark as setup
        # Store references if other methods of this concrete plugin need them
        self.event_bus_ref = event_bus
        self.npc_registry_ref = npc_registry
        return True # Indicate successful setup

    def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
        super().update_on_tick(current_time_iso, active_block) # Test calling super's default
        self.logger.info(f"ConcreteTestPlugin '{self.plugin_name}' specific tick update logic executed.")

    def get_status(self) -> dict:
        status = super().get_status() # Get base status
        status["custom_status_field"] = "concrete_plugin_is_active" # Add specific status
        status["status_message"] = "ConcreteTestPlugin reporting operational." # Override base message
        return status

    def shutdown(self) -> None:
        super().shutdown() # Test calling super's default for logging
        self.logger.info(f"ConcreteTestPlugin '{self.plugin_name}' specific shutdown actions performed.")


class TestFirmamentPluginBase(unittest.TestCase):

    def test_plugin_initialization(self):
        print("Running: test_plugin_initialization")
        plugin_name = "TestPluginForInitialization"
        fm_config = {"globalKey": "globalValueForFirmament"}
        ps_config = {"localKeyForPlugin": "localValueForPlugin"}

        plugin = ConcreteTestPlugin(plugin_name, fm_config, ps_config)

        self.assertEqual(plugin.plugin_name, plugin_name)
        self.assertEqual(plugin.firmament_config, fm_config)
        self.assertEqual(plugin.plugin_specific_config, ps_config)
        self.assertFalse(plugin.is_setup_complete, "is_setup_complete should be False after __init__.")
        self.assertIsNotNone(plugin.logger, "Logger should be initialized.")
        self.assertEqual(plugin.logger.name, f"firmament.plugin.{plugin_name}", "Logger name mismatch.")
        print("Test Passed: Plugin initialized with correct attributes and defaults.")

    def test_setup_method_on_concrete_plugin(self): # Renamed for clarity
        print("Running: test_setup_method_on_concrete_plugin")
        plugin = ConcreteTestPlugin("SetupMethodTestPlugin")
        # Create MagicMock instances for EventBus and NPCRegistry for this test
        mock_event_bus_instance = MagicMock(spec=EventBus)
        mock_npc_registry_instance = MagicMock(spec=NPCRegistry)

        self.assertFalse(plugin.is_setup_complete, "is_setup_complete should be False before setup.")
        setup_result = plugin.setup(mock_event_bus_instance, mock_npc_registry_instance)

        self.assertTrue(setup_result, "Concrete plugin's setup method should return True.")
        self.assertTrue(plugin.is_setup_complete, "is_setup_complete should be True after successful setup.")
        self.assertEqual(plugin.event_bus_ref, mock_event_bus_instance, "EventBus reference not stored by concrete plugin.")
        self.assertEqual(plugin.npc_registry_ref, mock_npc_registry_instance, "NPCRegistry reference not stored.")
        # Check if logger was used in setup (as per ConcreteTestPlugin's implementation)
        plugin.logger.info.assert_any_call(f"ConcreteTestPlugin '{plugin.plugin_name}' setup method called.")
        print("Test Passed: Concrete plugin's setup method executed, set flag, and stored refs.")


    def test_update_on_tick_behavior(self): # Renamed for clarity
        print("Running: test_update_on_tick_behavior")
        plugin = ConcreteTestPlugin("TickUpdateTestPlugin")

        # Patch the plugin's own logger to check calls
        with patch.object(plugin.logger, 'info') as mock_log_info_tick, \
             patch.object(plugin.logger, 'debug') as mock_log_debug_tick: # Base class uses debug if un-commented

            plugin.update_on_tick("2023-01-01T00:00:00Z", None)

            # Check if ConcreteTestPlugin's specific log message was called
            mock_log_info_tick.assert_any_call(f"ConcreteTestPlugin '{plugin.plugin_name}' specific tick update logic executed.")
            # Check if base class's (commented out) debug log for update_on_tick was NOT called if it remained commented
            # If it were active: mock_log_debug_tick.assert_any_call(f"Plugin '{plugin.plugin_name}' update_on_tick called at 2023-01-01T00:00:00Z.")
            # For now, we just ensure it runs without error and concrete part is logged.

        print("Test Passed: update_on_tick executed (check logs for specifics).")

    def test_get_status_behavior(self): # Renamed for clarity
        print("Running: test_get_status_behavior")
        plugin_name = "StatusReportingTestPlugin"
        plugin = ConcreteTestPlugin(plugin_name)
        plugin.is_setup_complete = True # Simulate setup being complete for status

        status = plugin.get_status()

        self.assertIn("plugin_name", status, "plugin_name missing from status.")
        self.assertEqual(status["plugin_name"], plugin_name)
        self.assertIn("is_setup_complete", status, "is_setup_complete missing from status.")
        self.assertTrue(status["is_setup_complete"])
        self.assertIn("status_message", status, "status_message missing from status.")
        self.assertEqual(status["status_message"], "ConcreteTestPlugin reporting operational.") # Overridden by concrete
        self.assertIn("custom_status_field", status, "Custom field from concrete plugin missing.")
        self.assertEqual(status["custom_status_field"], "concrete_plugin_is_active")
        print("Test Passed: get_status returned expected base and concrete plugin fields.")

    def test_shutdown_behavior(self): # Renamed for clarity
        print("Running: test_shutdown_behavior")
        plugin = ConcreteTestPlugin("ShutdownActionTestPlugin")

        with patch.object(plugin.logger, 'info') as mock_log_info_shutdown:
            plugin.shutdown()

            # Check that both the base class log (via super call) and concrete class log were made
            # Base class logs: "Plugin '{self.plugin_name}' shutdown method called."
            # Concrete logs: "ConcreteTestPlugin '{self.plugin_name}' specific shutdown actions performed."

            # Convert call_args_list to a list of strings for easier checking
            logged_messages = [args[0] for args, kwargs in mock_log_info_shutdown.call_args_list]

            self.assertTrue(any(f"Plugin '{plugin.plugin_name}' shutdown method called." in msg for msg in logged_messages),
                            "Base class shutdown log not found.")
            self.assertTrue(any(f"ConcreteTestPlugin '{plugin.plugin_name}' specific shutdown actions performed." in msg for msg in logged_messages),
                            "Concrete plugin shutdown log not found.")
        print("Test Passed: shutdown executed and logged messages from base and concrete implementation.")

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # To see all logs from plugin's logger, including base class calls
    unittest.main(verbosity=2)
