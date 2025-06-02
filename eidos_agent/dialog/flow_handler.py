"""
Handles dialog flow logic for the Eidos agent.

This module may include functions to interpret user intent,
manage conversation state, and determine appropriate agent responses
based on the dialog context.
"""

def is_thought_query(msg: str) -> bool:
    """
    Checks if a user's message is a query about Pathos's thoughts.

    Args:
        msg: The user's message string.

    Returns:
        True if the message contains trigger phrases related to thoughts,
        False otherwise.
    """
    triggers = [
        "what are you thinking", "what's on your mind",
        "what were you just thinking", "tell me your thoughts",
        "what is pathos thinking", "what is pathos's current thought",
        "any thoughts pathos", "pathos thoughts" # Added a few more variations
    ]
    msg_lower = msg.lower()
    for trigger in triggers:
        if trigger in msg_lower:
            return True
    return False

if __name__ == '__main__':
    # Test cases
    test_queries = [
        "Hey, what are you thinking about right now?",
        "Just curious, what's on your mind?",
        "System, what were you just thinking?",
        "Can you tell me your thoughts on this?",
        "I wonder what is Pathos thinking.",
        "What is Pathos's current thought?",
        "Any thoughts Pathos?",
        "Show me Pathos thoughts."
    ]

    non_queries = [
        "Hello there!",
        "What's the weather like?",
        "Tell me a joke.",
        "I think this is interesting.",
        "Thinking about dinner."
    ]

    print("--- Testing Thought Queries (should be True) ---")
    for i, query in enumerate(test_queries):
        result = is_thought_query(query)
        print(f"Query {i+1}: \"{query}\" -> {result}")
        assert result is True, f"Failed for query: {query}"

    print("\n--- Testing Non-Thought Queries (should be False) ---")
    for i, query in enumerate(non_queries):
        result = is_thought_query(query)
        print(f"Non-query {i+1}: \"{query}\" -> {result}")
        assert result is False, f"Failed for non-query: {query}"

    print("\nAll tests passed!")
