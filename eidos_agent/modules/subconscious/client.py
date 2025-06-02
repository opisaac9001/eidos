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
from typing import Dict, Optional # Tuple was unused

# --- Configuration Placeholder ---
# In a real Eidos application, this would likely come from a central config system.
# For example: from eidos.config import get_config
# SUBCONSCIOUS_NODE_BASE_URL = get_config().subconscious_node_url
SUBCONSCIOUS_NODE_BASE_URL = "http://localhost:8000" # Default for local development
DEFAULT_TIMEOUT = 5  # seconds

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Configure basic logging if not already configured by Eidos
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Client Functions ---

def get_current_thoughts() -> Optional[Dict]:
    """
    Retrieves the current thoughts, mood, and summary from the subconscious node.

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
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get thoughts from subconscious node at {url}: {e}")
        return default_response # Or return None, depending on how Eidos should handle this
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response from subconscious node at {url}: {e}")
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

# --- Example Usage (for testing) ---
if __name__ == '__main__':
    # Ensure the subconscious_node API server is running on http://localhost:8000
    logger.info("Testing subconscious client...")

    thoughts_data = get_current_thoughts()
    if thoughts_data:
        logger.info(f"Current thoughts from Pathos: {thoughts_data.get('summary')}")
        logger.info(f"Recent: {thoughts_data.get('recent_thoughts')}")
        logger.info(f"Mood: {thoughts_data.get('mood')}")
    else:
        logger.warning("Could not retrieve thoughts from Pathos.")

    logger.info("\nAttempting to sync context...")
    conv_summary = "User said: 'Tell me about the weather.' Pathos responded: (Thinking about rain)"
    action = "user_clicked_details_button"
    
    sync_success = sync_recent_context(conv_summary, action)
    if sync_success:
        logger.info("Context synced successfully.")
    else:
        logger.warning("Context sync failed or partially failed.")

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
