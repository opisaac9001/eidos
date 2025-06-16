"""
Client for interacting with the Pathos Subconscious Node API.

This module provides functions to:
- Fetch current thoughts and mood from the subconscious node.
- Inject conversation and action context into the subconscious node.

It uses the `requests` library for synchronous HTTP communication.
For asynchronous operations, `httpx` would be a suitable alternative.
"""
import requests
import logging
import json # For json.JSONDecodeError
import os # Added for os.getenv
from typing import Dict, Optional, Any # Added Any for payload typing

# --- Configuration ---
# Read from environment variable EIDOS_SUBCONSCIOUS_NODE_BASE_URL,
# with a default if not set.
SUBCONSCIOUS_NODE_BASE_URL = os.getenv("EIDOS_SUBCONSCIOUS_NODE_BASE_URL", "http://localhost:8000")
DEFAULT_TIMEOUT = 5  # seconds

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Configure basic logging if not already configured by Eidos
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Client Functions ---

def get_subconscious_thoughts_from_node() -> Optional[Dict[str, Any]]:
    """
    Retrieves the current thoughts, mood, and summary from the subconscious node.
    This is intended to be called by the Eidos agent.
    """
    url = f"{SUBCONSCIOUS_NODE_BASE_URL}/current_thoughts"
    default_response = {
        "recent_thoughts": ["The subconscious node is quiet or initializing."],
        "mood": {},
        "summary": "No summary available from subconscious node."
    }
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        return response.json()
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout connecting to subconscious node at {url} for thoughts.")
        return default_response
    except requests.exceptions.ConnectionError:
        logger.warning(f"Connection error when trying to reach subconscious node at {url} for thoughts.")
        return default_response
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code} from subconscious node at {url} for thoughts: {e.response.text[:200]}")
        return default_response
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response for thoughts from subconscious node at {url}: {e}")
        return default_response
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching thoughts from {url}: {e}", exc_info=True)
        return default_response

def get_current_thoughts() -> Optional[Dict]:
    """
    Retrieves the current thoughts, mood, and summary from the subconscious node.
    NOTE: This function seems to be a duplicate or predecessor of get_subconscious_thoughts_from_node.
    It's kept for now if other parts of the system (like the client's own test script) use it,
    but Eidos agent should prefer get_subconscious_thoughts_from_node.

    Returns:
        A dictionary containing 'recent_thoughts', 'mood', and 'summary' if successful,
        otherwise None or a default "quiet" state.
    """
    url = f"{SUBCONSCIOUS_NODE_BASE_URL}/current_thoughts"
    default_response = {"recent_thoughts": [], "mood": {}, "summary": "Pathos is quiet right now."}
    try:
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        return response.json()
    except requests.exceptions.RequestException as e: # General request exception
        logger.error(f"Failed to get thoughts (via get_current_thoughts) from subconscious node at {url}: {e}")
        return default_response
    except json.JSONDecodeError as e: # Specific JSON decode error
        logger.error(f"Failed to decode JSON response (via get_current_thoughts) from subconscious node at {url}: {e}")
        return default_response
    except Exception as e: # Catch-all for any other unexpected errors
        logger.error(f"An unexpected error occurred in get_current_thoughts at {url}: {e}", exc_info=True)
        return default_response


def sync_recent_context(conversation_history_summary: str, current_action: str) -> bool:
    """
    Injects recent conversation summary and current action context into the subconscious node.

    Args:
        conversation_history_summary: A string summarizing recent conversation.
        current_action: A string describing the current or most recent user action.

    Returns:
        True if both injections were successful (or at least accepted with 2xx status),
        False otherwise.
    """
    conversation_url = f"{SUBCONSCIOUS_NODE_BASE_URL}/inject/conversation"
    action_url = f"{SUBCONSCIOUS_NODE_BASE_URL}/inject/action"

    success_conversation = False
    success_action = False

    # Inject conversation context
    try:
        payload_conv = {"content": conversation_history_summary}
        response_conv = requests.post(conversation_url, json=payload_conv, timeout=DEFAULT_TIMEOUT)
        response_conv.raise_for_status()
        logger.info(f"Successfully injected conversation context: {conversation_history_summary[:100]}...")
        success_conversation = True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to inject conversation context at {conversation_url}: {e}")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred during conversation context injection: {e}")

    # Inject action context
    try:
        payload_action = {"content": current_action}
        response_action = requests.post(action_url, json=payload_action, timeout=DEFAULT_TIMEOUT)
        response_action.raise_for_status()
        logger.info(f"Successfully injected action context: {current_action}")
        success_action = True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to inject action context at {action_url}: {e}")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred during action context injection: {e}")

    return success_conversation and success_action


def send_node_control_command(node_state: str, daily_summary: Optional[str] = None) -> bool:
    """
    Sends a control command to the subconscious node to change its state
    and optionally provide a daily summary for dreaming.

    Args:
        node_state: The new state for the node (e.g., "AWAKE_THINKING", "SLEEPING_DREAMING").
        daily_summary: An optional string containing the summary of the day's events.

    Returns:
        True if the command was successfully sent (2xx status), False otherwise.
    """
    url = f"{SUBCONSCIOUS_NODE_BASE_URL}/control/state"
    payload: Dict[str, Any] = {"node_state": node_state}
    if daily_summary is not None:
        payload["daily_summary"] = daily_summary

    logger.info(f"Sending control command to subconscious node: State='{node_state}', Summary provided='{daily_summary is not None}'")
    try:
        response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        # The /control/state endpoint returns a MessageResponse which is JSON.
        # We can optionally log the message from the response.
        try:
            response_data = response.json()
            logger.info(f"Subconscious node control command successful. Response: {response_data.get('message', 'No message field.')}")
        except json.JSONDecodeError:
            # This might happen if the response is 2xx but not JSON, or empty.
            # For /control/state, it should be JSON, but good to be robust.
            logger.info(f"Subconscious node control command successful (status {response.status_code}), but no valid JSON response body.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send control command to subconscious node at {url}: {e}")
        return False
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred during node control command: {e}")
        return False


def sync_mood_to_subconscious(mood_snapshot: Dict[str, float]) -> bool:
    """
    Synchronizes the current mood snapshot from Eidos to the subconscious node.

    Args:
        mood_snapshot: A dictionary representing the current mood aspects and their values.

    Returns:
        True if the mood was successfully synced (2xx status), False otherwise.
    """
    url = f"{SUBCONSCIOUS_NODE_BASE_URL}/control/mood"
    payload = {"mood_aspects": mood_snapshot}

    logger.info(f"Syncing mood to subconscious node: {mood_snapshot}")
    try:
        response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        try:
            response_data = response.json()
            logger.info(f"Subconscious node mood sync successful. Response: {response_data.get('message', 'No message field.')}")
        except json.JSONDecodeError:
            logger.info(f"Subconscious node mood sync successful (status {response.status_code}), but no valid JSON response body.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to sync mood to subconscious node at {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during mood sync: {e}")
        return False

def push_dream_fragment_to_node(dream_content: str) -> bool:
    """
    Pushes a single dream fragment (string) to the subconscious node.
    """
    url = f"{SUBCONSCIOUS_NODE_BASE_URL}/inject/dream_fragment"
    payload = {"content": dream_content}

    logger.debug(f"Pushing dream fragment to subconscious node: '{dream_content[:100]}...' at {url}")
    try:
        response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        try:
            response_data = response.json()
            logger.info(f"Dream fragment push successful. Response: {response_data.get('message', 'No message field.')}")
        except json.JSONDecodeError:
            logger.info(f"Dream fragment push successful (status {response.status_code}), but no valid JSON response body.")
        return True
    except requests.exceptions.Timeout:
        logger.error(f"Timeout pushing dream fragment to subconscious node at {url}.")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error pushing dream fragment to subconscious node at {url}.")
        return False
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error {e.response.status_code} pushing dream fragment to subconscious node at {url}: {e.response.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred pushing dream fragment: {e}", exc_info=True)
        return False

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    # Ensure the subconscious_node API server is running on http://localhost:8000
    logger.info("Testing subconscious client...")

    logger.info("\n--- Testing get_subconscious_thoughts_from_node ---")
    eidos_thoughts = get_subconscious_thoughts_from_node()
    if eidos_thoughts:
        logger.info(f"Eidos received thoughts: {eidos_thoughts.get('summary')}")
        logger.info(f"Recent from Eidos perspective: {eidos_thoughts.get('recent_thoughts')}")
        logger.info(f"Mood from Eidos perspective: {eidos_thoughts.get('mood')}")
    else: # Should not happen if default_response is always returned on error
        logger.warning("Eidos could not retrieve thoughts (received None). This indicates an issue in error handling.")

    # Optional: Test the older get_current_thoughts if needed for compatibility checks
    # logger.info("\n--- Testing get_current_thoughts (legacy/test usage) ---")
    # legacy_thoughts_data = get_current_thoughts()
    # if legacy_thoughts_data:
    #     logger.info(f"Legacy thoughts: {legacy_thoughts_data.get('summary')}")
    # else:
    #     logger.warning("Legacy could not retrieve thoughts.")


    logger.info("\nAttempting to sync context...")
    conv_summary = "User said: 'Tell me about the weather.' Pathos responded: (Thinking about rain)"
    action = "user_clicked_details_button"

    sync_success = sync_recent_context(conv_summary, action)
    if sync_success:
        logger.info("Context synced successfully.")
    else:
        logger.warning("Context sync failed or partially failed.")

    logger.info("\nAttempting to send control commands...")
    control_success_dream = send_node_control_command("SLEEPING_DREAMING", "Today was eventful, user seemed happy.")
    if control_success_dream:
        logger.info("Control command (SLEEPING_DREAMING with summary) sent successfully.")
    else:
        logger.warning("Control command (SLEEPING_DREAMING with summary) failed.")

    control_success_awake = send_node_control_command("AWAKE_THINKING")
    if control_success_awake:
        logger.info("Control command (AWAKE_THINKING) sent successfully.")
    else:
        logger.warning("Control command (AWAKE_THINKING) failed.")

    logger.info("\nAttempting to sync mood...")
    sample_mood = {"valence": 0.2, "arousal": 0.6, "impulsiveness": 0.7}
    mood_sync_success = sync_mood_to_subconscious(sample_mood)
    if mood_sync_success:
        logger.info(f"Mood sync for {sample_mood} successful.")
    else:
        logger.warning(f"Mood sync for {sample_mood} failed.")

    another_mood = {"valence": -0.5, "arousal": 0.3, "proactivity": 0.2}
    mood_sync_success_2 = sync_mood_to_subconscious(another_mood)
    if mood_sync_success_2:
        logger.info(f"Mood sync for {another_mood} successful.")
    else:
        logger.warning(f"Mood sync for {another_mood} failed.")


    # Test with a potentially non-running server to see error logging
    # SUBCONSCIOUS_NODE_BASE_URL = "http://localhost:8001" # Non-existent server
    # logger.info("\nTesting with a non-existent server:")
    # thoughts_data_fail = get_current_thoughts()
    # if not thoughts_data_fail or thoughts_data_fail["summary"] == "Pathos is quiet right now.":
    #     logger.info("Correctly handled non-existent server for get_current_thoughts.")
    # else:
    #     logger.error(f"Unexpected response from non-existent server: {thoughts_data_fail}")

    # sync_fail = sync_recent_context("test conv", "test action")
    # if not sync_fail:
    #     logger.info("Correctly handled non-existent server for sync_recent_context.")
    # else:
    #     logger.error("sync_recent_context reported success with non-existent server.")

    logger.info("\nAttempting to push a dream fragment...")
    dream_push_success = push_dream_fragment_to_node("A fleeting image of a clock without hands.")
    if dream_push_success:
        logger.info("Dream fragment pushed successfully (test).")
    else:
        logger.warning("Dream fragment push failed (test).")

    dream_push_success_2 = push_dream_fragment_to_node("The scent of old books and distant rain.")
    if dream_push_success_2:
        logger.info("Second dream fragment pushed successfully (test).")
    else:
        logger.warning("Second dream fragment push failed (test).")


    # To use httpx for async operations, you would do something like:
    # import httpx
    # async def get_current_thoughts_async():
    #     async with httpx.AsyncClient() as client:
    #         try:
    #             response = await client.get(f"{SUBCONSCIOUS_NODE_BASE_URL}/current_thoughts", timeout=DEFAULT_TIMEOUT)
    #             response.raise_for_status()
    #             return response.json()
    #         except httpx.RequestError as e:
    #             logger.error(f"Async: Failed to get thoughts: {e}")
    #             return None
    #         except httpx.HTTPStatusError as e:
    #             logger.error(f"Async: HTTP error {e.response.status_code} while getting thoughts: {e}")
    #             return None
    # # And then run it within an asyncio event loop:
    # # import asyncio
    # # async def main():
    # #     data = await get_current_thoughts_async()
    # #     print(data)
    # # asyncio.run(main())
