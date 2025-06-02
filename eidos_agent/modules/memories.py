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

# Define Storage Path
IMPRINTS_DIR = "eidos_memories"
IMPRINTS_FILE_PATH = os.path.join(IMPRINTS_DIR, "pathos_subconscious_imprints.jsonl")

def store_imprint(content: str, timestamp: str, mood: Dict[str, Any], topics: List[str]) -> Dict[str, Any]:
    """
    Stores a memory imprint received from the subconscious node persistently to a JSONL file.

    The function ensures the storage directory exists, prepares the imprint data,
    and appends it as a JSON line to the specified file.

    Args:
        content: The textual content of the memory imprint.
        timestamp: The ISO 8601 timestamp of when the imprint was generated.
        mood: A dictionary representing the mood snapshot associated with the imprint.
        topics: A list of keywords or topics related to the imprint.

    Returns:
        A dictionary indicating the status of the storage operation, including
        the file path on success or an error message on failure.
    """
    logger.info(f"MEMORIES: Received subconscious imprint for persistent storage.")

    try:
        # Ensure Directory Exists
        if not os.path.exists(IMPRINTS_DIR):
            os.makedirs(IMPRINTS_DIR, exist_ok=True)
            logger.info(f"MEMORIES: Created directory for imprints at '{IMPRINTS_DIR}'.")

        # Prepare Imprint Data
        imprint_data = {
            "timestamp": timestamp,
            "content": content,
            "mood_snapshot": mood, # 'mood' parameter is used as the mood_snapshot
            "topics": topics
        }

        # Append to File
        with open(IMPRINTS_FILE_PATH, 'a') as f:
            f.write(json.dumps(imprint_data) + '\n')
        
        logger.info(f"MEMORIES: Successfully stored imprint to '{IMPRINTS_FILE_PATH}'. Content: '{content[:100]}...'")
        return {
            "status": "imprint successfully stored",
            "file_path": IMPRINTS_FILE_PATH,
            "imprint_content": content
        }
    except IOError as e:
        logger.error(f"MEMORIES: IOError while storing imprint to '{IMPRINTS_FILE_PATH}': {e}")
        return {"status": "failed to store imprint", "error": str(e), "imprint_content": content}
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"MEMORIES: Unexpected error while storing imprint: {e}", exc_info=True)
        return {"status": "failed to store imprint", "error": str(e), "imprint_content": content}

if __name__ == '__main__':
    print("--- Testing memories.store_imprint (Persistent Storage) ---")
    
    # Clean up existing file for a fresh test run, if it exists
    if os.path.exists(IMPRINTS_FILE_PATH):
        os.remove(IMPRINTS_FILE_PATH)
        print(f"Removed existing test file: {IMPRINTS_FILE_PATH}")
    if os.path.exists(IMPRINTS_DIR) and not os.listdir(IMPRINTS_DIR): # remove dir if it's empty
        os.rmdir(IMPRINTS_DIR)
        print(f"Removed empty test directory: {IMPRINTS_DIR}")


    imprints_to_store = [
        {
            "content": "Realized that consistent effort, even small, leads to big results.",
            "timestamp": "2023-10-27T11:00:00Z",
            "mood": {"name": "Reflective", "clarity": 0.9},
            "topics": ["realization", "effort", "consistency"]
        },
        {
            "content": "The sound of rain can be incredibly soothing.",
            "timestamp": "2023-10-27T11:05:00Z",
            "mood": {"name": "Calm", "peacefulness": 0.8},
            "topics": ["nature", "sound", "rain", "soothing"]
        },
        {
            "content": "A moment of sudden inspiration for a new project idea.",
            "timestamp": "2023-10-27T11:10:00Z",
            "mood": {"name": "Excited", "energy": 0.85},
            "topics": ["creativity", "ideas", "inspiration"]
        }
    ]

    results = []
    for i, imprint_args in enumerate(imprints_to_store):
        print(f"\nStoring imprint {i+1}...")
        result = store_imprint(**imprint_args)
        print(f"Result: {result}")
        results.append(result)

    print("\n--- Verification ---")
    successful_stores = [res for res in results if res["status"] == "imprint successfully stored"]
    print(f"Successfully stored {len(successful_stores)} out of {len(imprints_to_store)} imprints.")
    assert len(successful_stores) == len(imprints_to_store), "Not all imprints were stored successfully."

    if os.path.exists(IMPRINTS_FILE_PATH):
        print(f"\nContents of '{IMPRINTS_FILE_PATH}':")
        line_count = 0
        try:
            with open(IMPRINTS_FILE_PATH, 'r') as f:
                for line in f:
                    print(f"  {line.strip()}")
                    # Verify it's valid JSON
                    json.loads(line.strip())
                    line_count += 1
            print(f"Total imprints in file: {line_count}")
            assert line_count == len(imprints_to_store), "Number of lines in file does not match number of imprints stored."
        except Exception as e:
            print(f"Error reading or verifying file content: {e}")
            assert False, "Error during file content verification."
    else:
        print(f"Error: Imprints file '{IMPRINTS_FILE_PATH}' was not created.")
        assert False, "Imprints file not created."

    print("\nPersistent storage tests completed. Verify logs for detailed output.")

    # To simulate an error (e.g., permission denied), you might temporarily change permissions
    # on IMPRINTS_DIR or IMPRINTS_FILE_PATH manually before running a test call.
    # For example, on Linux/macOS:
    # os.chmod(IMPRINTS_DIR, 0o444) # Read-only
    # error_result = store_imprint("This should fail.", "2023-10-27T12:00:00Z", {}, [])
    # print(f"\nError simulation result: {error_result}")
    # assert error_result["status"] == "failed to store imprint"
    # os.chmod(IMPRINTS_DIR, 0o755) # Restore permissions
    # print("Error simulation test (manual setup) would appear above.")
