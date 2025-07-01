# eidos_agent/features/firmament/tests/npcs/test_npc_registry.py
import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import os
import logging # For assertLogs and general logging
from typing import Dict, Any, List # For type hints

# Adjust import path based on actual file structure
try:
    # Assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.npcs.npc_registry import NPCRegistry, CONFIG_DIR_PATH as REGISTRY_CONFIG_DIR_PATH, _PERSISTENCE_FILE_NAME_DEFAULT as REGISTRY_DEFAULT_FNAME
except ImportError: # pragma: no cover
    # Fallback for simpler structures or direct execution
    print("CRITICAL: Could not resolve imports for NPCRegistry test. Using dummy class.")
    REGISTRY_CONFIG_DIR_PATH = "./dummy_configs_for_registry_test"
    REGISTRY_DEFAULT_FNAME = "dummy_registry_persistence.json"
    class NPCRegistry: #type:ignore
        _instance = None
        def __init__(self, persistence_file_name=None):
            self._known_npcs: Dict[str, Dict[str,Any]] = {}
            self._persistence_file_path = os.path.join(REGISTRY_CONFIG_DIR_PATH, persistence_file_name or REGISTRY_DEFAULT_FNAME)
            print(f"Dummy NPCRegistry initialized. Persistence path: {self._persistence_file_path}")
        @classmethod
        def instance(cls, persistence_file_name=None):
            # Simplified dummy singleton for testing
            if not cls._instance or (persistence_file_name and cls._instance._persistence_file_path != os.path.join(REGISTRY_CONFIG_DIR_PATH, persistence_file_name)):
                cls._instance = cls(persistence_file_name=persistence_file_name)
            return cls._instance
        def _normalize_id(self, npc_id: str) -> str: return npc_id.strip().lower().replace(" ", "_") if npc_id and isinstance(npc_id, str) else ""
        def _load_from_file(self): print(f"Dummy _load_from_file called for {self._persistence_file_path}") # Mocked behavior
        def _save_to_file(self): print(f"Dummy _save_to_file called for {self._persistence_file_path}") # Mocked behavior
        def get_npc_by_id(self, npc_id: str) -> Optional[Dict[str, Any]]: return self._known_npcs.get(self._normalize_id(npc_id))
        def register_npc(self, npc_data: Dict[str, Any]) -> bool:
            npc_id = npc_data.get('id')
            if not isinstance(npc_data, dict) or not isinstance(npc_id, str) or not npc_id.strip(): return False
            normalized_id = self._normalize_id(npc_id)
            if 'name' not in npc_data or not npc_data.get('name','').strip(): npc_data['name'] = npc_id
            self._known_npcs[normalized_id] = npc_data; self._save_to_file(); return True
        def list_known_npc_ids(self) -> List[str]: return list(self._known_npcs.keys())
        def get_all_npcs(self) -> List[Dict[str, Any]]: return list(self._known_npcs.values())
        def clear_registry(self): self._known_npcs.clear(); self._save_to_file()

class TestNPCRegistry(unittest.TestCase):

    def setUp(self):
        # Define a specific test persistence file name
        self.test_persistence_filename = "test_npc_registry_for_unittest.json"
        self.test_persistence_file_path = os.path.join(REGISTRY_CONFIG_DIR_PATH, self.test_persistence_filename)

        # Reset the singleton instance before each test to ensure isolation
        NPCRegistry._instance = None

        # Ensure the dummy config dir exists for tests that might write
        # This should match the CONFIG_DIR_PATH from the module under test
        if not os.path.exists(REGISTRY_CONFIG_DIR_PATH): # pragma: no cover
            os.makedirs(REGISTRY_CONFIG_DIR_PATH, exist_ok=True)

        # Clean up any pre-existing test file to ensure a fresh start for each test
        if os.path.exists(self.test_persistence_file_path): # pragma: no cover
            os.remove(self.test_persistence_file_path)

    def tearDown(self):
        # Clean up the test persistence file after each test
        if os.path.exists(self.test_persistence_file_path): # pragma: no cover
            os.remove(self.test_persistence_file_path)
        NPCRegistry._instance = None # Ensure singleton is reset for other test classes/files

    def test_initialization_empty_and_load_file_not_found(self):
        print("Running: test_initialization_empty_and_load_file_not_found")
        # File should not exist here due to setUp.
        # NPCRegistry.instance() calls __init__, which calls _load_from_file.
        # We expect a log message that the file was not found.
        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_registry', level='INFO') as log_cm:
            registry = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)

        self.assertEqual(len(registry.list_known_npc_ids()), 0, "Registry should be empty if persistence file not found.")
        self.assertTrue(any(f"Persistence file not found at {self.test_persistence_file_path}" in msg for msg in log_cm.output),
                        "Expected log message about file not found missing.")
        print("Test Passed: Initialization empty when file not found.")


    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=True) # Assume file exists for this test
    def test_load_from_file_populates_registry(self, mock_path_exists, mock_file_open):
        print("Running: test_load_from_file_populates_registry")
        mock_json_data = {
            "npc001_test": {"id": "npc001_test", "name": "Loaded NPC 1"},
            "npc002_test": {"id": "npc002_test", "name": "Loaded NPC 2"}
        }
        # Configure mock_open to return a file handle that reads our mock JSON data
        mock_file_open.return_value.read.return_value = json.dumps(mock_json_data)

        registry = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)

        self.assertEqual(len(registry.list_known_npc_ids()), 2, "Registry should have 2 NPCs after loading.")
        self.assertIsNotNone(registry.get_npc_by_id("npc001_test"), "NPC001 not found after load.")
        if registry.get_npc_by_id("npc002_test"): # Check to prevent NoneType error
            self.assertEqual(registry.get_npc_by_id("npc002_test")["name"], "Loaded NPC 2", "NPC002 name mismatch.")

        # Check that open was called for reading the correct file
        mock_file_open.assert_called_once_with(self.test_persistence_file_path, 'r', encoding='utf-8')
        print("Test Passed: Loaded from file populates registry.")

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=True)
    def test_load_from_file_handles_corrupt_json(self, mock_path_exists, mock_file_open):
        print("Running: test_load_from_file_handles_corrupt_json")
        mock_file_open.return_value.read.return_value = "this is not valid json { definitely not"

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_registry', level='ERROR') as log_cm:
            registry = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)

        self.assertEqual(len(registry.list_known_npc_ids()), 0, "Registry should be empty after attempting to load corrupt JSON.")
        self.assertTrue(any("Error decoding JSON" in msg for msg in log_cm.output),
                        "Expected log message about JSON decode error missing.")
        print("Test Passed: Handled corrupt JSON on load.")

    @patch('builtins.open', new_callable=mock_open)
    def test_register_npc_triggers_save_and_data_is_correct(self, mock_file_open):
        print("Running: test_register_npc_triggers_save_and_data_is_correct")
        # Simulate file not existing for initial load by NPCRegistry.__init__
        # The first call to os.path.exists (in _load_from_file) should be False.
        # The subsequent calls (in _save_to_file for directory check) should be True or allow dir creation.
        # For simplicity, we'll assume directory exists.
        mock_file_open.side_effect = [FileNotFoundError, MagicMock()][1:] # First call (load) -> FileNotFoundError, subsequent (save) -> mock_open handle

        registry = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)
        self.assertEqual(len(registry.list_known_npc_ids()), 0, "Registry should be empty initially.")

        npc_data_to_save = {"id": "npc_save_test_id", "name": "Save Me Please", "role": "Persister"}
        registry.register_npc(npc_data_to_save)

        self.assertIn(registry._normalize_id("npc_save_test_id"), registry.list_known_npc_ids())

        # Check that open was called for writing the correct file after registration
        mock_file_open.assert_called_with(self.test_persistence_file_path, 'w', encoding='utf-8')

        # Check the content that was written by json.dump
        # mock_file_open().write is a MagicMock. We need to collect its calls.
        written_content = "".join(call_args[0][0] for call_args in mock_file_open().write.call_args_list)
        expected_saved_data = {registry._normalize_id("npc_save_test_id"): npc_data_to_save}
        self.assertEqual(json.loads(written_content), expected_saved_data, "Data saved to file is incorrect.")
        print("Test Passed: Register NPC triggers save with correct data.")

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists') # Patch os.path.exists used by _load_from_file
    def test_clear_registry_triggers_save_empty(self, mock_path_exists, mock_file_open):
        print("Running: test_clear_registry_triggers_save_empty")

        # Simulate file exists and contains data for the initial load
        initial_data = {"npc_to_clear_id": {"id": "npc_to_clear_id", "name": "Clear Me If You Can"}}
        mock_path_exists.return_value = True # File exists
        mock_file_open.return_value.read.return_value = json.dumps(initial_data)

        registry = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)
        self.assertIn(registry._normalize_id("npc_to_clear_id"), registry.list_known_npc_ids(), "NPC should be loaded initially.")

        # Reset mock_file_open to capture the 'write' call during clear_registry
        # The file handle mock is part of mock_file_open.return_value
        file_handle_mock = mock_file_open.return_value
        file_handle_mock.write.reset_mock() # Reset calls on the file handle's write method

        registry.clear_registry() # This should call _save_to_file

        self.assertEqual(len(registry.list_known_npc_ids()), 0, "Registry should be empty after clear.")

        # Verify that _save_to_file was called (which means 'open' in 'w' mode was called)
        # The call to open for read happened during __init__. The one for write happens in _save_to_file.
        mock_file_open.assert_called_with(self.test_persistence_file_path, 'w', encoding='utf-8')

        # Verify that an empty dictionary was written
        written_content = "".join(call_args[0][0] for call_args in file_handle_mock.write.call_args_list)
        self.assertEqual(json.loads(written_content), {}, "Cleared registry did not save an empty dictionary.")
        print("Test Passed: Clear registry triggers save with empty data.")

    def test_singleton_behavior_with_persistence_real_file(self):
        print("Running: test_singleton_behavior_with_persistence_real_file")
        # This test uses the actual file system with the temporary test file.

        # Instance 1: Register an NPC, should save to test_persistence_file_path
        registry1 = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)
        npc_data1 = {"id": "singleton_npc_real_file_1", "name": "Singleton One Real"}
        registry1.register_npc(npc_data1)
        self.assertTrue(os.path.exists(self.test_persistence_file_path), "File should exist after reg 1.")

        # Force new instance creation for registry2, it should load from the file written by registry1
        NPCRegistry._instance = None
        registry2 = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)

        self.assertIsNotNone(registry2.get_npc_by_id("singleton_npc_real_file_1"), "NPC1 not loaded by second instance from real file.")
        if registry2.get_npc_by_id("singleton_npc_real_file_1"):
            self.assertEqual(registry2.get_npc_by_id("singleton_npc_real_file_1")["name"], "Singleton One Real")

        # Instance 2: Register another NPC
        npc_data2 = {"id": "singleton_npc_real_file_2", "name": "Singleton Two Real"}
        registry2.register_npc(npc_data2) # Saves both npc1 and npc2

        # Force new instance creation for registry3
        NPCRegistry._instance = None
        registry3 = NPCRegistry.instance(persistence_file_name=self.test_persistence_filename)
        self.assertIsNotNone(registry3.get_npc_by_id("singleton_npc_real_file_1"), "NPC1 missing in third instance.")
        self.assertIsNotNone(registry3.get_npc_by_id("singleton_npc_real_file_2"), "NPC2 missing in third instance.")
        self.assertEqual(len(registry3.list_known_npc_ids()), 2)
        print("Test Passed: Singleton behavior correctly interacts with real file persistence.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Enable DEBUG to see detailed logs from registry itself
    unittest.main(verbosity=2)
