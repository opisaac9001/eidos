# eidos_agent/features/firmament/core/simulator.py
import logging
from datetime import datetime, timezone

from .event_bus import EventBus
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT, THOUGHT_TRIGGER

# --- Integration Imports ---
try:
    from ..integrations.chronos_adapter import get_current_block
    from ..integrations.chronos_adapter import _set_current_block_for_testing # For __main__
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from chronos_adapter. Simulator will use dummy for get_current_block.")
    def get_current_block(): return {"id": "dummy_error_block", "name": "Error Block", "type": "error"} #type:ignore
    _set_current_block_for_testing = lambda d=None: None #type:ignore

try:
    from ..core.event_handlers.random_events import maybe_trigger_random_event
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from random_events. Simulator will not trigger random events.")
    maybe_trigger_random_event = lambda: None #type:ignore

# --- Imports for Subconscious NPC Reference Processing ---
NPC_SYSTEM_AVAILABLE = False
try:
    from ..integrations.subconscious_hook import get_recent_subconscious_thoughts
    from ..npcs.subconscious_reference_parser import extract_character_references # This is the function whose signature changed
    from ..npcs.npc_improviser import NPCImproviser
    from ..npcs.npc_registry import NPCRegistry
    NPC_SYSTEM_AVAILABLE = True
except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not import NPC system components for simulator: {e}. NPC improvisation will be disabled.")
    # Define dummies so the rest of the file can parse
    get_recent_subconscious_thoughts = lambda limit=5: [] #type:ignore
    extract_character_references = lambda thoughts, known_profiles: [] #type:ignore Signature updated in dummy
    class NPCImproviser: #type:ignore
        def __init__(self, r=None): logger.warning("Using DUMMY NPCImproviser due to import error.")
        def improvise_npc(self, nh, stc, sc): logger.warning("DUMMY NPCImproviser.improvise_npc called."); return None
    class NPCRegistry: #type:ignore
        _instance=None
        @classmethod
        def instance(cls):
            logger.warning("Using DUMMY NPCRegistry due to import error.")
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def get_all_npcs(self): return []
        # The dummy for register_npc in the prompt was (s,name,d), but the actual one in npc_registry.py is (s, npc_data)
        # Reflecting the actual signature from Step 1 (Week 1) of NPC plan for the dummy:
        def register_npc(self, npc_data): logger.warning("DUMMY NPCRegistry.register_npc called with npc_data."); return False
        # list_known_npc_names was in prompt's dummy but not used here. get_all_npcs is.


logger = logging.getLogger(__name__)
_current_active_block_data: dict | None = None
EVENT_MEMORY_WRITE = "memory.write" # Define locally, assuming it's a global constant string

def run_simulation_tick():
    global _current_active_block_data
    # logger.debug(f"Simulator: Tick start. Prev block: {_current_active_block_data.get('id') if _current_active_block_data else 'None'}")

    # --- Schedule Block Transition Logic ---
    new_block_data = get_current_block()
    if not isinstance(new_block_data, dict) or not new_block_data.get("id"):
        if _current_active_block_data:
            EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "new_block_data_invalid_or_none"})
            _current_active_block_data = None
    else:
        new_block_id = new_block_data.get("id")
        previous_block_id = _current_active_block_data.get("id") if _current_active_block_data else None
        if new_block_id != previous_block_id:
            if _current_active_block_data:
                EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "block_changed"})
            EventBus.instance().publish(SCHEDULE_BLOCK_STARTED, {"block": new_block_data})
            _current_active_block_data = new_block_data

    # --- Random World Event Triggering ---
    if callable(maybe_trigger_random_event):
        maybe_trigger_random_event()
    else: # pragma: no cover
        logger.warning("Simulator: maybe_trigger_random_event is not callable (likely import error).")

    # --- Subconscious NPC Reference Processing ---
    if NPC_SYSTEM_AVAILABLE:
        # logger.debug("Simulator: Checking for subconscious NPC references...") # Too verbose for every tick
        try:
            npc_improviser = NPCImproviser()
            registry = NPCRegistry.instance()

            recent_thoughts_data = get_recent_subconscious_thoughts(limit=5)
            if not recent_thoughts_data:
                pass
            else:
                thought_contents = [t['content'] for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t]

                known_npc_profiles = registry.get_all_npcs() # Returns List[Dict[str,Any]]

                # MODIFIED CALL: Pass known_npc_profiles (List[Dict]) directly to extract_character_references
                # This aligns with the updated signature of extract_character_references.
                new_references = extract_character_references(thought_contents, known_npc_profiles)
                # REMOVED: The temporary adaptation line that created known_npc_display_names.

                for name_hint, thought_context_text in new_references:
                    logger.info(f"Simulator: New NPC reference detected: '{name_hint}' from thought: '{thought_context_text[:70]}...'")

                    current_time_iso = datetime.now(timezone.utc).isoformat()
                    location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                    activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'
                    pathos_mood = "neutral (placeholder)" # TODO: Get actual Pathos mood

                    scene_context = {
                        "location_description": location,
                        "pathos_mood_state": pathos_mood,
                        "current_activity_name": activity,
                        "time_of_day": current_time_iso,
                    }

                    improvised_profile = npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context)

                    if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                        # NPCImproviser provides "id" and "name". NPCRegistry.register_npc expects npc_data (dict)
                        # and uses the 'id' within that data as the key.
                        success = registry.register_npc(npc_data=improvised_profile)
                        if success:
                            logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")
                            memory_payload = {
                                "type": "npc_improvised",
                                "content": f"A new persona, '{improvised_profile['name']}' (ID: {improvised_profile['id']}), was improvised by Firmament based on a thought about '{name_hint}'. Role: {improvised_profile.get('role', 'N/A')}.",
                                "metadata": {
                                    "npc_id": improvised_profile["id"],
                                    "npc_name": improvised_profile["name"],
                                    "improvised_profile_summary": {k:v for k,v in improvised_profile.items() if k not in ['initial_dialogue', 'appearance']},
                                    "triggering_thought_snippet": thought_context_text[:150],
                                    "scene_context_at_improvisation": scene_context,
                                    "timestamp": current_time_iso
                                }
                            }
                            EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)
                        else: # pragma: no cover
                            logger.error(f"Simulator: Failed to register improvised NPC '{improvised_profile['name']}' via NPCRegistry.")
                    elif improvised_profile: # pragma: no cover
                         logger.warning(f"Simulator: Improvised NPC profile for '{name_hint}' was missing 'name' or 'id', or was invalid: {str(improvised_profile)[:200]}")

        except Exception as e: # pragma: no cover
            logger.error(f"Simulator: Error during subconscious NPC reference processing: {e}", exc_info=True)
    # else: # pragma: no cover
        # logger.debug("Simulator: NPC system components not available. Skipping subconscious NPC reference processing.")

    # logger.debug("Simulator: Tick finished.")


if __name__ == '__main__': # pragma: no cover
    import unittest.mock
    from collections import defaultdict

    logging.basicConfig(level=logging.INFO)
    sim_logger = logging.getLogger('eidos_agent.features.firmament.core.simulator')
    sim_logger.setLevel(logging.DEBUG)

    _test_events_captured_sim = []
    def main_test_event_handler(event_type, data):
        _test_events_captured_sim.append({"type": event_type, "data": data})
        print(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Data Content: {str(data.get('content', data.get('block', {}).get('name', str(data))))[:100]}")

    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim = EventBus.instance()
    if hasattr(test_bus_sim, '_subscribers'): test_bus_sim._subscribers = defaultdict(list)

    event_types_for_main_test = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, IMPULSE
    ]
    # Add NPC_DIALOGUE only if it's actually defined (not a dummy)
    if 'NPC_DIALOGUE' in globals() and not isinstance(globals()['NPC_DIALOGUE'], str) or "dummy" not in str(globals()['NPC_DIALOGUE']):
        event_types_for_main_test.append(globals()['NPC_DIALOGUE'])


    for et_name_obj in event_types_for_main_test:
        actual_et_name_str = str(getattr(et_name_obj, 'value', et_name_obj))
        def create_main_handler(et_cap_name_str_arg): return lambda d: main_test_event_handler(et_cap_name_str_arg, d)
        test_bus_sim.subscribe(actual_et_name_str, create_main_handler(actual_et_name_str))

    mock_thoughts_for_sim_test = [
        {'content': "I wonder if a person named Cassandra is around here.", 'timestamp': datetime.now(timezone.utc).isoformat()},
        {'content': "Maybe Bob knows about Cassandra. I should ask Bob.", 'timestamp': datetime.now(timezone.utc).isoformat()}
    ]
    mock_improvised_cassandra_profile = {
        "id": "cassandra_improv_simtest", "name": "Cassandra (SimTest Improvised)",
        "appearance": "Mysterious aura, dark robes", "role": "Fortune Teller",
        "personality": "Enigmatic and slightly ominous", "relationship_to_pathos": "A completely new encounter",
        "initial_dialogue": "The threads of fate are often tangled, seeker."
    }

    class MockNPCRegistryForSimTest:
        def __init__(self): self.npcs_registered_in_test = {}; print("MockNPCRegistryForSimTest Initialized")
        def get_all_npcs(self): return list(self.npcs_registered_in_test.values())
        def register_npc(self, npc_data):
            npc_id = npc_data.get('id')
            if not npc_id: logger.error("MockNPCRegistry: register_npc called with no ID in npc_data."); return False
            print(f"MockNPCRegistryForSimTest: Registering NPC ID {npc_id}")
            self.npcs_registered_in_test[npc_id] = npc_data; return True

    mock_registry_instance_for_sim = MockNPCRegistryForSimTest()
    mock_registry_instance_for_sim.register_npc({"id": "bob", "name": "Bob", "presence_trigger_events": []})


    print("\n--- Testing Simulator Tick with Subconscious NPC Improvisation (Parser Change) ---")
    _current_active_block_data = None

    # Patch the global NPC_SYSTEM_AVAILABLE to True for this test if it might be False due to earlier import errors
    # Also, mock extract_character_references to simulate its new behavior (taking profiles)
    # and to control its output for the test.
    def mock_extract_references_for_sim_test(thoughts_content, known_profiles_list):
        print(f"Mocked extract_character_references called. Known profiles count: {len(known_profiles_list)}")
        # Simulate finding "Cassandra" if "Bob" is known
        if any(p.get("id") == "bob" for p in known_profiles_list):
            for thought in thoughts_content:
                if "Cassandra" in thought:
                    return [("Cassandra", thought)] # Return verbatim name and context
        return []

    with patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', True), \
         patch('eidos_agent.features.firmament.core.simulator.get_recent_subconscious_thoughts', return_value=mock_thoughts_for_sim_test) as mock_get_thoughts, \
         patch('eidos_agent.features.firmament.core.simulator.extract_character_references', side_effect=mock_extract_references_for_sim_test) as mock_extract_refs_call, \
         patch('eidos_agent.features.firmament.core.simulator.NPCImproviser.improvise_npc', return_value=mock_improvised_cassandra_profile) as mock_improvise_method, \
         patch('eidos_agent.features.firmament.core.simulator.NPCRegistry.instance', return_value=mock_registry_instance_for_sim) as mock_registry_factory, \
         patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event') as mock_random_events_call:

        _set_current_block_for_testing({"id": "test_sim_block_npc_improv", "name": "Activity During Improv", "type": "testing"})
        run_simulation_tick()

    mock_get_thoughts.assert_called_once_with(limit=5)
    mock_extract_refs_call.assert_called_once() # Check it was called
    # Verify that known_npc_profiles (a list of dicts) was passed to the mocked extract_character_references
    args_extract, _ = mock_extract_refs_call.call_args
    assert isinstance(args_extract[1], list) and all(isinstance(p, dict) for p in args_extract[1]), \
        "extract_character_references not called with a list of profiles."
    assert any(p.get("id") == "bob" for p in args_extract[1]), "Mocked Bob profile not passed to extract_character_references."

    called_with_cassandra_hint = False
    for call_args_list in mock_improvise_method.call_args_list:
        args_improv, kwargs_improv = call_args_list
        if kwargs_improv.get('name_hint') == "Cassandra":
            called_with_cassandra_hint = True
            break
    assert called_with_cassandra_hint, "NPCImproviser.improvise_npc not called with name_hint 'Cassandra'."

    assert len(mock_registry_instance_for_sim.npcs_registered_in_test) == 2, \
        f"Expected 2 NPCs in mock registry (Bob + Cassandra), got {len(mock_registry_instance_for_sim.npcs_registered_in_test)}. NPCs: {mock_registry_instance_for_sim.npcs_registered_in_test.keys()}"
    assert "cassandra_improv_simtest" in mock_registry_instance_for_sim.npcs_registered_in_test, \
        "Improvised Cassandra profile not found in mock registry by ID."

    improvised_mem_events = [e for e in _test_events_captured_sim if e['type'] == EVENT_MEMORY_WRITE and e['data'].get('type') == "npc_improvised"]
    assert len(improvised_mem_events) == 1, f"Expected 1 'npc_improvised' memory event, found {len(improvised_mem_events)}."
    if improvised_mem_events:
        assert "Cassandra (SimTest Improvised)" in improvised_mem_events[0]['data']['content']
        assert improvised_mem_events[0]['data']['metadata']['npc_id'] == "cassandra_improv_simtest"

    print("\nSubconscious NPC improvisation flow in simulator tick (with parser signature change) test completed successfully.")
    _current_active_block_data = None
    print("\n--- Simulator main test finished ---")
