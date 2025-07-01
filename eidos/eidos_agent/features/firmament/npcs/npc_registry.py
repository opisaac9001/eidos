# eidos_agent/features/firmament/npcs/npc_registry.py
import logging
from typing import Dict, Optional, Any, List
import json # Added
import os   # Added

logger = logging.getLogger(__name__)

# Path to the configs directory, relative to this file's directory
# This file is in: eidos_agent/features/firmament/npcs/
# Configs are in: eidos_agent/features/firmament/configs/
# So, go up one level ("..") to firmament/, then into "configs/"
CONFIG_DIR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "configs"))
_PERSISTENCE_FILE_NAME_DEFAULT = "improvised_npcs_registry.json"


class NPCRegistry:
    _instance: Optional['NPCRegistry'] = None

    def __init__(self, persistence_file_name: str = _PERSISTENCE_FILE_NAME_DEFAULT):
        """
        Initializes the NPCRegistry.
        The constructor should ideally not be called directly if using the singleton pattern.
        Use NPCRegistry.instance() instead.
        The persistence_file_name is primarily for allowing tests to use a temporary file.
        """
        if NPCRegistry._instance is not None and persistence_file_name == _PERSISTENCE_FILE_NAME_DEFAULT: # pragma: no cover
            # This condition means we are trying to re-initialize the *singleton* instance directly
            # after it has already been created via instance(). This is usually not intended.
            # If instance() was called with a custom file name, that would create a separate instance.
            logger.warning("NPCRegistry __init__ called directly on an existing singleton instance. "
                           "This typically shouldn't happen. State will be reloaded.")

        self._known_npcs: Dict[str, Dict[str, Any]] = {}
        self._persistence_file_path = os.path.join(CONFIG_DIR_PATH, persistence_file_name)
        # logger.info(f"NPCRegistry: Persistence file path set to: {self._persistence_file_path}")
        self._load_from_file()

    @classmethod
    def instance(cls, persistence_file_name: str = _PERSISTENCE_FILE_NAME_DEFAULT) -> 'NPCRegistry':
        """
        Provides access to the singleton instance of NPCRegistry.
        If a custom persistence_file_name is provided to this method *and* an instance
        already exists using the default file name, it will still return the existing default instance.
        To use a different file for a distinct registry (e.g., for tests), ensure instance() is called
        with that custom name *before* any calls with the default name, or manage instances externally.
        For simplicity, this singleton primarily manages one default instance.
        """
        if cls._instance is None or \
           (cls._instance and cls._instance._persistence_file_path != os.path.join(CONFIG_DIR_PATH, persistence_file_name)):
            # Create new instance if none exists, or if the requested persistence file is different from the existing singleton's.
            # This latter part allows creating separate instances for testing with different files,
            # though it slightly complicates strict singleton interpretation if file names vary.
            # For a strict single global instance, remove the file path check.
            if cls._instance is not None and \
               cls._instance._persistence_file_path != os.path.join(CONFIG_DIR_PATH, persistence_file_name): # pragma: no cover
                logger.warning(f"NPCRegistry.instance() called with a new persistence file ('{persistence_file_name}'). "
                               f"Creating a new registry instance for this file. This is unusual for a singleton.")
                # Create a new instance for the different file, don't overwrite cls._instance for the default one.
                # This means instance() is not a strict singleton if file names differ.
                # For the purpose of this class, we'll assume the *first call to instance()* sets the singleton.
                # Or, for testing, allow re-creation if filename differs.
                # Let's stick to: first call to instance() creates THE singleton.
                # If a test needs a different file, it should manage its own instance or patch the path.
                # The provided __main__ handles this by manipulating _PERSISTENCE_FILE_NAME directly.

            # logger.info(f"NPCRegistry: Creating new singleton instance. Persistence: {os.path.join(CONFIG_DIR_PATH, persistence_file_name)}")
            try: # Ensure config directory exists for persistence when instance is first created
                if not os.path.exists(CONFIG_DIR_PATH): # pragma: no cover
                    os.makedirs(CONFIG_DIR_PATH, exist_ok=True)
                    logger.info(f"NPCRegistry: Created config directory for persistence: {CONFIG_DIR_PATH}")
            except OSError as e: # pragma: no cover
                logger.error(f"NPCRegistry: Could not create config directory {CONFIG_DIR_PATH}. Persistence might fail. Error: {e}")

            cls._instance = cls(persistence_file_name=persistence_file_name) # Calls __init__ which calls _load_from_file
        return cls._instance

    def _normalize_id(self, npc_id: str) -> str:
        if not npc_id or not isinstance(npc_id, str): return ""
        return npc_id.strip().lower().replace(" ", "_")

    def _load_from_file(self):
        # logger.debug(f"NPCRegistry: Attempting to load NPCs from {self._persistence_file_path}")
        try:
            if os.path.exists(self._persistence_file_path):
                with open(self._persistence_file_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                if isinstance(loaded_data, dict):
                    # Assume keys in the file are already normalized if saved by this class
                    self._known_npcs = loaded_data
                    logger.info(f"NPCRegistry: Loaded {len(self._known_npcs)} NPCs from {self._persistence_file_path}")
                else: # pragma: no cover
                    logger.warning(f"NPCRegistry: Data in {self._persistence_file_path} is not a dictionary. Starting with empty registry.")
                    self._known_npcs = {}
            else:
                logger.info(f"NPCRegistry: Persistence file not found at {self._persistence_file_path}. Starting with an empty registry.")
                self._known_npcs = {} # Ensure it's empty if file not found
        except json.JSONDecodeError as e: # pragma: no cover
            logger.error(f"NPCRegistry: Error decoding JSON from {self._persistence_file_path}. File might be corrupted. Error: {e}. Starting with empty registry.", exc_info=False) # exc_info=False for brevity
            self._known_npcs = {}
        except Exception as e: # pragma: no cover
            logger.error(f"NPCRegistry: Unexpected error loading from {self._persistence_file_path}. Error: {e}. Starting with empty registry.", exc_info=True)
            self._known_npcs = {}

    def _save_to_file(self):
        # logger.debug(f"NPCRegistry: Attempting to save {len(self._known_npcs)} NPCs to {self._persistence_file_path}")
        try:
            # Ensure directory exists before trying to save file. instance() should do this, but good to be safe.
            if not os.path.exists(os.path.dirname(self._persistence_file_path)): # pragma: no cover
                 os.makedirs(os.path.dirname(self._persistence_file_path), exist_ok=True)
                 logger.info(f"NPCRegistry: Created directory for persistence file: {os.path.dirname(self._persistence_file_path)}")


            with open(self._persistence_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._known_npcs, f, indent=2, ensure_ascii=False) # ensure_ascii=False for broader char support
            logger.info(f"NPCRegistry: Successfully saved {len(self._known_npcs)} NPCs to {self._persistence_file_path}")
        except IOError as e: # pragma: no cover
            logger.error(f"NPCRegistry: IOError saving NPCs to {self._persistence_file_path}. Error: {e}", exc_info=True)
        except Exception as e: # pragma: no cover
            logger.error(f"NPCRegistry: Unexpected error saving NPCs to {self._persistence_file_path}. Error: {e}", exc_info=True)


    def get_npc_by_id(self, npc_id: str) -> Optional[Dict[str, Any]]:
        normalized_id_key = self._normalize_id(npc_id)
        if not normalized_id_key:
            # logger.warning("get_npc_by_id called with empty or invalid npc_id.")
            return None
        return self._known_npcs.get(normalized_id_key)

    def register_npc(self, npc_data: Dict[str, Any]) -> bool:
        if not isinstance(npc_data, dict):
            logger.error("NPCRegistry: Register NPC failed. npc_data is not a dictionary.")
            return False

        npc_id_from_data = npc_data.get('id')
        if not isinstance(npc_id_from_data, str) or not npc_id_from_data.strip():
            logger.error(f"NPCRegistry: Register NPC failed. 'id' field is missing, not a string, or empty in npc_data: {str(npc_data)[:100]}")
            return False

        normalized_id_key = self._normalize_id(npc_id_from_data)

        # Ensure 'name' exists in npc_data, default to id if not. This is good practice for profiles.
        if 'name' not in npc_data or not isinstance(npc_data.get('name'), str) or not npc_data.get('name','').strip():
            logger.warning(f"NPCRegistry: NPC data for ID '{normalized_id_key}' is missing a valid 'name'. Defaulting name to ID for this registration.")
            npc_data['name'] = npc_id_from_data # Use original non-normalized ID as name if name is missing/invalid

        # logger.info(f"NPCRegistry: Registering/Updating NPC with ID '{normalized_id_key}' (Name: '{npc_data['name']}').")
        self._known_npcs[normalized_id_key] = npc_data
        self._save_to_file() # Persist after change
        return True

    def list_known_npc_ids(self) -> List[str]:
        return list(self._known_npcs.keys())

    def get_all_npcs(self) -> List[Dict[str, Any]]:
        return list(self._known_npcs.values()) # Consider deep copies if profiles are mutable and shared

    def clear_registry(self):
        """Clears all NPCs from the in-memory store and persists this empty state to the file."""
        self._known_npcs.clear()
        logger.info("NPCRegistry: In-memory NPC store cleared.")
        self._save_to_file() # Persist the cleared state (writes an empty JSON object {} to file)

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Set to DEBUG to see all log messages from registry

    # Use a temporary file for this __main__ test to avoid affecting real data
    # This global manipulation is for testing this script directly only.
    # In real use, instance() would use the default or a passed-in name.
    _original_persistence_file_name_for_test = _PERSISTENCE_FILE_NAME_DEFAULT
    _PERSISTENCE_FILE_NAME_MAIN_TEST = "test_npc_registry_temp.json"

    # The NPCRegistry instance will use this path due to how its __init__ gets the filename
    # We need to ensure CONFIG_DIR_PATH exists because _save_to_file and _load_from_file use it.
    if not os.path.exists(CONFIG_DIR_PATH):
        os.makedirs(CONFIG_DIR_PATH, exist_ok=True)
        print(f"__main__: Created test config directory: {CONFIG_DIR_PATH}")

    temp_file_path_for_test = os.path.join(CONFIG_DIR_PATH, _PERSISTENCE_FILE_NAME_MAIN_TEST)

    # Clean up previous test file if it exists before starting
    if os.path.exists(temp_file_path_for_test):
        os.remove(temp_file_path_for_test)
        print(f"__main__: Removed pre-existing temporary test file: {temp_file_path_for_test}")

    print(f"NPCRegistry __main__ test: Using temporary persistence file: {temp_file_path_for_test}")

    # --- Test 1: Initial load (file shouldn't exist) ---
    NPCRegistry._instance = None # Force re-creation for test load, using the new temp file name
    registry = NPCRegistry.instance(persistence_file_name=_PERSISTENCE_FILE_NAME_MAIN_TEST)
    print(f"Initial known NPC IDs: {registry.list_known_npc_ids()}")
    assert not registry.list_known_npc_ids(), "Registry should be empty initially if file doesn't exist."

    # --- Test 2: Register NPC (triggers save) ---
    npc1_data = {"id": "npc_test_001", "name": "Test NPC One", "role": "Tester"}
    registry.register_npc(npc1_data)
    assert "npc_test_001" in registry.list_known_npc_ids() # IDs are normalized, so "npc_test_001" is key
    assert os.path.exists(temp_file_path_for_test), "Persistence file should have been created after registration."
    print(f"NPC '{npc1_data['name']}' registered. File exists: {os.path.exists(temp_file_path_for_test)}")

    # --- Test 3: Create new instance (should load from file) ---
    NPCRegistry._instance = None
    registry2 = NPCRegistry.instance(persistence_file_name=_PERSISTENCE_FILE_NAME_MAIN_TEST)
    print(f"NPC IDs after new instance and load: {registry2.list_known_npc_ids()}")
    assert "npc_test_001" in registry2.list_known_npc_ids(), "NPC One not loaded from file by new instance."
    retrieved_npc1 = registry2.get_npc_by_id("npc_test_001")
    assert retrieved_npc1 and retrieved_npc1.get("role") == "Tester", "NPC One data mismatch after load."

    # --- Test 4: Register another NPC ---
    npc2_data = {"id": "npc_test_002", "name": "Test NPC Two", "appearance": "blue"}
    registry2.register_npc(npc2_data) # Should save both npc1 and npc2

    NPCRegistry._instance = None
    registry3 = NPCRegistry.instance(persistence_file_name=_PERSISTENCE_FILE_NAME_MAIN_TEST)
    assert "npc_test_001" in registry3.list_known_npc_ids()
    assert "npc_test_002" in registry3.list_known_npc_ids(), "NPC Two not loaded."
    assert len(registry3.list_known_npc_ids()) == 2, "Incorrect number of NPCs loaded after second registration."
    print(f"Registered NPC Two. Total NPCs now: {len(registry3.list_known_npc_ids())}")

    # --- Test 5: Clear registry (triggers save of empty) ---
    registry3.clear_registry()
    assert not registry3.list_known_npc_ids(), "Registry should be empty after clear."
    print("Registry cleared.")

    NPCRegistry._instance = None
    registry4 = NPCRegistry.instance(persistence_file_name=_PERSISTENCE_FILE_NAME_MAIN_TEST)
    assert not registry4.list_known_npc_ids(), "Registry not empty after clear and reload."
    print(f"NPC IDs after clear and reload: {registry4.list_known_npc_ids()}")

    # Final clean up of the temporary test file
    if os.path.exists(temp_file_path_for_test):
        os.remove(temp_file_path_for_test)
        print(f"__main__: Cleaned up temporary persistence file: {temp_file_path_for_test}")

    # Restore _instance to None so other tests (if any in same suite run) get a fresh default.
    NPCRegistry._instance = None

    print("\nNPCRegistry persistence __main__ tests completed.")
