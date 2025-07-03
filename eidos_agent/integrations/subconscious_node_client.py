import logging
import httpx
from typing import List, Optional, Dict, Any

from ..core.config import Config
from ..features.firmament.core.http_client_manager import HTTPClientManager # Assuming it might move to core later
from ..schemas.subconscious_schemas import SubconsciousThought, SubconsciousInjectType, SubconsciousControlState

logger = logging.getLogger(__name__)

class SubconsciousNodeClient:
    """
    Client for interacting with the external Subconscious Node API.
    """
    def __init__(self, config: Config, http_client_manager: HTTPClientManager):
        self.config = config
        subconscious_config = config.get_nested_value(config.SYSTEM_NODES_CONFIG, ['subconscious_node'], {})
        self.api_base_url = subconscious_config.get('api_base_url', 'http://localhost:8000') # Default from subconscious_orchestrator

        # Get the shared client from the manager
        self.http_client = http_client_manager.get_client()
        if not self.http_client:
            logger.error("SubconsciousNodeClient: Failed to get HTTP client from HTTPClientManager. API calls will fail.")
            # You might want to raise an error here or handle it more gracefully if http_client can't be obtained.
            # For now, it will lead to errors in the methods below if self.http_client is None.

        logger.info(f"SubconsciousNodeClient initialized. API Base URL: {self.api_base_url}")

    async def _request(self, method: str, endpoint: str, json_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Helper method to make requests to the Subconscious Node API."""
        if not self.http_client:
            logger.error(f"SubconsciousNodeClient: HTTP client not available for request to {endpoint}.")
            return {"success": False, "error": "HTTP client not available."}

        url = f"{self.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = await self.http_client.request(method, url, json=json_payload, timeout=10.0) # Standard timeout
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            return {"success": True, "data": response.json()}
        except httpx.HTTPStatusError as e:
            logger.error(f"SubconsciousNode API error for {method} {url}: {e.response.status_code} - {e.response.text[:200]}", exc_info=False)
            return {"success": False, "status_code": e.response.status_code, "error": f"API Error: {e.response.status_code} - {e.response.text[:100]}..."}
        except httpx.RequestError as e:
            logger.error(f"SubconsciousNode request error for {method} {url}: {e}", exc_info=False)
            return {"success": False, "error": f"Request Error: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error in SubconsciousNodeClient._request for {method} {url}: {e}", exc_info=True)
            return {"success": False, "error": f"Unexpected Error: {str(e)}"}

    async def get_significant_thoughts(self, limit: int = 3) -> List[SubconsciousThought]:
        """
        Fetches recent/significant thoughts from the SubconsciousNode's /current_thoughts endpoint.
        The Subconscious Node API returns:
        {
            "recent_thoughts": List[str], # Raw thought strings
            "mood": Dict,
            "summary": str
        }
        This client method will attempt to map these to SubconsciousThought Pydantic models.
        Actual "significance" scoring might be basic (e.g., just latest) or need more from API.
        """
        logger.debug(f"Fetching {limit} significant thoughts from Subconscious Node.")
        response_dict = await self._request("GET", "/current_thoughts")

        thoughts: List[SubconsciousThought] = []
        if response_dict.get("success"):
            data = response_dict.get("data", {})
            raw_thought_strings = data.get("recent_thoughts", [])
            mood_snapshot = data.get("mood", {}) # Mood from the subconscious node itself

            for i, thought_content in enumerate(raw_thought_strings[:limit]):
                # Create a simple ID and use current time as timestamp_recorded by client
                # A more robust system might have SubconsciousNode provide IDs and timestamps.
                thoughts.append(
                    SubconsciousThought(
                        thought_id=f"subthought_{uuid.uuid4().hex[:8]}", # Generate an ID
                        timestamp_recorded=datetime.utcnow(), # Timestamp of retrieval
                        content=str(thought_content),
                        mood_at_thought=mood_snapshot, # Mood of the subconscious node at time of thought batch
                        # Salience, keywords, etc., would need to come from SubconsciousNode API if desired
                    )
                )
            logger.info(f"Retrieved {len(thoughts)} thoughts from Subconscious Node.")
        else:
            logger.warning(f"Failed to get thoughts from Subconscious Node: {response_dict.get('error')}")
        return thoughts

    async def inject_context_to_node(self, context_type: str, content: str) -> bool:
        """
        Injects context (e.g., 'conversation', 'action', 'dream_fragment') to the SubconsciousNode.
        Valid context_types: "dream_fragment", "conversation", "action".
        """
        valid_types = ["dream_fragment", "conversation", "action"]
        if context_type.lower() not in valid_types:
            logger.error(f"Invalid context_type '{context_type}' for inject_context_to_node. Must be one of {valid_types}.")
            return False

        endpoint = f"inject/{context_type.lower()}"
        payload = SubconsciousInjectType(content=content)

        logger.debug(f"Injecting context type '{context_type}' to Subconscious Node: '{content[:70]}...'")
        response_dict = await self._request("POST", endpoint, json_payload=payload.model_dump())

        if response_dict.get("success"):
            logger.info(f"Successfully injected context type '{context_type}' to Subconscious Node.")
            return True
        else:
            logger.warning(f"Failed to inject context to Subconscious Node: {response_dict.get('error')}")
            return False

    async def set_node_operational_state(self, state: str, daily_summary_for_dreaming: Optional[str] = None) -> bool:
        """
        Sets the SubconsciousNode's operational state (e.g., AWAKE_THINKING, SLEEPING_DREAMING).
        """
        payload = SubconsciousControlState(node_state=state, daily_summary=daily_summary_for_dreaming)

        logger.info(f"Setting Subconscious Node operational state to '{state}'. Summary provided: {bool(daily_summary_for_dreaming)}")
        response_dict = await self._request("POST", "control/state", json_payload=payload.model_dump(exclude_none=True))

        if response_dict.get("success"):
            logger.info(f"Successfully set Subconscious Node state to '{state}'.")
            return True
        else:
            logger.warning(f"Failed to set Subconscious Node state: {response_dict.get('error')}")
            return False

    # Example: If Eidos needs to sync its main mood TO the subconscious node
    # async def sync_mood_to_node(self, ethos_mood_state: MoodState) -> bool:
    #     """ Syncs Pathos's main mood state to the Subconscious Node. """
    #     # This would require SubconsciousNode API to have a /control/mood endpoint
    #     # and for MoodState to be translatable to what that endpoint expects.
    #     # For now, this is a conceptual placeholder.
    #     payload = {"mood_aspects": ethos_mood_state.detailed_hexus_scores ... } # Adapt as needed
    #     logger.info(f"Syncing mood to Subconscious Node: {ethos_mood_state.name}")
    #     response_dict = await self._request("POST", "control/mood", json_payload=payload)
    #     if response_dict.get("success"):
    #         logger.info("Successfully synced mood to Subconscious Node.")
    #         return True
    #     else:
    #         logger.warning(f"Failed to sync mood to Subconscious Node: {response_dict.get('error')}")
    #         return False

# Example usage (for testing, not part of the class typically)
async def _test_client():
    # This requires a running SubconsciousNode API and HTTPClientManager
    # For now, this is a conceptual test structure

    class MockConfig(Config): # Basic mock for testing
        SYSTEM_NODES_CONFIG: Dict[str, Any] = {
            "subconscious_node": {
                "api_base_url": "http://localhost:8000" # Ensure your SubconsciousNode is running here
            }
        }
        def get_nested_value(self, data, keys, default=None): # Simplified
            current = data
            for key in keys:
                if isinstance(current, dict) and key in current: current = current[key]
                else: return default
            return current

    mock_config_instance = MockConfig()

    # HTTPClientManager needs to be properly initialized and shut down if used globally
    # For a quick test, one might create a temporary client, but ideally use the manager
    http_manager = HTTPClientManager.instance()
    await http_manager.startup() # Ensure client is active

    client = SubconsciousNodeClient(config=mock_config_instance, http_client_manager=http_manager)

    print("Testing get_significant_thoughts...")
    thoughts = await client.get_significant_thoughts(limit=2)
    if thoughts:
        for thought in thoughts:
            print(f"- Thought ID: {thought.thought_id}, Content: {thought.content[:50]}...")
    else:
        print("No thoughts retrieved or error occurred.")

    print("\nTesting inject_context_to_node (conversation)...")
    success_conv = await client.inject_context_to_node("conversation", "User said: Hello Pathos!")
    print(f"Inject conversation context success: {success_conv}")

    print("\nTesting inject_context_to_node (action)...")
    success_action = await client.inject_context_to_node("action", "Pathos decided to check the weather.")
    print(f"Inject action context success: {success_action}")

    print("\nTesting inject_context_to_node (dream_fragment)...")
    success_dream = await client.inject_context_to_node("dream_fragment", "A field of floating clocks...")
    print(f"Inject dream_fragment context success: {success_dream}")

    print("\nTesting set_node_operational_state (AWAKE_THINKING)...")
    success_state_awake = await client.set_node_operational_state("AWAKE_THINKING")
    print(f"Set state to AWAKE_THINKING success: {success_state_awake}")

    await asyncio.sleep(2) # Give it a moment to think if it's running

    print("\nTesting set_node_operational_state (SLEEPING_DREAMING)...")
    success_state_sleep = await client.set_node_operational_state("SLEEPING_DREAMING", daily_summary="Pathos had a busy day coding and talking about philosophy.")
    print(f"Set state to SLEEPING_DREAMING success: {success_state_sleep}")

    await http_manager.shutdown() # Clean up client

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # asyncio.run(_test_client()) # Requires a running Subconscious Node API
    logger.info("SubconsciousNodeClient created. Run _test_client() with a live SubconsciousNode for testing.")
