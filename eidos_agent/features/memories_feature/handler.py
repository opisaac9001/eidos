"""
Eidos Agent Memories Module.

This module is responsible for handling the persistent storage of significant
information, such as "imprints" received from the Pathos Subconscious Node.
Imprints are stored in a JSONL file for durability and later retrieval or analysis.
"""
import logging
import json
import os
from typing import List, Dict, Any

# Configure basic logging if not already configured by Eidos
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# NOTE: The EthosCore instance would typically be accessed via
# a dependency injection mechanism or a global application context in a FastAPI app.
# from eidos_agent.main import get_ethos_core # Hypothetical access
ETHOS_CORE_INSTANCE = None # Placeholder
DEFAULT_SALIENCE_FOR_IMPRINT = 0.6

# Attempt to import PATHOS_USER_ID, provide a fallback if not found
try:
    from eidos_agent.persona_logic.chronos_engine.engine import PATHOS_USER_ID
except ImportError:
    PATHOS_USER_ID = "pathos_agent_internal" # Fallback if direct import fails

def set_ethos_core_instance(instance): # Helper for testing or app setup
    global ETHOS_CORE_INSTANCE
    ETHOS_CORE_INSTANCE = instance

async def store_imprint(content: str, timestamp: str, mood: Dict[str, Any], topics: List[str]) -> Dict[str, Any]:
    """
    Stores a memory imprint received from the subconscious node by adding it
    to EthosCore.

    Args:
        content: The textual content of the memory imprint.
        timestamp: The ISO 8601 timestamp of when the imprint was generated.
        mood: A dictionary representing the mood snapshot associated with the imprint.
        topics: A list of keywords or topics related to the imprint.

    Returns:
        A dictionary indicating the status of the storage operation.
    """
    logger.info(f"MEMORIES HANDLER: Received imprint for EthosCore storage: '{content[:100]}...'")

    if not ETHOS_CORE_INSTANCE:
        logger.error("MEMORIES HANDLER: EthosCore instance not available. Cannot store imprint.")
        return {"status": "error", "detail": "EthosCore not configured"}

    entry_data = {
        "type": "subconscious_imprint", # Or "pathos_realization", "subconscious_insight"
        "content": content,
        "metadata": {
            "source": "subconscious_node_hook", # Clearly mark it came via this hook
            "original_timestamp": timestamp, # Timestamp from subconscious node
            "mood_at_imprint": mood, # Mood from subconscious node
            "topics_from_imprint": topics, # Topics from subconscious node
            # Potentially add other relevant info from ImprintData if it evolves
        },
        "salience": DEFAULT_SALIENCE_FOR_IMPRINT
    }

    try:
        # EthosCore.add_memory_entry is typically async
        memory_record = await ETHOS_CORE_INSTANCE.add_memory_entry(
            entry_data=entry_data,
            user_id_context=PATHOS_USER_ID
        )
        if memory_record and hasattr(memory_record, 'id') and memory_record.id:
            logger.info(f"MEMORIES HANDLER: Imprint successfully stored in EthosCore with ID {memory_record.id}. Content: '{content[:100]}...'")
            return {
                "status": "imprint_stored_in_ethos",
                "memory_id": memory_record.id,
                "imprint_content": content
            }
        else:
            logger.warning(f"MEMORIES HANDLER: EthosCore.add_memory_entry did not return a valid record or ID for imprint: '{content[:100]}...'")
            return {"status": "failed_to_store_imprint_in_ethos", "detail": "EthosCore returned no ID", "imprint_content": content}

    except Exception as e:
        logger.exception(f"MEMORIES HANDLER: Error calling EthosCore.add_memory_entry for imprint '{content[:100]}...'")
        return {"status": "error_processing_imprint", "detail": str(e)}


if __name__ == '__main__':
    print("--- Testing memories_feature.handler.store_imprint (mocked EthosCore) ---")

    # Mock EthosCore and its method for testing
    class MockEthosCore:
        async def add_memory_entry(self, entry_data: Dict[str, Any], user_id_context: str) -> Any:
            print(f"MockEthosCore.add_memory_entry called:")
            print(f"  User ID Context: {user_id_context}")
            print(f"  Entry Data: {json.dumps(entry_data, indent=2)}")
            if "error" in entry_data["content"].lower():
                raise ValueError("Simulated error in EthosCore")

            # Simulate a returned memory record object with an ID
            class MockMemoryRecord:
                def __init__(self, id_val):
                    self.id = id_val

            return MockMemoryRecord(id_val=f"mock_mem_{hash(entry_data['content'])}")

    # Set the mock instance for the handler to use
    mock_ethos_instance = MockEthosCore()
    set_ethos_core_instance(mock_ethos_instance)
    print("MockEthosCore instance set.")

    import asyncio

    async def run_tests():
        imprints_to_store = [
            {
                "content": "Realized that consistent effort, even small, leads to big results.",
                "timestamp": "2023-10-27T11:00:00Z",
                "mood": {"name": "Reflective", "clarity": 0.9, "valence": 0.6, "arousal": 0.3},
                "topics": ["realization", "effort", "consistency"]
            },
            {
                "content": "The sound of rain can be incredibly soothing.",
                "timestamp": "2023-10-27T11:05:00Z",
                "mood": {"name": "Calm", "peacefulness": 0.8, "valence": 0.5, "arousal": 0.1},
                "topics": ["nature", "sound", "rain", "soothing"]
            },
            {
                "content": "A moment of sudden inspiration for a new project idea with error.",
                "timestamp": "2023-10-27T11:10:00Z",
                "mood": {"name": "Excited", "energy": 0.85, "valence": 0.8, "arousal": 0.7},
                "topics": ["creativity", "ideas", "inspiration"]
            }
        ]

        for i, imprint_args in enumerate(imprints_to_store):
            print(f"\nStoring imprint {i+1}...")
            result = await store_imprint(**imprint_args)
            print(f"Result from handler: {result}")
            if "error" in imprint_args["content"].lower():
                assert result["status"] == "error_processing_imprint"
            else:
                assert result["status"] == "imprint_stored_in_ethos"
                assert "memory_id" in result

        # Test case where EthosCore is not set
        set_ethos_core_instance(None)
        print("\nEthosCore instance unset for next test.")
        result_no_ec = await store_imprint(**imprints_to_store[0])
        print(f"Result with no EthosCore: {result_no_ec}")
        assert result_no_ec["status"] == "error"
        assert result_no_ec["detail"] == "EthosCore not configured"

    asyncio.run(run_tests())
    print("\nMemories feature handler tests completed.")
