# eidos_agent/features/firmament/npcs/npc_registry.py
import logging
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)

class NPCRegistry:
    """
    Handles in-memory storage and identity tracking for all known NPCs.
    NPCs are primarily keyed by a normalized version of their unique ID.
    This registry is intended to be a singleton or a shared instance within Firmament.
    """
    _instance: Optional['NPCRegistry'] = None

    def __init__(self):
        """
        Initializes the NPCRegistry.
        The constructor should ideally not be called directly if using the singleton pattern.
        Use NPCRegistry.instance() instead.
        """
        if NPCRegistry._instance is not None: # pragma: no cover
            # This can happen if __init__ is called directly after instance() has been used.
            # Or, if the class is instantiated multiple times without the singleton pattern being strictly enforced.
            logger.warning("NPCRegistry already initialized. This might indicate multiple instances are being created.")
            # To ensure we don't overwrite, we can either raise an error or just use the existing one.
            # For simplicity here, we'll allow re-initialization of the current object's state,
            # but the singleton `_instance` will point to the first one created via `instance()`.

        # Stores NPC data, keyed by NPC's unique ID (expected to be normalized, e.g., lowercase string).
        # Example: {"lara_croft_id": {"id": "lara_croft_id", "name": "Lara Croft", ...}}
        self._known_npcs: Dict[str, Dict[str, Any]] = {}
        # logger.info("NPCRegistry initialized (in-memory store).") # Logged by instance() usually

    @classmethod
    def instance(cls) -> 'NPCRegistry':
        """Provides access to the singleton instance of NPCRegistry."""
        if cls._instance is None:
            logger.info("Creating new NPCRegistry singleton instance.")
            cls._instance = cls()
        return cls._instance

    def _normalize_id(self, npc_id: str) -> str:
        """Normalizes an NPC ID to be used as a consistent key (e.g., lowercased, spaces replaced)."""
        if not npc_id or not isinstance(npc_id, str): # Basic validation
            return ""
        return npc_id.strip().lower().replace(" ", "_")

    def get_npc_by_id(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves NPC data by their unique ID.

        Args:
            npc_id (str): The unique ID of the NPC to retrieve. Case-insensitive, spaces handled.

        Returns:
            Optional[Dict[str, Any]]: The NPC data dictionary if found, else None.
        """
        normalized_id_key = self._normalize_id(npc_id)
        if not normalized_id_key:
            logger.warning("get_npc_by_id called with empty or invalid npc_id.")
            return None

        npc_data = self._known_npcs.get(normalized_id_key)
        # if npc_data:
            # logger.debug(f"NPC with ID '{npc_id}' (normalized: {normalized_id_key}) found in registry.")
        # else:
            # logger.debug(f"NPC with ID '{npc_id}' (normalized: {normalized_id_key}) not found in registry.")
        return npc_data # Consider returning a copy if mutable: return copy.deepcopy(npc_data)

    def register_npc(self, npc_data: Dict[str, Any]) -> bool:
        """
        Registers a new NPC or updates an existing one based on the 'id' field in npc_data.
        The 'id' from npc_data will be normalized for keying.

        Args:
            npc_data (Dict[str, Any]): The dictionary containing the NPC's profile data.
                                       Must include an 'id' field (string) and preferably a 'name' field.

        Returns:
            bool: True if registration/update was successful, False otherwise.
        """
        if not isinstance(npc_data, dict):
            logger.error("Cannot register NPC: npc_data is not a dictionary.")
            return False

        npc_id_from_data = npc_data.get('id')
        if not isinstance(npc_id_from_data, str) or not npc_id_from_data.strip():
            logger.error(f"Cannot register NPC: 'id' field is missing, not a string, or empty in npc_data: {str(npc_data)[:100]}")
            return False

        normalized_id_key = self._normalize_id(npc_id_from_data)

        # Ensure 'name' exists, default to id if not
        if 'name' not in npc_data or not npc_data['name']:
            logger.warning(f"NPC data for ID '{normalized_id_key}' is missing a 'name'. Defaulting name to ID.")
            npc_data['name'] = npc_id_from_data # Use original non-normalized ID as name if name is missing

        if normalized_id_key in self._known_npcs:
            logger.info(f"Updating existing NPC in registry with ID: '{normalized_id_key}' (Name: '{npc_data['name']}').")
        else:
            logger.info(f"Registering new NPC with ID: '{normalized_id_key}' (Name: '{npc_data['name']}').")

        self._known_npcs[normalized_id_key] = npc_data
        # TODO: Implement persistence logic here (e.g., save to file/DB) if registry needs to persist beyond session.
        # logger.debug(f"NPC data for '{normalized_id_key}': {npc_data}")
        return True

    def list_known_npc_ids(self) -> List[str]:
        """Returns a list of (normalized) IDs of all known NPCs."""
        return list(self._known_npcs.keys())

    def get_all_npcs(self) -> List[Dict[str, Any]]:
        """Returns a list of all NPC data dictionaries."""
        return list(self._known_npcs.values()) # Consider returning deep copies if mutable

    def clear_registry(self): # Useful for testing or full reset
        """Clears all NPCs from the registry."""
        self._known_npcs.clear()
        logger.info("NPCRegistry cleared of all NPC data.")

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Show debug logs for __main__

    # Use the singleton instance for operations
    registry = NPCRegistry.instance()
    print(f"Initial known NPC IDs: {registry.list_known_npc_ids()}")

    # Register Lara
    lara_data = {
        "id": "lara_croft_adventurer", # Unique ID
        "name": "Lara Croft",
        "appearance": "athletic, brown ponytail",
        "role": "Archaeologist",
        "initial_dialogue": "The world is full of secrets, waiting to be found."
    }
    registry.register_npc(lara_data)

    # Register Drake
    drake_data = {
        "id": "nathan_drake_explorer", # Unique ID
        "name": "Nathan Drake",
        "appearance": "half-tucked shirt, ruggedly handsome",
        "role": "Treasure Hunter",
        "initial_dialogue": "Fortune favors the bold, right?"
    }
    registry.register_npc(drake_data)

    print(f"Known NPC IDs after registration: {registry.list_known_npc_ids()}")
    print(f"All NPC data list: {registry.get_all_npcs()}")


    # Get Lara by her ID
    retrieved_lara = registry.get_npc_by_id("lara_croft_adventurer")
    print(f"Retrieved Lara (by ID 'lara_croft_adventurer'): {'Found' if retrieved_lara else 'Not Found'}")
    if retrieved_lara: assert retrieved_lara["role"] == "Archaeologist"

    retrieved_lara_case_insensitive = registry.get_npc_by_id("LARA_CROFT_ADVENTURER") # Test case insensitivity
    print(f"Retrieved Lara (by ID 'LARA_CROFT_ADVENTURER'): {'Found' if retrieved_lara_case_insensitive else 'Not Found'}")
    if retrieved_lara_case_insensitive: assert retrieved_lara_case_insensitive["appearance"] == "athletic, brown ponytail"

    # Get Drake by his ID
    retrieved_drake = registry.get_npc_by_id("nathan_drake_explorer")
    print(f"Retrieved Drake (by ID 'nathan_drake_explorer'): {'Found' if retrieved_drake else 'Not Found'}")
    if retrieved_drake: assert retrieved_drake["name"] == "Nathan Drake"

    # Attempt to get non-existent NPC
    retrieved_ghost = registry.get_npc_by_id("ghost_npc")
    print(f"Retrieved Ghost NPC (by ID 'ghost_npc'): {'Found' if retrieved_ghost else 'Not Found'}")
    assert retrieved_ghost is None

    # Update Lara's data (by re-registering with the same ID)
    updated_lara_data = {
        "id": "lara_croft_adventurer",
        "name": "Lara Croft",
        "appearance": "athletic, brown ponytail, now with a determined glint",
        "role": "Seasoned World-Class Archaeologist", # Role updated
        "initial_dialogue": "Some things are best left undisturbed... but not by me."
    }
    registry.register_npc(updated_lara_data)
    retrieved_lara_updated = registry.get_npc_by_id("lara_croft_adventurer")
    if retrieved_lara_updated:
        print(f"Updated Lara's role: {retrieved_lara_updated.get('role')}")
        assert retrieved_lara_updated.get('role') == "Seasoned World-Class Archaeologist"

    # Test registration with missing 'id' in data (should fail)
    invalid_data_no_id = {"name": "Nameless Wonder", "role": "Mystery"}
    print(f"Attempting to register NPC with missing 'id': {registry.register_npc(invalid_data_no_id)}")
    assert registry.get_npc_by_id("nameless_wonder") is None # Should not be registered under name either

    # Test registration with empty 'id' string
    invalid_data_empty_id = {"id": "  ", "name": "Empty ID Test", "role": "Void"}
    print(f"Attempting to register NPC with empty 'id': {registry.register_npc(invalid_data_empty_id)}")


    # Test clearing the registry
    registry.clear_registry()
    print(f"Known NPC IDs after clearing: {registry.list_known_npc_ids()}")
    assert len(registry.list_known_npc_ids()) == 0

    # Test singleton behavior
    registry1 = NPCRegistry.instance()
    registry2 = NPCRegistry.instance()
    assert registry1 is registry2, "NPCRegistry.instance() should return the same instance."
    registry1.register_npc({"id": "test_singleton", "name": "Singleton Sam"})
    assert registry2.get_npc_by_id("test_singleton") is not None, "Change in one instance should reflect in other via singleton."

    print("\nNPCRegistry __main__ tests completed.")
