# eidos_agent/services/memory_event_listener.py
import logging
from typing import Dict, Any, Optional

# This will be populated by a setter from the main application setup
_ethos_core_instance: Optional[Any] = None # Use Any to avoid circular deps if EthosCore type hint is tricky here
logger = logging.getLogger(__name__)

def set_ethos_core_for_memory_event_listener(ethos_core: Any):
    global _ethos_core_instance
    _ethos_core_instance = ethos_core
    logger.info(f"MemoryEventListener: EthosCore instance set ({_ethos_core_instance is not None}).")

async def handle_memory_write_event(memory_data: Dict[str, Any]):
    if not _ethos_core_instance:
        logger.error("MemoryEventListener: EthosCore instance not set. Cannot process 'memory.write' event.")
        return

    if not isinstance(memory_data, dict):
        logger.error(f"MemoryEventListener: Received non-dict data for 'memory.write' event: {memory_data}")
        return

    entry_type = memory_data.get("type")
    content_preview = str(memory_data.get("content", "")[:70]) + "..."
    logger.info(f"MemoryEventListener: Received 'memory.write' event. Type: '{entry_type}', Content: '{content_preview}'")

    try:
        # Determine user_id_context for add_memory_entry
        # It might be in metadata, or directly in memory_data for some simpler cases.
        user_id_from_metadata = memory_data.get('metadata', {}).get('user_id')
        user_id_direct = memory_data.get('user_id')
        user_id_context = user_id_from_metadata or user_id_direct

        # Ensure PATHOS_USER_ID is used if no specific user context and it's a Pathos-internal memory type
        if not user_id_context and entry_type in ['thought', 'reflection_insight', 'aspiration', 'subconscious_imprint', 'proactive_action_record']: # Added proactive_action_record
            # Attempt to get PATHOS_USER_ID from the EthosCore instance if available
            if hasattr(_ethos_core_instance, 'PATHOS_USER_ID'):
                user_id_context = _ethos_core_instance.PATHOS_USER_ID
            else: # Fallback if EthosCore instance doesn't have PATHOS_USER_ID directly (should not happen with real EthosCore)
                logger.warning(f"MemoryEventListener: PATHOS_USER_ID not found on EthosCore instance for memory type '{entry_type}'. User context might be missing.")

        await _ethos_core_instance.add_memory_entry(entry_data=memory_data, user_id_context=user_id_context)
        logger.info(f"MemoryEventListener: Successfully processed 'memory.write' event for type '{entry_type}'.")
    except Exception as e:
        logger.error(f"MemoryEventListener: Error processing 'memory.write' event for type '{entry_type}': {e}", exc_info=True)

if __name__ == '__main__': # Basic test placeholder
    logging.basicConfig(level=logging.DEBUG)
    logger.info("MemoryEventListener module direct run (for basic check).")
    # In a real test, you'd mock EthosCore and EventBus.
    # This main block is just to ensure the file is syntactically valid.
    class MockEthosCore:
        PATHOS_USER_ID = "test_pathos_user"
        async def add_memory_entry(self, entry_data, user_id_context):
            print(f"MockEthosCore.add_memory_entry called with type: {entry_data.get('type')}, content: '{entry_data.get('content')}', user_context: {user_id_context}")

    set_ethos_core_for_memory_event_listener(MockEthosCore())
    import asyncio
    asyncio.run(handle_memory_write_event({"type": "test_event", "content": "Test content from main."}))
    asyncio.run(handle_memory_write_event({"type": "subconscious_imprint", "content": "A test thought."}))
