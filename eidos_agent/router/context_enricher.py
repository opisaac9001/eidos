"""
Provides functions to enrich prompts with additional context,
such as thoughts from the Pathos Subconscious Node.
"""
import logging

# Attempt to import from other Eidos modules
try:
    from eidos_agent.dialog.flow_handler import is_thought_query
    from eidos_agent.modules.subconscious.client import get_current_thoughts
except ImportError:
    # Fallback for isolated testing or if PYTHONPATH is not set up correctly
    logging.warning("context_enricher: Could not import Eidos modules. Using placeholders for testing.")
    # Define placeholder functions if actual imports fail
    def is_thought_query(msg: str) -> bool:
        print(f"Placeholder is_thought_query called with: {msg}")
        return "what are you thinking" in msg.lower()

    def get_current_thoughts():
        print("Placeholder get_current_thoughts called.")
        # Simulate different responses for testing
        if hasattr(get_current_thoughts, 'call_count'):
            get_current_thoughts.call_count += 1
        else:
            get_current_thoughts.call_count = 1

        if get_current_thoughts.call_count % 3 == 1:
            return {"recent_thoughts": ["The sky is blue.", "Thinking about philosophy."], "mood": {"name": "Contemplative"}, "summary": "Contemplating."}
        elif get_current_thoughts.call_count % 3 == 2:
            return {"recent_thoughts": [], "mood": {"name": "Quiet"}, "summary": "Pathos is quiet."}
        else:
            return None


logger = logging.getLogger(__name__)
if not logger.handlers: # Ensure logger is configured
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def enrich_prompt_with_subconscious(base_prompt: str, user_msg: str) -> str:
    """
    Enriches a base prompt with subconscious thoughts if the user's message
    is a query about thoughts.

    Args:
        base_prompt: The original prompt string for the main LLM.
        user_msg: The user's current message string.

    Returns:
        The potentially enriched prompt string.
    """
    if is_thought_query(user_msg):
        logger.info(f"Thought query detected for user message: '{user_msg}'")
        thoughts_data = get_current_thoughts()

        if thoughts_data and thoughts_data.get("recent_thoughts"):
            # Using "Pathos' recent thoughts include:" as per one of the plan options
            formatted_thoughts = "\n".join([f"- {t}" for t in thoughts_data["recent_thoughts"]])
            enrichment = f"\n\nPathos' recent thoughts include:\n{formatted_thoughts}"
            logger.info(f"Enriching prompt with thoughts.") # Removed potentially problematic replace
            return base_prompt + enrichment
        elif thoughts_data: # Thoughts data exists but no recent_thoughts or it's empty
            node_summary = thoughts_data.get("summary", "Pathos is quiet right now.")
            enrichment = f"\n\nPathos reports: \"{node_summary}\"" # Provide summary if no specific thoughts
            logger.info(f"Enriching prompt with Pathos summary: {node_summary}")
            return base_prompt + enrichment
        else: # Failed to get thoughts_data (e.g., API error)
            enrichment = "\n\nPathos is quiet right now and no thoughts could be retrieved."
            logger.warning("Failed to retrieve thoughts data or it was None. Adding 'quiet' message.")
            return base_prompt + enrichment
    else:
        logger.debug(f"No thought query detected for user message: '{user_msg}'")
        return base_prompt

if __name__ == '__main__':
    print("--- Testing Prompt Enrichment ---")

    # Reset call count for placeholder get_current_thoughts if it's the placeholder
    if hasattr(get_current_thoughts, 'call_count'):
        get_current_thoughts.call_count = 0


    base_system_prompt = "You are Eidos, a helpful AI assistant."

    # Case 1: User asks about thoughts, thoughts are available
    user_message_1 = "What are you thinking about?"
    enriched_prompt_1 = enrich_prompt_with_subconscious(base_system_prompt, user_message_1)
    print(f"\nUser: \"{user_message_1}\"")
    print(f"Prompt:\n{enriched_prompt_1}")
    assert "Pathos' recent thoughts include:" in enriched_prompt_1
    assert "- The sky is blue." in enriched_prompt_1

    # Case 2: User asks about thoughts, thoughts_data is available but recent_thoughts is empty
    user_message_2 = "What's on your mind, Pathos?" # Assuming is_thought_query catches this
    # Manually adjust placeholder for this specific test if needed, or rely on its cycling
    if hasattr(get_current_thoughts, 'call_count'): # This will be the second call to the placeholder
        pass # Placeholder will return empty recent_thoughts on 2nd call
    enriched_prompt_2 = enrich_prompt_with_subconscious(base_system_prompt, user_message_2)
    print(f"\nUser: \"{user_message_2}\"")
    print(f"Prompt:\n{enriched_prompt_2}")
    assert "Pathos reports: \"Pathos is quiet.\"" in enriched_prompt_2


    # Case 3: User asks about thoughts, get_current_thoughts returns None
    user_message_3 = "Tell me your thoughts."
    # Manually adjust placeholder for this specific test if needed
    if hasattr(get_current_thoughts, 'call_count'): # This will be the third call
        pass # Placeholder will return None on 3rd call
    enriched_prompt_3 = enrich_prompt_with_subconscious(base_system_prompt, user_message_3)
    print(f"\nUser: \"{user_message_3}\"")
    print(f"Prompt:\n{enriched_prompt_3}")
    assert "Pathos is quiet right now and no thoughts could be retrieved." in enriched_prompt_3

    # Case 4: User does not ask about thoughts
    user_message_4 = "What's the weather like?"
    enriched_prompt_4 = enrich_prompt_with_subconscious(base_system_prompt, user_message_4)
    print(f"\nUser: \"{user_message_4}\"")
    print(f"Prompt:\n{enriched_prompt_4}")
    assert enriched_prompt_4 == base_system_prompt

    # Case 5: is_thought_query returns True, but get_current_thoughts returns valid data with no 'recent_thoughts' key
    # (This tests the specific condition: `thoughts_data and thoughts_data.get("recent_thoughts")`)
    if hasattr(get_current_thoughts, 'call_count'):
        get_current_thoughts.call_count = 0 # Reset to ensure predictable placeholder behavior
    
    # Mock get_current_thoughts to return a specific dict for this test
    original_get_thoughts = get_current_thoughts 
    def mock_get_thoughts_no_recent():
        print("Mocked get_current_thoughts for 'no recent_thoughts key' test called.")
        return {"mood": {"name": "Curious"}, "summary": "Thinking about something else."}
    
    # If using the placeholder, we need to be able to swap it
    if hasattr(enrich_prompt_with_subconscious, '__globals__') and 'get_current_thoughts' in enrich_prompt_with_subconscious.__globals__:
        enrich_prompt_with_subconscious.__globals__['get_current_thoughts'] = mock_get_thoughts_no_recent
    else: # If imports worked, we need to patch differently or accept placeholder behavior
        print("Warning: Could not directly patch get_current_thoughts for specific test case 5, relying on placeholder cycle if active.")
        # If real imports worked, this test case might not be perfectly isolated without a true mock library
        # For now, we'll let the placeholder cycle, assuming the 1st call will have recent_thoughts
        # and this test might then reflect the "Pathos reports: " case if it's the 2nd/3rd call.
        # This highlights limitations of placeholder testing vs. proper mocking.
        # To make it more robust with placeholders, we'd need more control over the placeholder's return sequence.

    user_message_5 = "What are you thinking now?"
    enriched_prompt_5 = enrich_prompt_with_subconscious(base_system_prompt, user_message_5)
    print(f"\nUser: \"{user_message_5}\" (testing specific 'no recent_thoughts' key)")
    print(f"Prompt:\n{enriched_prompt_5}")
    
    if 'get_current_thoughts' in enrich_prompt_with_subconscious.__globals__ and \
       enrich_prompt_with_subconscious.__globals__['get_current_thoughts'] == mock_get_thoughts_no_recent:
        assert "Pathos reports: \"Thinking about something else.\"" in enriched_prompt_5
        enrich_prompt_with_subconscious.__globals__['get_current_thoughts'] = original_get_thoughts # Restore
    else: # Placeholder behavior check
        assert "Pathos' recent thoughts include:" in enriched_prompt_5 or \
               "Pathos reports:" in enriched_prompt_5 or \
               "Pathos is quiet right now" in enriched_prompt_5


    print("\nPrompt enrichment tests finished.")
