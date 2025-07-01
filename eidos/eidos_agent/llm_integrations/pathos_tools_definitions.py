"""
Tool Definitions for Pathos Interface.

This module centralizes the definitions of tools available to the Pathos LLM
and the broader Eidos system when interacting with or via Pathos.
"""

# --- Individual Tool Definitions ---

# Bookshelf Handler Instance
# This assumes that the configuration for BookshelfHandler (via Config.get_bookshelf_config())
# is available when this module is loaded. If not, this instantiation might fail or be None.
# A more robust system might use a service locator or dependency injection.
from eidos_agent.features.bookshelf_feature.handler import BookshelfHandler
from eidos_agent.core.config import Config # To check if bookshelf is configured

bookshelf_handler_instance: BookshelfHandler | None = None
if Config.get_bookshelf_config(): # Only initialize if configured
    bookshelf_handler_instance = BookshelfHandler()
else:
    print("Warning: BookshelfHandler not initialized in pathos_tools_definitions as Bookshelf is not configured.")

# Tool definitions will point to methods on bookshelf_handler_instance.
# The actual execution will require this instance to be available to the tool dispatcher.

GET_CURRENT_TIME_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "get_current_time", "description": ("Gets the current date and time. If a location is specified, it attempts to provide the local time for that location. If no location is given, or if the specified location's time cannot be determined, it defaults to Coordinated Universal Time (UTC)."), "parameters": { "type": "object", "properties": { "location": { "type": "string", "description": ( "Optional. The city and state/country (e.g., 'San Francisco, CA', 'London, UK') or a standard IANA timezone name (e.g., 'America/New_York', 'Europe/London') for which to get the local time." ) } }, "required": [] } } } ]
WEB_SEARCH_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "web_search", "description": "MUST use this function to find current information like news, events, weather, facts. REQUIRED for queries about 'latest', 'today', 'current', 'who won', 'what is X'. Do NOT answer from memory if current information is needed.", "parameters": { "type": "object", "properties": { "query": { "type": "string", "description": "The specific search query phrase to use for the web search. Formulate a good query based on the user's request." } }, "required": ["query"] } } } ]
MATH_CALCULATOR_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "math_calculator", "description": "Calculates the result of a mathematical expression. Use for arithmetic, algebra, calculus, etc. Input should be a standard mathematical expression string.", "parameters": { "type": "object", "properties": { "expression": { "type": "string", "description": "The mathematical expression to evaluate (e.g., '2 * (5 + 3)', 'derivative of x^2')." } }, "required": ["expression"] } } } ]
GET_WEATHER_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "get_weather", "description": "Gets the current weather conditions for a specified location.", "parameters": { "type": "object", "properties": { "location": { "type": "string", "description": "The city and state/country (e.g., 'San Francisco, CA', 'London, UK') for which to get the weather." } }, "required": ["location"] } } } ]
STORE_USER_FACT_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "store_user_fact", "description": ("Use this tool to remember a specific, distinct piece of factual information explicitly stated by the user about themselves (e.g., their name, a key preference, a personal detail they want you to remember). Only use for clear, direct statements of fact from the user."), "parameters": { "type": "object", "properties": { "attribute_name": { "type": "string", "description": "A concise key or category for the fact (e.g., 'name', 'favorite_color', 'location', 'pet_name', 'occupation'). Use a consistent, simple key." }, "attribute_value": { "type": "string", "description": "The actual value of the fact stated by the user (e.g., 'Isaac', 'blue', 'California', 'Fluffy', 'engineer')." }, "user_statement_context": { "type": "string", "description": "A brief summary or the exact user sentence where this fact was stated, for context." } }, "required": ["attribute_name", "attribute_value", "user_statement_context"] } } } ]
STORE_WORLD_FACT_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "store_world_fact", "description": ("Use this tool to remember a specific, verifiable piece of factual information about the world, an entity, a concept, or a topic. This is for general knowledge that you have learned and want to retain (e.g., from a web search, a document, or a user explicitly teaching you a fact). Do not use for user's personal preferences or details about the user themselves (use 'store_user_fact' for that)."), "parameters": { "type": "object", "properties": { "fact_statement": { "type": "string", "description": "The factual statement to be stored (e.g., 'The capital of France is Paris.', 'Water boils at 100 degrees Celsius at sea level.')." }, "source_description": { "type": "string", "description": "A brief description of where this fact was learned or derived from (e.g., 'Web search result snippet', 'User statement', 'Document: Introduction to Physics, page 10')." }, "topic_tags": { "type": "array", "items": {"type": "string"}, "description": "Optional. A list of 1-3 relevant topic tags or keywords for this fact (e.g., ['geography', 'capitals', 'france'], ['physics', 'chemistry', 'water_properties'])." }, "confidence_level": { "type": "number", "description": "Optional. A numerical confidence level (0.0 to 1.0) in the accuracy of this fact, if assessable. Default to 0.8 if learned from a seemingly reliable source.", "default": 0.8 } }, "required": ["fact_statement", "source_description"] } } } ]
PERFORM_DEEP_RESEARCH_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "perform_deep_research", "description": ("Use this tool for complex questions that require in-depth analysis, synthesis of information from multiple web search results, or a comprehensive understanding of a multifaceted topic. Prefer this over a single 'web_search' if the user is asking for a detailed explanation, a report, an exploration of different viewpoints, or a summary of a broad subject. This tool will perform multiple searches and synthesize the findings."), "parameters": { "type": "object", "properties": { "research_query": { "type": "string", "description": "The central question or topic for the in-depth research. Be specific." }, "number_of_searches": { "type": "integer", "description": "Optional. Suggest 2-3 initial web searches to gather diverse information. Max 4.", "default": 3 } }, "required": ["research_query"] } } } ]
GET_NEWS_HEADLINES_TOOL_DEFINITION = [{ "type": "function", "function": { "name": "get_news_headlines", "description": "Gets the top news headlines from configured news sources. Use this specifically when the user asks for current news headlines.", "parameters": {"type": "object", "properties": {}, "required": []} } }]
ADD_PATHOS_EVENT_TOOL_DEFINITION = [{ "type": "function", "function": { "name": "add_pathos_event", "description": "Schedules a new multi-day or single-day event for Pathos (the AI assistant, Patrick Shaw). Use this when the user asks Pathos to plan something for itself, like a vacation, work trip, conference, or personal day. You must gather all required parameters: title, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), and event_type.", "parameters": { "type": "object", "properties": { "title": {"type": "string", "description": "A descriptive title for the event (e.g., 'Vacation in Kyoto', 'AI Ethics Conference')."}, "start_date": {"type": "string", "description": "The start date of the event in YYYY-MM-DD format."}, "end_date": {"type": "string", "description": "The end date of the event in YYYY-MM-DD format. For single-day events, this is the same as the start_date."}, "event_type": {"type": "string", "description": "The type of event. Must be one of: 'vacation', 'work_trip', 'conference', 'personal_day', 'appointment', 'recurring_task', 'holiday', 'social_engagement', 'creative_project', 'learning_goal', 'health_wellness', 'other_event'.", "enum": ["vacation", "work_trip", "conference", "personal_day", "appointment", "recurring_task", "holiday", "social_engagement", "creative_project", "learning_goal", "health_wellness", "other_event"]}, "description": {"type": "string", "description": "Optional. A brief description of the event."}, "location": {"type": "string", "description": "Optional. The location of the event (e.g., 'Kyoto, Japan', 'Online')."}, "activity_theme": {"type": "string", "description": "Optional. A general theme for activities during the event (e.g., 'Relaxation and Sightseeing', 'Deep Learning Workshops')."}, "planned_sites_or_tasks": {"type": "array", "items": {"type": "string"}, "description": "Optional. A list of specific sites to visit or tasks to accomplish during the event."} }, "required": ["title", "start_date", "end_date", "event_type"] } } }]
INITIATE_SIMULATED_INTERACTION_TOOL_DEFINITION = [{ "type": "function", "function": { "name": "initiate_simulated_interaction", "description": "Starts a simulated conversation with a new Non-Player Character (NPC). Use this to begin an interaction based on a scenario Pathos wants to explore.", "parameters": { "type": "object", "properties": { "npc_name": {"type": "string", "description": "Optional. The name of the NPC. If not provided, a name might be implicitly determined or not used."}, "npc_role": {"type": "string", "description": "The role or relationship of the NPC to Pathos (e.g., 'store clerk', 'client', 'old friend')."}, "npc_description": {"type": "string", "description": "A short description of the NPC's personality, demeanor, or key characteristics (e.g., 'grumpy, impatient', 'friendly, helpful', 'curious about AI')."}, "initial_context": {"type": "string", "description": "The initial situation, setting, or topic for the conversation (e.g., 'Pathos is at a cafe trying to order a coffee', 'Pathos is meeting a new client to discuss a project', 'Pathos wants to ask for directions to a specific book section')."}, "pathos_opening_statement": {"type": "string", "description": "Pathos's first line or question to the NPC to start the conversation."} }, "required": ["npc_role", "npc_description", "initial_context", "pathos_opening_statement"] } } }]
SEND_MESSAGE_TO_SIMULATED_NPC_TOOL_DEFINITION = [{ "type": "function", "function": { "name": "send_message_to_simulated_npc", "description": "Sends Pathos's message to the currently active NPC in an ongoing simulated conversation and gets the NPC's reply.", "parameters": { "type": "object", "properties": { "message_to_npc": {"type": "string", "description": "Pathos's message or response to the NPC."} }, "required": ["message_to_npc"] } } }]
END_SIMULATED_INTERACTION_TOOL_DEFINITION = [{ "type": "function", "function": { "name": "end_simulated_interaction", "description": "Ends the current simulated conversation with the NPC.", "parameters": {"type": "object", "properties": {}, "required": []} } }]


# --- Bookshelf Tool Definitions ---
BOOKSHELF_ADD_DOCUMENT_TOOL_DEFINITION = [{
    "type": "function",
    "function": {
        "name": "bookshelf_add_document",
        "description": "Adds a new document to your personal bookshelf for later retrieval and reference. Use this to store text content like articles, notes, or user-provided documents you need to remember.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_name": {"type": "string", "description": "A unique name or title for the document (e.g., 'My Research Notes on AI', 'Recipe for Sourdough Bread')."},
                "document_content": {"type": "string", "description": "The full text content of the document to be added."},
                "document_source": {"type": "string", "description": "Optional. The origin or source of the document (e.g., 'User upload', 'Web article scrape', 'Personal note'). Defaults to 'unknown' if not provided."},
                "topics": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional. A list of keywords or topics relevant to the document (e.g., ['artificial intelligence', 'research', 'ethics'])."
                }
            },
            "required": ["document_name", "document_content"]
        }
    }
}]

BOOKSHELF_QUERY_TOOL_DEFINITION = [{
    "type": "function",
    "function": {
        "name": "bookshelf_query",
        "description": "Searches your personal bookshelf for documents relevant to a query. Returns context from matching documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "The question or search term to query your bookshelf with."},
                "document_name": {"type": "string", "description": "Optional. If provided, the search will be limited to only the document with this specific name."},
                "topics_filter": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional. A list of topics to filter the search by. Documents matching any of these topics will be prioritized or included."
                },
                "top_k": {"type": "integer", "description": "Optional. The number of most relevant text chunks to retrieve. Defaults to 3 or 5."}
            },
            "required": ["query_text"]
        }
    }
}]

BOOKSHELF_LIST_DOCUMENTS_TOOL_DEFINITION = [{
    "type": "function",
    "function": {
        "name": "bookshelf_list_documents",
        "description": "Lists the names of all documents currently stored on your personal bookshelf.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }
}]

BOOKSHELF_GET_DOCUMENT_RAW_TEXT_TOOL_DEFINITION = [{
    "type": "function",
    "function": {
        "name": "bookshelf_get_document_raw_text",
        "description": "Retrieves the full, raw text content of a specific document from your bookshelf. Use this if you need to read or analyze an entire document.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_name": {"type": "string", "description": "The unique name of the document to retrieve."}
            },
            "required": ["document_name"]
        }
    }
}]

BOOKSHELF_REMOVE_DOCUMENT_TOOL_DEFINITION = [{
    "type": "function",
    "function": {
        "name": "bookshelf_remove_document",
        "description": "Removes a document and all its content from your personal bookshelf. Use this to 'forget' or delete a document.",
        "parameters": {
            "type": "object",
            "properties": {
                "document_name": {"type": "string", "description": "The unique name of the document to remove."}
            },
            "required": ["document_name"]
        }
    }
}]


# --- Composite Tool Lists ---

# Tools Pathos's main LLM will be directly aware of and can choose to use for HIS OWN purposes
AVAILABLE_TOOLS_FOR_PATHOS_LLM = [
    *STORE_USER_FACT_TOOL_DEFINITION,       # Remembering facts about his friend (the user)
    *STORE_WORLD_FACT_TOOL_DEFINITION,      # Remembering general knowledge he learns
    *PERFORM_DEEP_RESEARCH_TOOL_DEFINITION, # For his own deep dives into topics of interest
    *ADD_PATHOS_EVENT_TOOL_DEFINITION,      # For scheduling his own personal events/plans
    *INITIATE_SIMULATED_INTERACTION_TOOL_DEFINITION, # For him to start a simulated chat (e.g. practice)
    *SEND_MESSAGE_TO_SIMULATED_NPC_TOOL_DEFINITION,  # For him to continue a simulated chat
    *END_SIMULATED_INTERACTION_TOOL_DEFINITION,      # For him to end a simulated chat
    *MATH_CALCULATOR_TOOL_DEFINITION        # He might use this for a personal calculation
]

# All tools, including those PathosInterface might call directly or system might use
# These might be used by LogosCore when it's acting as the "Computer Interaction Module"
# on behalf of Pathos, or for system functions.
ALL_AVAILABLE_SYSTEM_TOOLS = [
    *GET_CURRENT_TIME_TOOL_DEFINITION,
    *WEB_SEARCH_TOOL_DEFINITION,
    *MATH_CALCULATOR_TOOL_DEFINITION,
    *GET_WEATHER_TOOL_DEFINITION,
    *STORE_USER_FACT_TOOL_DEFINITION,       # Also available to system for direct user fact storage via Logos
    *PERFORM_DEEP_RESEARCH_TOOL_DEFINITION, # Also available to system
    *STORE_WORLD_FACT_TOOL_DEFINITION,      # Also available to system
    *GET_NEWS_HEADLINES_TOOL_DEFINITION,
    *ADD_PATHOS_EVENT_TOOL_DEFINITION,      # System might add events too
    *INITIATE_SIMULATED_INTERACTION_TOOL_DEFINITION, # System might initiate for testing/scenarios
    *SEND_MESSAGE_TO_SIMULATED_NPC_TOOL_DEFINITION,
    *END_SIMULATED_INTERACTION_TOOL_DEFINITION,
    # Bookshelf tools for the system to use (e.g., when directed by user commands processed by Logos)
    *BOOKSHELF_ADD_DOCUMENT_TOOL_DEFINITION,
    *BOOKSHELF_QUERY_TOOL_DEFINITION,
    *BOOKSHELF_LIST_DOCUMENTS_TOOL_DEFINITION,
    *BOOKSHELF_GET_DOCUMENT_RAW_TEXT_TOOL_DEFINITION,
    *BOOKSHELF_REMOVE_DOCUMENT_TOOL_DEFINITION,
]
