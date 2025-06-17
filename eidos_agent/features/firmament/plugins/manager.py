# eidos_agent/features/firmament/plugins/manager.py
import os
import importlib.util
import inspect
import logging
from typing import Dict, Type, Optional, Any, TYPE_CHECKING

# Import FirmamentPluginBase to check for subclasses
try:
    from .plugin_base import FirmamentPluginBase
except ImportError: # pragma: no cover
    print("CRITICAL: PluginManager could not import FirmamentPluginBase. Plugin system will not work.")
    # Define a dummy base class if import fails, so the rest of the file can parse.
    class FirmamentPluginBase: # type: ignore
        def __init__(self, plugin_name, firmament_config=None, plugin_specific_config=None): self.logger=logging.getLogger(plugin_name); self.plugin_name=plugin_name; self.is_setup_complete=False
        def setup(self, event_bus, npc_registry) -> bool: return False
        def update_on_tick(self, t, b=None): pass
        def get_status(self): return {}
        def shutdown(self): pass


if TYPE_CHECKING: # To avoid circular import issues, for type hinting only # pragma: no cover
    # These paths assume manager.py is in firmament/plugins/
    # EventBus is in firmament/core/
    # NPCRegistry is in firmament/npcs/
    from ..core.event_bus import EventBus # type: ignore
    from ..npcs.npc_registry import NPCRegistry # type: ignore
    # If FirmamentModuleConfig is a specific TypedDict or Pydantic model, import it here.
    # from ....core.config import FirmamentModuleConfig # Example path if config is at project's core

logger = logging.getLogger(__name__)

# Default path for plugins relative to this manager.py file's directory.
# firmament/plugins/manager.py -> this file
# firmament/plugins/enabled/  <- default plugin subdirectory
DEFAULT_PLUGIN_SUBDIR = "enabled"

class PluginManager:
    """
    Manages the discovery, loading, initialization, and lifecycle of Firmament plugins.
    Plugins are Python files located in a specified directory (defaulting to 'enabled'
    subdirectory within the 'plugins' package). Each valid plugin file should contain
    one or more classes that inherit from FirmamentPluginBase.
    """
    def __init__(
        self,
        event_bus: 'EventBus',
        npc_registry: 'NPCRegistry',
        firmament_config: Optional[Dict[str, Any]] = None,
        plugin_dir_override: Optional[str] = None,
        plugin_specific_configs_override: Optional[Dict[str, Dict[str, Any]]] = None # For injecting configs
    ):
        """
        Initializes the PluginManager.

        Args:
            event_bus: Instance of Firmament's EventBus.
            npc_registry: Instance of Firmament's NPCRegistry.
            firmament_config (Optional[Dict[str, Any]]): The main Firmament configuration
                                                         dictionary, passed to plugins.
            plugin_dir_override (Optional[str]): Absolute path to the plugin directory.
                                                 If None, defaults to 'enabled' subdirectory
                                                 within this 'plugins' package.
            plugin_specific_configs_override (Optional[Dict[str, Dict[str, Any]]]):
                                                 A dictionary where keys are plugin names and
                                                 values are their specific configuration dicts.
                                                 This allows for external configuration loading.
        """
        self.event_bus = event_bus
        self.npc_registry = npc_registry
        self.firmament_config = firmament_config if firmament_config is not None else {}

        if plugin_dir_override:
            self.plugin_dir = os.path.abspath(plugin_dir_override)
        else:
            self.plugin_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), DEFAULT_PLUGIN_SUBDIR)
            )

        self.active_plugins: Dict[str, FirmamentPluginBase] = {}

        # Load plugin-specific configurations.
        # TODO: Implement a more robust system for loading these, e.g., from a dedicated config file or directory.
        # For now, they can be passed in at initialization or remain empty.
        self.plugin_specific_configs: Dict[str, Dict[str, Any]] = plugin_specific_configs_override if plugin_specific_configs_override is not None else {}

        logger.info(f"PluginManager initialized. Plugin directory set to: {self.plugin_dir}")
        if not os.path.isdir(self.plugin_dir): # pragma: no cover
            logger.warning(f"Plugin directory does not exist or is not a directory: {self.plugin_dir}. No plugins will be loaded unless created.")
            # Consider creating it: os.makedirs(self.plugin_dir, exist_ok=True) if desired behavior.

    def _discover_plugins(self) -> Dict[str, Type[FirmamentPluginBase]]:
        """
        Scans the plugin directory for Python files, imports them dynamically,
        and discovers classes within them that are subclasses of FirmamentPluginBase.
        It ignores files starting with an underscore.
        """
        discovered_plugin_classes: Dict[str, Type[FirmamentPluginBase]] = {}
        if not os.path.isdir(self.plugin_dir): # Check again, might have been created after init log
            return discovered_plugin_classes # Silently return empty if dir still not there

        logger.debug(f"Discovering plugins in directory: {self.plugin_dir}")
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name_simple = filename[:-3] # Remove .py extension
                # Construct a unique module name for importlib to avoid collisions
                # This assumes plugins are structured to be importable this way.
                # The path from where 'firmament' package is known to Python matters here.
                # e.g., if plugins are in eidos_agent.features.firmament.plugins.enabled.my_plugin
                # This needs to be robust based on how plugins are packaged and where manager is.
                # For now, using a prefix related to the 'enabled' subdir.
                # A more robust way might involve making 'enabled' a package itself.
                module_import_name = f"eidos_agent.features.firmament.plugins.{DEFAULT_PLUGIN_SUBDIR}.{module_name_simple}"
                file_path = os.path.join(self.plugin_dir, filename)

                try:
                    module_spec = importlib.util.spec_from_file_location(module_import_name, file_path)
                    if module_spec and module_spec.loader:
                        plugin_module = importlib.util.module_from_spec(module_spec)
                        # Add to sys.modules before exec_module to handle relative imports within plugin if any
                        # sys.modules[module_import_name] = plugin_module # Careful with sys.modules manipulation
                        module_spec.loader.exec_module(plugin_module)
                        # logger.debug(f"Successfully imported module: {module_name_simple} as {module_import_name}")

                        for name, class_obj in inspect.getmembers(plugin_module, inspect.isclass):
                            if issubclass(class_obj, FirmamentPluginBase) and class_obj is not FirmamentPluginBase:
                                # Use a PLUGIN_NAME class attribute if defined, otherwise class name.
                                plugin_name_key = getattr(class_obj, 'PLUGIN_NAME', class_obj.__name__)

                                if plugin_name_key in discovered_plugin_classes: # pragma: no cover
                                    logger.warning(f"Duplicate plugin name '{plugin_name_key}' found. "
                                                   f"Class {class_obj.__name__} in {module_name_simple} will overwrite previous from "
                                                   f"{discovered_plugin_classes[plugin_name_key].__module__}.")
                                discovered_plugin_classes[plugin_name_key] = class_obj
                                logger.info(f"Discovered plugin class '{class_obj.__name__}' (key: '{plugin_name_key}') in module '{module_name_simple}'.")
                    # else: # pragma: no cover
                        # logger.error(f"Could not create module spec for {module_name_simple} at {file_path}")
                except Exception as e: # pragma: no cover
                    logger.error(f"Error importing or inspecting plugin module {module_name_simple} from {file_path}: {e}", exc_info=True)

        return discovered_plugin_classes

    def load_plugins(self) -> None:
        """
        Discovers all available plugins, then instantiates and calls the setup() method
        on each valid plugin class found. Active plugins are stored in self.active_plugins.
        """
        self.active_plugins.clear() # Clear any previously loaded plugins
        plugin_classes_to_load = self._discover_plugins()

        if not plugin_classes_to_load:
            logger.info("No plugin classes were discovered. Plugin loading phase complete with no active plugins.")
            return

        logger.info(f"Attempting to load and set up {len(plugin_classes_to_load)} discovered plugin classes...")
        for plugin_name, plugin_class in plugin_classes_to_load.items():
            try:
                # logger.debug(f"Instantiating plugin '{plugin_name}' from class {plugin_class.__name__}...")
                plugin_specific_config = self.plugin_specific_configs.get(plugin_name, {}) # Get specific config or empty dict

                instance = plugin_class(
                    plugin_name=plugin_name,
                    firmament_config=self.firmament_config,
                    plugin_specific_config=plugin_specific_config
                )

                # logger.debug(f"Calling setup() for plugin '{plugin_name}'...")
                setup_successful = instance.setup(self.event_bus, self.npc_registry)

                if setup_successful:
                    instance.is_setup_complete = True # Ensure flag is set if plugin's setup returns True but doesn't set it
                    self.active_plugins[plugin_name] = instance
                    logger.info(f"Plugin '{plugin_name}' (Class: {plugin_class.__name__}) loaded and setup successfully.")
                else:
                    logger.warning(f"Plugin '{plugin_name}' (Class: {plugin_class.__name__}) setup method returned False. Plugin will not be activated.")
            except Exception as e: # pragma: no cover
                logger.error(f"Error instantiating or setting up plugin '{plugin_name}' from class {plugin_class.__name__}: {e}", exc_info=True)

        logger.info(f"Plugin loading phase complete. {len(self.active_plugins)} plugins are now active.")


    def run_plugin_updates(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
        """
        Calls the 'update_on_tick' method for all currently active plugins.
        This should be called by the main simulation loop on each tick.
        """
        if not self.active_plugins:
            return

        # logger.debug(f"PluginManager: Running updates for {len(self.active_plugins)} active plugins at {current_time_iso}.")
        for plugin_name, plugin_instance in self.active_plugins.items():
            if not plugin_instance.is_setup_complete: # Skip if setup failed
                continue
            try:
                # logger.debug(f"Updating plugin: {plugin_name}")
                plugin_instance.update_on_tick(current_time_iso, active_block)
            except Exception as e: # pragma: no cover
                logger.error(f"Error during update_on_tick for plugin '{plugin_name}': {e}", exc_info=True)
                # Consider disabling a misbehaving plugin after repeated errors.

    def shutdown_plugins(self) -> None:
        """Calls the shutdown method for all currently active plugins."""
        logger.info(f"PluginManager: Initiating shutdown for {len(self.active_plugins)} active plugins.")
        for plugin_name, plugin_instance in self.active_plugins.items():
            try:
                logger.info(f"Shutting down plugin: {plugin_name}")
                plugin_instance.shutdown()
            except Exception as e: # pragma: no cover
                logger.error(f"Error during shutdown for plugin '{plugin_name}': {e}", exc_info=True)

        self.active_plugins.clear()
        logger.info("PluginManager: All active plugins have been processed for shutdown.")


if __name__ == '__main__': # pragma: no cover
    # This __main__ block is for demonstration and basic testing of the PluginManager.
    # It creates dummy plugin files to test the discovery and loading mechanism.
    logging.basicConfig(level=logging.DEBUG) # Set to DEBUG to see all logs from manager and plugins
    logger_main = logging.getLogger(__name__ + ".__main__")
    logger_main.info("--- Testing PluginManager Standalone ---")

    # Create mock Firmament core components for testing the manager
    class MockEventBusForManagerTest:
        def subscribe(self, event_type, handler): logger_main.info(f"MockEventBus: Handler '{getattr(handler, '__name__', 'unknown')}' subscribed to '{event_type}'")
        def publish(self, event_type, data): logger_main.info(f"MockEventBus: Event '{event_type}' published with {data}")

    class MockNPCRegistryForManagerTest:
        def list_known_npc_ids(self): return ["npc_registry_mock_001"]

    mock_bus_main_test = MockEventBusForManagerTest()
    mock_registry_main_test = MockNPCRegistryForManagerTest()
    mock_fm_config_main_test = {"main_firmament_setting": "active", "version_data": "1.1"}

    # Determine the path to a temporary 'enabled_test_plugins' directory for this test
    # This should be relative to this manager.py file.
    current_script_dir_for_test = os.path.dirname(os.path.abspath(__file__))
    test_plugin_dir_for_main = os.path.join(current_script_dir_for_test, "enabled_test_plugins_main")

    # Create dummy plugin files and directory for the discovery test
    if not os.path.exists(test_plugin_dir_for_main):
        os.makedirs(test_plugin_dir_for_main, exist_ok=True)
        logger_main.info(f"Created test plugin directory: {test_plugin_dir_for_main}")

    # Dummy Plugin 1: test_plugin_alpha.py
    plugin_alpha_content = """
# Test Plugin Alpha
from ..plugin_base import FirmamentPluginBase # Path relative to where plugins/enabled/ would be
import logging

class AlphaPlugin(FirmamentPluginBase):
    PLUGIN_NAME = "AlphaTesterPlugin" # Custom name for registration

    def setup(self, event_bus, npc_registry):
        self.logger.info(f'{self.PLUGIN_NAME} setup method called successfully!')
        event_bus.subscribe("ALPHA_INTERNAL_EVENT", self.handle_alpha_event)
        self.logger.info(f"  Plugin Specific Config: {self.plugin_specific_config}")
        self.logger.info(f"  Firmament Config accessed: {self.firmament_config.get('version_data')}")
        return True # Indicate successful setup

    def handle_alpha_event(self, data):
        self.logger.info(f'{self.PLUGIN_NAME} handled ALPHA_INTERNAL_EVENT with data: {data}')

    def update_on_tick(self, current_time_iso, active_block=None):
        self.logger.info(f'{self.PLUGIN_NAME} received update_on_tick at {current_time_iso}')

    def shutdown(self):
        self.logger.info(f'{self.PLUGIN_NAME} shutdown sequence initiated.')
"""
    with open(os.path.join(test_plugin_dir_for_main, "test_plugin_alpha.py"), "w") as f:
        f.write(plugin_alpha_content)

    # Dummy Plugin 2: test_plugin_beta.py (will use class name as plugin name)
    plugin_beta_content = """
from ..plugin_base import FirmamentPluginBase
class BetaPluginExample(FirmamentPluginBase):
    def setup(self, event_bus, npc_registry):
        self.logger.info(f'{self.plugin_name} setup method called (using class name as plugin name).')
        return True
"""
    with open(os.path.join(test_plugin_dir_for_main, "test_plugin_beta.py"), "w") as f:
        f.write(plugin_beta_content)

    # Non-Python file and underscore file for testing discovery filters
    with open(os.path.join(test_plugin_dir_for_main, "notes.txt"), "w") as f: f.write("Not a plugin.")
    with open(os.path.join(test_plugin_dir_for_main, "_helper_script.py"), "w") as f: f.write("# Should be ignored")


    logger_main.info(f"\n--- Initializing PluginManager with test directory: {test_plugin_dir_for_main} ---")
    # Example of providing plugin-specific configs to the manager
    plugin_configs_for_manager = {
        "AlphaTesterPlugin": {"alpha_specific_key": "alpha_value_123", "debug_mode": True},
        "BetaPluginExample": {"beta_setting": 42}
    }
    manager_instance = PluginManager(
        mock_bus_main_test,
        mock_registry_main_test,
        mock_fm_config_main_test,
        plugin_dir_override=test_plugin_dir_for_main,
        plugin_specific_configs_override=plugin_configs_for_manager
    )

    logger_main.info("\n--- Discovering and Loading Plugins via manager.load_plugins() ---")
    manager_instance.load_plugins() # This calls _discover_plugins and then setup on each

    assert "AlphaTesterPlugin" in manager_instance.active_plugins, "AlphaTesterPlugin not found in active plugins."
    assert "BetaPluginExample" in manager_instance.active_plugins, "BetaPluginExample (by class name) not found."
    assert len(manager_instance.active_plugins) == 2, f"Expected 2 active plugins, found {len(manager_instance.active_plugins)}."

    logger_main.info("\n--- Running Plugin Updates via manager.run_plugin_updates() ---")
    manager_instance.run_plugin_updates("2023-10-27T10:30:00Z", {"id": "test_block_active", "name": "Active Test Block"})
    # To verify this, check the log output for "AlphaTesterPlugin received update_on_tick..."

    logger_main.info("\n--- Simulating an event that AlphaTesterPlugin subscribed to ---")
    mock_bus_main_test.publish("ALPHA_INTERNAL_EVENT", {"message": "Hello from main test!"})
    # Check logs for "AlphaTesterPlugin handled ALPHA_INTERNAL_EVENT..."

    logger_main.info("\n--- Shutting Down Plugins via manager.shutdown_plugins() ---")
    manager_instance.shutdown_plugins()
    assert not manager_instance.active_plugins, "Active plugins list should be empty after shutdown."

    # Clean up dummy plugin files and directory
    try:
        for f_name in ["test_plugin_alpha.py", "test_plugin_beta.py", "notes.txt", "_helper_script.py"]:
            os.remove(os.path.join(test_plugin_dir_for_main, f_name))
        os.rmdir(test_plugin_dir_for_main)
        logger_main.info(f"Cleaned up test plugin directory: {test_plugin_dir_for_main}")
    except OSError as e: # pragma: no cover
        logger_main.error(f"Error cleaning up test plugin directory: {e}")

    logger_main.info("\n--- PluginManager __main__ tests completed successfully. ---")
