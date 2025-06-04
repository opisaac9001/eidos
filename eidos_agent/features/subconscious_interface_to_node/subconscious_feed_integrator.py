import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

# Placeholder for actual imports - these would come from other Eidos modules
# from eidos_agent.dialog.flow_handler import is_thought_query
# from eidos_agent.features.subconscious_interface_to_node.subconscious.client import get_current_thoughts

# --- Start of Dummy Implementations (replace with actual imports) ---
def is_thought_query(msg: str) -> bool:
    """
    Placeholder: Determines if the user's message is a query about thoughts.
    """
    logger = logging.getLogger(__name__)
    logger.debug(f"Placeholder is_thought_query called with: {msg}")
    if msg is None: return False
    return "what are you thinking" in msg.lower() or \
           "what's on your mind" in msg.lower() or \
           "tell me your thoughts" in msg.lower()

def get_current_thoughts() -> Optional[Dict[str, Any]]:
    """
    Placeholder: Simulates fetching current thoughts data from the Subconscious Node.
    """
    logger = logging.getLogger(__name__)
    logger.debug("Placeholder get_current_thoughts called.")
    # Simulate different responses for testing
    # This is a simplified version of the placeholder in context_enricher.py
    if not hasattr(get_current_thoughts, 'call_count'):
        get_current_thoughts.call_count = 0 # type: ignore

    get_current_thoughts.call_count += 1 # type: ignore

    if get_current_thoughts.call_count % 4 == 1: # type: ignore
        return {
            "recent_thoughts": ["The sky is blue today.", "Contemplating the nature of tasks.", "Feeling a bit digital."],
            "mood": {"name": "Contemplative", "intensity": 0.7},
            "summary": "Pathos is in a contemplative mood, thinking about various topics."
        }
    elif get_current_thoughts.call_count % 4 == 2: # type: ignore
        return {
            "recent_thoughts": [], # No specific thoughts, but summary is there
            "mood": {"name": "Quiet", "intensity": 0.4},
            "summary": "Pathos is quiet at the moment."
        }
    elif get_current_thoughts.call_count % 4 == 3: # type: ignore
        # Simulate a case where mood or summary might be missing, but thoughts are there
         return {
            "recent_thoughts": ["Just processed a complex query.", "The user seems curious."],
            "mood": None, # Mood missing
            "summary": "Actively processing."
        }
    else:
        return None # Represents an error or no data from the subconscious node
# --- End of Dummy Implementations ---


logger = logging.getLogger(__name__)

class SubconsciousFeedIntegrator:
    """
    Integrates the feed from the Pathos Subconscious Node, providing cached access
    and formatted outputs for different Eidos components.
    """
    def __init__(self, cache_duration_seconds: int = 60):
        """
        Initializes the SubconsciousFeedIntegrator.

        Args:
            cache_duration_seconds: Duration in seconds to cache the subconscious feed.
                                   Defaults to 60 seconds.
        """
        self.cache_duration = timedelta(seconds=cache_duration_seconds)
        self._cached_feed: Optional[Dict[str, Any]] = None
        self._last_fetch_time: Optional[datetime] = None
        logger.info(f"SubconsciousFeedIntegrator initialized with cache duration: {self.cache_duration.total_seconds()}s")

    def get_current_subconscious_feed(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Retrieves the current subconscious feed, using a cache to limit frequent calls.

        Args:
            force_refresh: If True, bypasses the cache and fetches fresh data.

        Returns:
            A dictionary containing the subconscious feed data, or None if an error occurs.
        """
        now = datetime.now()
        if not force_refresh and self._cached_feed is not None and \
           self._last_fetch_time is not None and \
           (now - self._last_fetch_time) < self.cache_duration:
            logger.debug("Returning cached subconscious feed.")
            return self._cached_feed

        logger.debug(f"Fetching fresh subconscious feed. Force refresh: {force_refresh}")
        try:
            # This would be the actual call to the subconscious node client
            fresh_feed = get_current_thoughts()
            self._cached_feed = fresh_feed
            self._last_fetch_time = now
            if fresh_feed:
                logger.info("Successfully fetched and cached fresh subconscious feed.")
            else:
                logger.warning("Fetched subconscious feed was None or empty.")
            return fresh_feed
        except Exception as e:
            logger.error(f"Error fetching subconscious feed: {e}", exc_info=True)
            # In case of error, clear cache to avoid serving stale error indicators potentially
            self._cached_feed = None
            self._last_fetch_time = None
            return None

    def get_formatted_thoughts_for_prompt(self, user_input_text: str) -> Optional[str]:
        """
        Determines if the user is asking about Pathos's thoughts and, if so,
        formats the current subconscious feed for injection into an LLM prompt.

        Args:
            user_input_text: The user's current input message.

        Returns:
            A string containing the formatted thoughts for prompt enrichment,
            or None if thoughts are not relevant or not available.
        """
        if not is_thought_query(user_input_text):
            logger.debug(f"No thought query detected for user message: '{user_input_text}'")
            return None

        logger.info(f"Thought query detected for user message: '{user_input_text}'")
        thoughts_data = self.get_current_subconscious_feed()

        if not thoughts_data:
            logger.warning("Failed to retrieve thoughts data or it was None. Adding 'quiet' message for prompt.")
            return "\n\nPathos is quiet right now and no thoughts could be retrieved."

        recent_thoughts = thoughts_data.get("recent_thoughts")
        node_summary = thoughts_data.get("summary", "Pathos is quiet right now.") # Default if summary key missing

        if recent_thoughts and isinstance(recent_thoughts, list) and len(recent_thoughts) > 0:
            formatted_thoughts = "\n".join([f"- {t}" for t in recent_thoughts])
            enrichment = f"\n\nPathos' recent thoughts include:\n{formatted_thoughts}"
            logger.info("Enriching prompt with detailed thoughts.")
            return enrichment
        else: # No recent_thoughts or it's empty, but thoughts_data exists
            enrichment = f"\n\nPathos reports: \"{node_summary}\""
            logger.info(f"Enriching prompt with Pathos summary: {node_summary}")
            return enrichment

    def get_subconscious_snapshot_for_ethos(self) -> Dict[str, Any]:
        """
        Prepares a snapshot of the subconscious state for EthosCore.
        This might include mood, a summary, and a brief preview of recent thoughts.

        Returns:
            A dictionary containing the snapshot.
        """
        feed = self.get_current_subconscious_feed()
        if not feed:
            return {
                "status": "unavailable",
                "mood": None,
                "summary": "Subconscious feed currently unavailable.",
                "thoughts_preview": []
            }

        mood = feed.get("mood")
        summary = feed.get("summary", "No summary available.")
        recent_thoughts: List[str] = feed.get("recent_thoughts", [])

        # Create a concise preview of thoughts
        thoughts_preview = recent_thoughts[:2] # e.g., first 2 thoughts
        if len(recent_thoughts) > 2:
            thoughts_preview.append(f"...and {len(recent_thoughts) - 2} more.")

        snapshot = {
            "status": "available",
            "mood": mood,
            "summary": summary,
            "thoughts_preview": thoughts_preview,
            "full_feed_timestamp": self._last_fetch_time.isoformat() if self._last_fetch_time else None
        }
        logger.info(f"Generated subconscious snapshot for Ethos: Mood='{mood.get('name') if mood else 'N/A'}', Summary='{summary[:50]}...'")
        return snapshot


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing SubconsciousFeedIntegrator ---")

    integrator = SubconsciousFeedIntegrator(cache_duration_seconds=5) # Short cache for testing

    # Test 1: Initial fetch and formatting for prompt (thought query)
    user_msg1 = "What are you thinking about, Pathos?"
    formatted_prompt_thoughts1 = integrator.get_formatted_thoughts_for_prompt(user_msg1)
    print(f"\nTest 1: User asks about thoughts ('{user_msg1}')")
    print(f"Formatted for prompt (1st call):\n{formatted_prompt_thoughts1}")
    assert formatted_prompt_thoughts1 is not None
    assert "Pathos' recent thoughts include:" in formatted_prompt_thoughts1 or "Pathos reports:" in formatted_prompt_thoughts1

    # Test 2: Cached fetch (should be quick and use cache)
    formatted_prompt_thoughts2 = integrator.get_formatted_thoughts_for_prompt(user_msg1)
    print(f"\nTest 2: User asks about thoughts again (cached)")
    print(f"Formatted for prompt (2nd call, cached):\n{formatted_prompt_thoughts2}")
    assert formatted_prompt_thoughts2 == formatted_prompt_thoughts1 # Should be identical due to cache

    # Test 3: Snapshot for Ethos
    snapshot1 = integrator.get_subconscious_snapshot_for_ethos()
    print(f"\nTest 3: Snapshot for Ethos (1st call, uses same cache as above)")
    print(f"Snapshot 1: {snapshot1}")
    assert snapshot1["status"] == "available"
    assert "mood" in snapshot1
    assert "summary" in snapshot1
    assert "thoughts_preview" in snapshot1

    # Test 4: Force refresh
    print("\nTest 4: Force refresh subconscious feed...")
    # Note: Placeholder get_current_thoughts cycles its response.
    # Call 1 to get_formatted_thoughts_for_prompt (uncached) - feed_call_count = 1
    # Call 2 to get_formatted_thoughts_for_prompt (cached)
    # Call 3 to get_subconscious_snapshot_for_ethos (cached)
    # So, next call to get_current_thoughts() via force_refresh will be call_count = 2 for the dummy function
    forced_feed = integrator.get_current_subconscious_feed(force_refresh=True)
    print(f"Forced feed data: {forced_feed}")
    assert forced_feed is not None # Should get new data based on dummy's cycle

    # Verify that the next Ethos snapshot reflects this forced update
    snapshot2 = integrator.get_subconscious_snapshot_for_ethos()
    print(f"Snapshot 2 (after force refresh): {snapshot2}")
    if forced_feed.get("recent_thoughts"): # if the new feed had thoughts
         assert snapshot2["summary"] == forced_feed.get("summary")
    else: # if the new feed had no thoughts (e.g. "Pathos is quiet")
         assert snapshot2["summary"] == forced_feed.get("summary")


    # Test 5: Non-thought query
    user_msg2 = "What's the weather like?"
    formatted_prompt_thoughts3 = integrator.get_formatted_thoughts_for_prompt(user_msg2)
    print(f"\nTest 5: User asks non-thought query ('{user_msg2}')")
    print(f"Formatted for prompt (non-thought query):\n{formatted_prompt_thoughts3}")
    assert formatted_prompt_thoughts3 is None

    # Test 6: Cache expiration
    print("\nTest 6: Waiting for cache to expire (5 seconds)...")
    import time
    time.sleep(5.1)
    # This will be call_count = 3 for the dummy get_current_thoughts
    formatted_prompt_thoughts4 = integrator.get_formatted_thoughts_for_prompt(user_msg1)
    print(f"Formatted for prompt (after cache expiry):\n{formatted_prompt_thoughts4}")
    assert formatted_prompt_thoughts4 is not None
    # Check it's different from the last cached value if dummy is cycling
    # The dummy get_current_thoughts() call_count is now 3.
    # forced_feed was call_count = 2.
    # So this should be different from snapshot2 if the dummy provides different data for call 2 and 3.
    # This depends on dummy's internal logic.
    # snapshot2 summary was from forced_feed (call 2).
    # formatted_prompt_thoughts4 summary is from call 3.
    current_feed_for_test6 = integrator.get_current_subconscious_feed() # get current state for assertion
    if current_feed_for_test6 and current_feed_for_test6.get("recent_thoughts"):
        assert "Pathos' recent thoughts include:" in formatted_prompt_thoughts4
    elif current_feed_for_test6:
        assert f"Pathos reports: \"{current_feed_for_test6.get('summary')}\"" in formatted_prompt_thoughts4
    else: # if get_current_thoughts() returned None for call_count = 3
        assert "Pathos is quiet right now and no thoughts could be retrieved." in formatted_prompt_thoughts4

    # Test 7: Subconscious node returns None (simulating error or no data)
    # Manually ensure next call to dummy get_current_thoughts returns None (call_count = 4)
    if hasattr(get_current_thoughts, 'call_count'):
        get_current_thoughts.call_count = 3 # So next call is 4
    print(f"\nTest 7: Simulating subconscious node returning None...")
    integrator.get_current_subconscious_feed(force_refresh=True) # This will be call_count = 4, should return None

    snapshot_error = integrator.get_subconscious_snapshot_for_ethos()
    print(f"Snapshot (after node error): {snapshot_error}")
    assert snapshot_error["status"] == "unavailable"
    assert "Subconscious feed currently unavailable." in snapshot_error["summary"]

    prompt_error_case = integrator.get_formatted_thoughts_for_prompt(user_msg1)
    print(f"Formatted for prompt (after node error):\n{prompt_error_case}")
    assert "Pathos is quiet right now and no thoughts could be retrieved." in prompt_error_case


    logger.info("--- SubconsciousFeedIntegrator tests finished ---")
```
