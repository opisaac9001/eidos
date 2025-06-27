# eidos_agent/features/firmament/plugins/plugin_base.py
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TYPE_CHECKING

# Forward type declarations for type hinting to avoid circular imports
# These actual classes will be passed in by the PluginManager or a similar mechanism.
if TYPE_CHECKING: # pragma: no cover
    from ..core.event_bus import EventBus # type: ignore
    from ..npcs.npc_registry import NPCRegistry # type: ignore
    # If FirmamentModuleConfig is a specific TypedDict or Pydantic model, import it here for type checking.
    # from ....core.config import FirmamentModuleConfig # Example if it exists and is needed by plugins

logger = logging.getLogger(__name__) # Module-level logger

class FirmamentPluginBase(ABC):
    """
    Abstract base class for all Firmament plugins.
    Plugins should inherit from this class and implement the required methods,
    particularly `setup`.
    """
    def __init__(
        self,
        plugin_name: str,
        firmament_config: Optional[Dict[str, Any]] = None,
        plugin_specific_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initializes the plugin. This is typically called by a plugin manager.

        Args:
            plugin_name (str): The unique name of the plugin (e.g., derived from its module name).
            firmament_config (Optional[Dict[str, Any]]): A reference to the main Firmament
                                                         module's configuration (if available and needed).
            plugin_specific_config (Optional[Dict[str, Any]]): A dictionary containing
                                                               configuration specific to this plugin,
                                                               often loaded from a plugin config file.
        """
        self.plugin_name = plugin_name
        self.firmament_config = firmament_config if firmament_config is not None else {}
        self.plugin_specific_config = plugin_specific_config if plugin_specific_config is not None else {}
        self.is_setup_complete = False # Tracks if the setup method was called and completed successfully

        # Plugin-specific logger instance for better log filtering and identification
        self.logger = logging.getLogger(f"firmament.plugin.{self.plugin_name}")
        self.logger.info(f"Plugin '{self.plugin_name}' instance initialized.")

    @abstractmethod
    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        """
        Called by the PluginManager to initialize the plugin after it's loaded.
        This method is where the plugin should perform its primary setup, such as
        subscribing to events or preparing resources.

        Args:
            event_bus (EventBus): An instance of the Firmament EventBus for event interactions.
            npc_registry (NPCRegistry): An instance of the Firmament NPCRegistry for NPC data access.

        Returns:
            bool: True if setup was successful, False otherwise. If False, the plugin
                  manager might not activate the plugin or might log an error.
        """
        self.logger.debug(f"Plugin '{self.plugin_name}' abstract setup method called (should be overridden).")
        pass # pragma: no cover (as it's abstract and should be implemented by subclasses)

    def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
        """
        Optional method called by the PluginManager on every simulation tick
        for plugins that need to perform periodic actions or updates based on time.

        Args:
            current_time_iso (str): The current simulation time as an ISO formatted string.
            active_block (Optional[Dict[str, Any]]): The data of the currently active
                                                     schedule block from the simulator,
                                                     or None if no block is currently active.
        """
        # self.logger.debug(f"Plugin '{self.plugin_name}' update_on_tick called at {current_time_iso}.")
        # Default implementation does nothing. Subclasses can override this if needed.
        pass

    def get_status(self) -> Dict[str, Any]:
        """
        Optional method for plugins to report their current status, internal state,
        or other diagnostic information. Useful for monitoring or debugging.

        Returns:
            Dict[str, Any]: A dictionary representing the plugin's status.
                            It's recommended to include at least basic information like
                            'plugin_name' and 'is_setup_complete'.
        """
        return {
            "plugin_name": self.plugin_name,
            "is_setup_complete": self.is_setup_complete,
            "status_message": "Basic status from FirmamentPluginBase."
        }

    def shutdown(self) -> None:
        """
        Optional method called by the PluginManager when Firmament is shutting down
        or when the plugin is being unloaded. Plugins can use this to clean up
        resources (e.g., close files, release network connections, save state).
        """
        self.logger.info(f"Plugin '{self.plugin_name}' shutdown method called.")
        # Default implementation does nothing. Subclasses can override.
        pass

if __name__ == '__main__': # pragma: no cover
    # This block demonstrates how a concrete plugin might be implemented and tested.
    # It's for illustrative purposes and direct testing of the base class structure.

    # Mock EventBus and NPCRegistry for local testing of the example plugin
    # These mocks simulate the objects that would be passed by a real PluginManager.
    class MockEventBusForPluginTest:
        def __init__(self): self.subscriptions = {}
        def subscribe(self, event_type, handler):
            self.subscriptions.setdefault(event_type, []).append(handler)
            print(f"MockEventBus: Handler '{handler.__name__ if hasattr(handler, '__name__') else str(handler)}' subscribed to '{event_type}'")
        def publish(self, event_type, data):
            print(f"MockEventBus: Event '{event_type}' published with data: {data}")
            if event_type in self.subscriptions:
                for handler in self.subscriptions[event_type]:
                    handler(data) # Call the subscribed handler

    class MockNPCRegistryForPluginTest:
        def list_known_npc_ids(self): return ["npc_mock_001", "npc_mock_002"]
        def get_npc_by_id(self, npc_id):
            if npc_id == "npc_mock_001": return {"id": npc_id, "name": "Mock NPC One"}
            return None

    # Define a concrete example plugin inheriting from the base class
    class MyExampleFirmamentPlugin(FirmamentPluginBase):
        def __init__(self, plugin_name: str, firmament_config=None, plugin_specific_config=None):
            super().__init__(plugin_name, firmament_config, plugin_specific_config)
            self.tick_updates_received = 0
            self.dummy_events_handled = 0
            self.logger.info("MyExampleFirmamentPlugin specific initialization done.")

        def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
            self.logger.info(f"MyExampleFirmamentPlugin '{self.plugin_name}' setup method executing...")
            self.logger.info(f"  EventBus type: {type(event_bus)}, NPCRegistry type: {type(npc_registry)}")

            # Example: Subscribe to a dummy event
            event_bus.subscribe("DUMMY_EVENT_FOR_PLUGIN_TEST", self.handle_dummy_event)
            self.logger.info("  Subscribed to 'DUMMY_EVENT_FOR_PLUGIN_TEST'.")

            # Example: Interact with NPCRegistry
            known_ids = npc_registry.list_known_npc_ids()
            self.logger.info(f"  Known NPC IDs from registry during setup: {known_ids}")

            self.is_setup_complete = True # Mark setup as complete
            self.logger.info(f"MyExampleFirmamentPlugin '{self.plugin_name}' setup successful.")
            return True

        def handle_dummy_event(self, data: Dict[str, Any]):
            self.logger.info(f"MyExampleFirmamentPlugin '{self.plugin_name}' received DUMMY_EVENT_FOR_PLUGIN_TEST with data: {data}")
            self.dummy_events_handled += 1

        def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
            super().update_on_tick(current_time_iso, active_block) # Good practice to call super's method
            self.tick_updates_received += 1
            self.logger.info(f"MyExamplePlugin '{self.plugin_name}' received tick update #{self.tick_updates_received} at {current_time_iso}. Active block: {active_block.get('name') if active_block else 'None'}.")

        def get_status(self) -> Dict[str, Any]:
            base_status = super().get_status() # Get status from base class
            base_status.update({ # Add plugin-specific status
                "tick_updates_received": self.tick_updates_received,
                "dummy_events_handled": self.dummy_events_handled,
                "custom_message": "MyExamplePlugin is operating nominally!"
            })
            return base_status

        def shutdown(self) -> None:
            super().shutdown() # Call super's method for base shutdown logging/actions
            self.logger.info(f"MyExampleFirmamentPlugin '{self.plugin_name}' performing specific shutdown actions (e.g., saving state).")
            # Example: self.save_plugin_state()

    # --- Test the example plugin ---
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    mock_bus_main = MockEventBusForPluginTest()
    mock_registry_main = MockNPCRegistryForPluginTest()

    print("\n--- Initializing MyExampleFirmamentPlugin ---")
    plugin_config_example = {"my_custom_setting": 123, "api_key_for_plugin": "xyz789"}
    firmament_overall_config = {"global_simulation_speed": 2.0, "max_npcs": 10}

    example_plugin_instance = MyExampleFirmamentPlugin(
        plugin_name="WeatherForecaster001",
        firmament_config=firmament_overall_config,
        plugin_specific_config=plugin_config_example
    )
    print(f"Plugin Name: {example_plugin_instance.plugin_name}")
    print(f"Plugin Specific Config: {example_plugin_instance.plugin_specific_config}")
    print(f"Plugin has access to Firmament Config: {example_plugin_instance.firmament_config}")

    print("\n--- Setting up MyExampleFirmamentPlugin ---")
    setup_result = example_plugin_instance.setup(mock_bus_main, mock_registry_main)
    print(f"Plugin Setup Successful: {setup_result}")
    assert setup_result is True, "Plugin setup method failed."
    assert example_plugin_instance.is_setup_complete is True, "is_setup_complete flag not set by plugin."

    print("\n--- Simulating an event for the plugin ---")
    mock_bus_main.publish("DUMMY_EVENT_FOR_PLUGIN_TEST", {"payload": "Test data for dummy event"})
    assert example_plugin_instance.dummy_events_handled == 1, "Plugin's event handler was not called."

    print("\n--- Calling update_on_tick on the plugin ---")
    example_plugin_instance.update_on_tick("2023-10-27T10:00:00Z", {"id": "block_work", "name": "Test Work Block"})
    example_plugin_instance.update_on_tick("2023-10-27T10:01:00Z", {"id": "block_work", "name": "Test Work Block"})
    assert example_plugin_instance.tick_updates_received == 2, "Plugin's update_on_tick was not called as expected."

    print("\n--- Getting plugin status ---")
    current_status = example_plugin_instance.get_status()
    print(f"Plugin Status: {current_status}")
    assert current_status["plugin_name"] == "WeatherForecaster001", "Status has incorrect plugin name."
    assert current_status["tick_updates_received"] == 2, "Status has incorrect tick_updates_received count."
    assert current_status["dummy_events_handled"] == 1, "Status has incorrect dummy_events_handled count."

    print("\n--- Calling shutdown on the plugin ---")
    example_plugin_instance.shutdown()

    print("\n--- Plugin Base Class and Example Plugin __main__ test completed successfully. ---")
