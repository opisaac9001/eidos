# eidos_agent/features/firmament/core/simulator.py
import logging
from datetime import datetime, timezone

from .event_bus import EventBus
# Added NEW_NPC_IMPROVISED to imports
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT, THOUGHT_TRIGGER, NEW_NPC_IMPROVISED

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
    from ..npcs.subconscious_reference_parser import extract_character_references
    from ..npcs.npc_improviser import NPCImproviser
    from ..npcs.npc_registry import NPCRegistry
    NPC_SYSTEM_AVAILABLE = True
except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not import NPC system components for simulator: {e}. NPC improvisation will be disabled.")
    get_recent_subconscious_thoughts = lambda limit=5: [] #type:ignore
    extract_character_references = lambda thoughts, known_profiles: [] #type:ignore
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
        def register_npc(self, npc_data): logger.warning("DUMMY NPCRegistry.register_npc called with npc_data."); return False


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

    if callable(maybe_trigger_random_event):
        maybe_trigger_random_event()
    else: # pragma: no cover
        logger.warning("Simulator: maybe_trigger_random_event is not callable (likely import error).")

    if NPC_SYSTEM_AVAILABLE:
        # logger.debug("Simulator: Checking for subconscious NPC references...")
        try:
            npc_improviser = NPCImproviser()
            registry = NPCRegistry.instance()

            recent_thoughts_data = get_recent_subconscious_thoughts(limit=5)
            if recent_thoughts_data:
                thought_contents = [t['content'] for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t]
                # Create a mapping from thought content string to the original full thought payload
                original_thought_payloads = {t['content']: t for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t}

                known_npc_profiles = registry.get_all_npcs()
                new_references = extract_character_references(thought_contents, known_npc_profiles)

                for name_hint, thought_context_text in new_references:
                    logger.info(f"Simulator: New NPC reference detected: '{name_hint}' from thought: '{thought_context_text[:70]}...'")

                    current_time_iso = datetime.now(timezone.utc).isoformat()
                    location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                    activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'
                    pathos_mood = "neutral (placeholder)"

                    scene_context = {
                        "location_description": location,
                        "pathos_mood_state": pathos_mood,
                        "current_activity_name": activity,
                        "time_of_day": current_time_iso,
                    }

                    improvised_profile = npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context)

                    if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                        success = registry.register_npc(npc_data=improvised_profile)
                        if success:
                            logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")

                            # Publish EVENT_MEMORY_WRITE for the improvisation event
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

                            # --- Publish NEW_NPC_IMPROVISED event ---
                            # Retrieve the original full thought payload that triggered this specific improvisation
                            original_thought = original_thought_payloads.get(thought_context_text, {})

                            new_npc_event_payload = {
                                "improvised_npc_profile": improvised_profile, # The full profile dict
                                "triggering_thought_content": thought_context_text, # The specific thought text content
                                "original_subconscious_thought_payload": original_thought, # Full original thought dict for this reference
                                "scene_context_at_improvisation": scene_context
                            }
                            EventBus.instance().publish(NEW_NPC_IMPROVISED, new_npc_event_payload)
                            logger.info(f"Simulator: Published NEW_NPC_IMPROVISED event for NPC '{improvised_profile['name']}'.")
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
        print(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Data Content: {str(data.get('content', data.get('block', {}).get('name', str(data.get('improvised_npc_profile', {}).get('name', str(data)))))[:100]}")


    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim = EventBus.instance()
    if hasattr(test_bus_sim, '_subscribers'): test_bus_sim._subscribers = defaultdict(list)

    event_types_for_main_test = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, NEW_NPC_IMPROVISED # Added NEW_NPC_IMPROVISED
    ]
    # Add IMPULSE and NPC_DIALOGUE only if they are actually defined (not dummies)
    if 'IMPULSE' in globals() and (not isinstance(globals()['IMPULSE'], str) or "dummy" not in str(globals().get('IMPULSE',''))):
        event_types_for_main_test.append(globals()['IMPULSE'])
    if 'NPC_DIALOGUE' in globals() and (not isinstance(globals()['NPC_DIALOGUE'], str) or "dummy" not in str(globals().get('NPC_DIALOGUE',''))):
        event_types_for_main_test.append(globals()['NPC_DIALOGUE'])


    for et_name_obj in event_types_for_main_test:
        actual_et_name_str = str(getattr(et_name_obj, 'value', et_name_obj))
        def create_main_handler(et_cap_name_str_arg): return lambda d: main_test_event_handler(et_cap_name_str_arg, d)
        test_bus_sim.subscribe(actual_et_name_str, create_main_handler(actual_et_name_str))

    # Mock thought data for the test
    cassandra_thought_content = "I wonder if Cassandra is around here."
    bob_thought_content = "Maybe Bob knows about Cassandra. I should ask Bob."
    mock_thoughts_for_sim_test = [
        {'content': cassandra_thought_content, 'timestamp': datetime.now(timezone.utc).isoformat(), 'source': 'test_subconscious_cassandra'},
        {'content': bob_thought_content, 'timestamp': datetime.now(timezone.utc).isoformat(), 'source': 'test_subconscious_bob'}
    ]
    mock_improvised_cassandra_profile = {"id": "cassandra_simtest", "name": "Cassandra Improvised", "role": "Seer"}

    class MockNPCRegistryForSimMainTest:
        def __init__(self): self.npcs_registered_in_test = {}; print("MockNPCRegistryForSimMainTest Initialized")
        def get_all_npcs(self): return list(self.npcs_registered_in_test.values())
        def register_npc(self, npc_data):
            npc_id = npc_data.get('id')
            if not npc_id: logger.error("MockNPCRegistry: register_npc called with no ID in npc_data."); return False
            print(f"MockNPCRegistryForSimMainTest: Registering NPC ID {npc_id}")
            self.npcs_registered_in_test[npc_id] = npc_data; return True

    mock_registry_instance_for_sim_main = MockNPCRegistryForSimMainTest()
    mock_registry_instance_for_sim_main.register_npc({"id": "bob", "name": "Bob", "presence_trigger_events": []}) # Pre-populate Bob


    print("\n--- Testing Simulator Tick with NEW_NPC_IMPROVISED Event ---")
    _current_active_block_data = None

    with patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', True), \
         patch('eidos_agent.features.firmament.core.simulator.get_recent_subconscious_thoughts', return_value=mock_thoughts_for_sim_test) as m_get_thoughts, \
         patch('eidos_agent.features.firmament.core.simulator.extract_character_references', return_value=[("Cassandra", cassandra_thought_content)]) as m_extract_refs, \
         patch('eidos_agent.features.firmament.core.simulator.NPCImproviser.improvise_npc', return_value=mock_improvised_cassandra_profile) as m_improvise, \
         patch('eidos_agent.features.firmament.core.simulator.NPCRegistry.instance', return_value=mock_registry_instance_for_sim_main) as m_registry_factory, \
         patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event'): # Mock random events

        _set_current_block_for_testing({"id": "sim_block_new_npc", "name": "Activity New NPC", "type": "testing"})
        run_simulation_tick()

    m_improvise.assert_called_once()
    assert len(mock_registry_instance_for_sim_main.npcs_registered_in_test) == 2
    assert "cassandra_simtest" in mock_registry_instance_for_sim_main.npcs_registered_in_test

    new_npc_events = [e for e in _test_events_captured_sim if e['type'] == str(NEW_NPC_IMPROVISED)]
    assert len(new_npc_events) == 1, f"Expected 1 NEW_NPC_IMPROVISED event, found {len(new_npc_events)}."
    if new_npc_events:
        event_data = new_npc_events[0]['data']
        assert event_data['improvised_npc_profile']['id'] == "cassandra_simtest"
        assert event_data['triggering_thought_content'] == cassandra_thought_content
        # Check if the original_subconscious_thought_payload matches the first thought (about Cassandra)
        assert event_data['original_subconscious_thought_payload']['content'] == cassandra_thought_content
        assert event_data['original_subconscious_thought_payload']['source'] == 'test_subconscious_cassandra'

    print("NEW_NPC_IMPROVISED event test completed successfully.")
    _current_active_block_data = None
    print("\n--- Simulator main test finished ---")
