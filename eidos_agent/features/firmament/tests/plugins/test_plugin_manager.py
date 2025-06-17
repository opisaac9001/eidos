# eidos_agent/features/firmament/tests/plugins/test_plugin_manager.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import importlib.util
import sys
import logging
from typing import Dict, Type, Optional, Any, TYPE_CHECKING


# Adjust import path based on actual file structure
try:
    # Assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.plugins.manager import PluginManager, DEFAULT_PLUGIN_SUBDIR
    from eidos_agent.features.firmament.plugins.plugin_base import FirmamentPluginBase
    # For type hinting and instantiating PluginManager
    if TYPE_CHECKING: # pragma: no cover
        from eidos_agent.core.event_bus import EventBus
        from eidos_agent.features.firmament.npcs.npc_registry import NPCRegistry
except ImportError: # pragma: no cover
    print("CRITICAL: Could not resolve imports for PluginManager test. Using dummy classes.")
    # Dummies
    class FirmamentPluginBase:
        def __init__(self, plugin_name, firmament_config=None, plugin_specific_config=None):
            self.plugin_name=plugin_name
            self.firmament_config = firmament_config or {}
            self.plugin_specific_config = plugin_specific_config or {}
            self.logger=MagicMock(spec=logging.Logger)
            self.is_setup_complete=False
        def setup(self,event_bus,npc_registry) -> bool: self.is_setup_complete=True; return True
        def update_on_tick(self,t,ab=None):pass
        def get_status(self): return {}
        def shutdown(self):pass
    class PluginManager: #type:ignore
        def __init__(self,event_bus,npc_registry,firmament_config,plugin_dir_override=None,plugin_specific_configs_override=None):
            self.active_plugins: Dict[str, FirmamentPluginBase] = {}
            self.event_bus=event_bus
            self.npc_registry=npc_registry
            self.plugin_dir = plugin_dir_override or "dummy_enabled"
            self.firmament_config = firmament_config
            self.plugin_specific_configs = plugin_specific_configs_override or {}
        def _discover_plugins(self) -> Dict[str, Type[FirmamentPluginBase]]: return {}
        def load_plugins(self): pass
        def run_plugin_updates(self,t,ab): pass
        def shutdown_plugins(self): pass
    DEFAULT_PLUGIN_SUBDIR = "enabled_dummy" #type:ignore
    EventBus = MagicMock(name="DummyEventBusForManagerTest") #type:ignore
    NPCRegistry = MagicMock(name="DummyNPCRegistryForManagerTest") #type:ignore


# --- Helper Mock Plugin Classes (defined globally in the test file) ---
class MockPluginAlpha(FirmamentPluginBase):
    PLUGIN_NAME = "Alpha"
    def __init__(self, plugin_name, firmament_config, plugin_specific_config):
        super().__init__(plugin_name, firmament_config, plugin_specific_config)
        self.setup_called_with = None
        self.update_tick_called_with = None
        self.shutdown_called = False
    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        self.setup_called_with = (event_bus, npc_registry)
        self.is_setup_complete = True
        self.logger.info(f"{self.plugin_name} setup success.")
        return True
    def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]]) -> None:
        self.update_tick_called_with = (current_time_iso, active_block)
        self.logger.info(f"{self.plugin_name} updated.")
    def shutdown(self) -> None:
        self.shutdown_called = True
        self.logger.info(f"{self.plugin_name} shutdown.")

class MockPluginBeta(FirmamentPluginBase):
    # Name will be class name: MockPluginBeta
    def __init__(self, plugin_name, firmament_config, plugin_specific_config):
        super().__init__(plugin_name, firmament_config, plugin_specific_config)
    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        self.is_setup_complete = False
        self.logger.warning(f"{self.plugin_name} setup failed intentionally.")
        return False # Setup fails

class MockPluginGamma(FirmamentPluginBase):
    def __init__(self, plugin_name, firmament_config, plugin_specific_config):
        super().__init__(plugin_name, firmament_config, plugin_specific_config)
    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        self.logger.error(f"{self.plugin_name} setup erroring intentionally.")
        raise ValueError("Gamma setup intentional error")


class TestPluginManager(unittest.TestCase):

    def setUp(self):
        self.mock_event_bus = MagicMock(spec=EventBus)
        self.mock_npc_registry = MagicMock(spec=NPCRegistry)
        self.mock_firmament_config = {"global_setting": "test_value_fm_config"}

        # Use a temporary directory for plugin files specific to each test run
        # This path should be unique enough for parallel tests if run that way, though unittest usually serializes.
        # It's created relative to this test file's location.
        self.base_test_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_plugin_root_dir = os.path.join(self.base_test_dir, "temp_pm_test_plugins_root")
        self.test_plugins_path = os.path.join(self.temp_plugin_root_dir, DEFAULT_PLUGIN_SUBDIR) # e.g., temp_pm_test_plugins_root/enabled

        # Clean up before test, then create fresh
        if os.path.exists(self.temp_plugin_root_dir): # pragma: no cover
            import shutil
            shutil.rmtree(self.temp_plugin_root_dir)
        os.makedirs(self.test_plugins_path, exist_ok=True)

        self.manager = PluginManager(
            self.mock_event_bus,
            self.mock_npc_registry,
            self.mock_firmament_config,
            plugin_dir_override=self.test_plugins_path
        )

    def tearDown(self):
        # Clean up temp plugin directory and files
        if os.path.exists(self.temp_plugin_root_dir): # pragma: no cover
            import shutil
            shutil.rmtree(self.temp_plugin_root_dir)

    def _create_mock_plugin_file(self, filename="plugin_module.py", content=""):
        """Helper to create a plugin file in the test plugin directory."""
        filepath = os.path.join(self.test_plugins_path, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    # Patching where these functions are USED (inside PluginManager)
    @patch('eidos_agent.features.firmament.plugins.manager.importlib.util.spec_from_file_location')
    @patch('eidos_agent.features.firmament.plugins.manager.importlib.util.module_from_spec')
    @patch('eidos_agent.features.firmament.plugins.manager.os.listdir')
    def test_discover_plugins_logic(self, mock_listdir, mock_module_from_spec, mock_spec_from_file_location):
        print("Running: test_discover_plugins_logic")
        mock_listdir.return_value = ["alpha_plugin.py", "beta_plugin.py", "_ignored_helper.py", "some_notes.txt"]

        # --- Mocking for alpha_plugin.py ---
        mock_alpha_module_obj = MagicMock() # This is the module object
        # Attach the class to this module object. inspect.getmembers will find it.
        mock_alpha_module_obj.AlphaPluginClassForTest = MockPluginAlpha

        # --- Mocking for beta_plugin.py ---
        mock_beta_module_obj = MagicMock()
        mock_beta_module_obj.BetaPluginClassForTest = MockPluginBeta

        # Configure module_from_spec to return our module mocks based on the spec's name
        def module_from_spec_side_effect(spec):
            if spec.name.endswith("alpha_plugin"): return mock_alpha_module_obj
            if spec.name.endswith("beta_plugin"): return mock_beta_module_obj
            return MagicMock() # Default for any other case
        mock_module_from_spec.side_effect = module_from_spec_side_effect

        # Configure spec_from_file_location to return a mock spec with a mock loader
        # The loader's exec_module will be called on the module objects above.
        def spec_side_effect_for_discovery(name, location):
            mock_spec = MagicMock()
            mock_spec.name = name # importlib uses this name
            mock_spec.loader = MagicMock()
            mock_spec.loader.exec_module = MagicMock() # This method is called by importlib
            return mock_spec
        mock_spec_from_file_location.side_effect = spec_side_effect_for_discovery

        discovered_classes = self.manager._discover_plugins()

        # Assertions
        self.assertEqual(mock_spec_from_file_location.call_count, 2, "Should have tried to load 2 .py files.")
        # Check that exec_module was called for each loaded module spec
        for call_obj in mock_spec_from_file_location.return_value.loader.exec_module.call_args_list:
             self.assertIn(call_obj.args[0], [mock_alpha_module_obj, mock_beta_module_obj], "exec_module not called with expected module.")

        self.assertIn("Alpha", discovered_classes, "Alpha plugin (by PLUGIN_NAME) not discovered.")
        self.assertEqual(discovered_classes["Alpha"], MockPluginAlpha)
        self.assertIn("MockPluginBeta", discovered_classes, "Beta plugin (by class name) not discovered.") # Falls back to class name
        self.assertEqual(discovered_classes["MockPluginBeta"], MockPluginBeta)
        self.assertEqual(len(discovered_classes), 2, "Incorrect number of plugins discovered.")
        print("Test Passed: Plugin discovery logic with mocks.")


    @patch('eidos_agent.features.firmament.plugins.manager.PluginManager._discover_plugins')
    def test_load_plugins_instantiates_and_sets_up_correctly(self, mock_discover_plugins_method):
        print("Running: test_load_plugins_instantiates_and_sets_up_correctly")

        # Configure _discover_plugins to return a controlled dict of plugin classes
        mock_discover_plugins_method.return_value = {
            "AlphaInstanceTest": MockPluginAlpha, # Setup will succeed
            "BetaInstanceTest": MockPluginBeta,   # Setup will fail (returns False)
            "GammaInstanceTest": MockPluginGamma  # Setup will raise an error
        }

        # Example plugin-specific configs for the manager to use
        self.manager.plugin_specific_configs = {
            "AlphaInstanceTest": {"alpha_setting": "alpha_val"},
            "BetaInstanceTest": {"beta_setting": "beta_val"}
            # Gamma has no specific config here
        }

        self.manager.load_plugins() # This is the primary method call under test

        # --- Assertions for Alpha ---
        self.assertIn("AlphaInstanceTest", self.manager.active_plugins, "Alpha plugin should be active.")
        alpha_instance = self.manager.active_plugins.get("AlphaInstanceTest")
        self.assertIsInstance(alpha_instance, MockPluginAlpha, "Alpha instance type mismatch.")
        if alpha_instance: # For type checker
            self.assertTrue(alpha_instance.is_setup_complete, "Alpha plugin setup flag should be True.")
            self.assertEqual(alpha_instance.setup_called_with, (self.mock_event_bus, self.mock_npc_registry), "Alpha setup not called with correct args.")
            self.assertEqual(alpha_instance.plugin_specific_config.get("alpha_setting"), "alpha_val", "Alpha specific config not passed.")
            self.assertEqual(alpha_instance.firmament_config, self.mock_firmament_config, "Firmament config not passed to Alpha.")

        # --- Assertions for Beta (setup fails) ---
        self.assertNotIn("BetaInstanceTest", self.manager.active_plugins, "Beta plugin (setup returns False) should not be active.")

        # --- Assertions for Gamma (setup raises error) ---
        self.assertNotIn("GammaInstanceTest", self.manager.active_plugins, "Gamma plugin (setup errors) should not be active.")

        self.assertEqual(len(self.manager.active_plugins), 1, "Only Alpha plugin should be active.")
        print("Test Passed: Plugin loading, instantiation, and setup calls handled correctly.")

    def test_run_plugin_updates_calls_active_plugins(self):
        print("Running: test_run_plugin_updates_calls_active_plugins")
        # Manually set up an active plugin for this test
        plugin_alpha_inst = MockPluginAlpha("AlphaForTickUpdate", {}, {})
        plugin_alpha_inst.is_setup_complete = True # Simulate successful setup
        self.manager.active_plugins = {"AlphaForTickUpdate": plugin_alpha_inst}

        test_time_iso = "2023-10-28T10:00:00Z"
        test_active_block = {"name": "Test Current Block", "type": "testing"}
        self.manager.run_plugin_updates(test_time_iso, test_active_block)

        self.assertEqual(plugin_alpha_inst.update_tick_called_with, (test_time_iso, test_active_block),
                         "Plugin's update_on_tick not called or called with wrong arguments.")
        print("Test Passed: run_plugin_updates called active plugin's update_on_tick.")

    def test_shutdown_plugins_calls_active_plugins_and_clears(self):
        print("Running: test_shutdown_plugins_calls_active_plugins_and_clears")
        plugin_alpha_inst_shutdown = MockPluginAlpha("AlphaForShutdown", {}, {})
        plugin_alpha_inst_shutdown.is_setup_complete = True
        self.manager.active_plugins = {"AlphaForShutdown": plugin_alpha_inst_shutdown}

        self.manager.shutdown_plugins()

        self.assertTrue(plugin_alpha_inst_shutdown.shutdown_called, "Plugin's shutdown method not called.")
        self.assertEqual(len(self.manager.active_plugins), 0,
                         "Active plugins dictionary should be empty after shutdown_plugins.")
        print("Test Passed: shutdown_plugins called plugin's shutdown and cleared active plugins.")

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Enable DEBUG to see detailed logs from manager and mock plugins
    unittest.main(verbosity=2)
