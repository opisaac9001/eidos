import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Literal, Union, AsyncGenerator, Tuple
import re
import json
from pathlib import Path
import uuid
import httpx
from eidos_agent.utils.prompt_loader import load_system_prompt

try:
    import tiktoken # FIX: Added import tiktoken
except ImportError:
    tiktoken = None
    logging.getLogger(__name__).warning("Tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken") # Use standard logging for early init

from eidos_agent.core.config import Config, LLMConfig
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger
from eidos_agent.core.api_models import ChatMessage # Assuming this is defined elsewhere if needed
from eidos_agent.modules.chronos_engine import PATHOS_USER_ID
from eidos_agent.modules import simulation_module

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.services.external_tts_service import ExternalTTSService

logger = get_logger(__name__)

# --- Tool Definitions (ensure these are up-to-date with your decisions) ---
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
ALL_AVAILABLE_SYSTEM_TOOLS = [
    *GET_CURRENT_TIME_TOOL_DEFINITION,
    *WEB_SEARCH_TOOL_DEFINITION, # <<<< Stays here for Computer Interaction Module
    *MATH_CALCULATOR_TOOL_DEFINITION,
    *GET_WEATHER_TOOL_DEFINITION, # <<<< Stays here for Computer Interaction Module
    *STORE_USER_FACT_TOOL_DEFINITION,
    *PERFORM_DEEP_RESEARCH_TOOL_DEFINITION,
    *STORE_WORLD_FACT_TOOL_DEFINITION,
    *GET_NEWS_HEADLINES_TOOL_DEFINITION, # <<<< Stays here for Computer Interaction Module
    *ADD_PATHOS_EVENT_TOOL_DEFINITION,
    *INITIATE_SIMULATED_INTERACTION_TOOL_DEFINITION,
    *SEND_MESSAGE_TO_SIMULATED_NPC_TOOL_DEFINITION,
    *END_SIMULATED_INTERACTION_TOOL_DEFINITION
]


def estimate_tokens_for_messages(messages: List[Dict[str, Any]], model_name_for_tiktoken: str = "cl100k_base") -> int:
    if tiktoken is None: return -1
    try: encoding = tiktoken.get_encoding(model_name_for_tiktoken)
    except Exception:
        try: encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e_enc: logger.error(f"Tiktoken: Failed to get cl100k_base encoding: {e_enc}"); return -1
    num_tokens = 0; tokens_per_message_overhead = 3; tokens_for_name_if_present = 1
    for message in messages:
        num_tokens += tokens_per_message_overhead
        if message.get("name"): num_tokens += tokens_for_name_if_present
        content = message.get("content")
        if content:
            if isinstance(content, str):
                try: num_tokens += len(encoding.encode(content))
                except Exception as e: logger.debug(f"Tiktoken content encode error (str): {e}")
            elif isinstance(content, list): # For multimodal messages
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                        try: num_tokens += len(encoding.encode(part["text"]))
                        except Exception as e: logger.debug(f"Tiktoken content encode error (text part): {e}")
                    # Image tokens are harder to estimate precisely without model-specific logic
                    # OpenAI uses a fixed cost per image, or cost based on resolution.
                    # For a rough estimate, we can add a fixed number or ignore for client-side.
                    # For now, let's add a placeholder if an image part exists.
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        num_tokens += 70 # Rough estimate for an image part placeholder/overhead
            else: # Fallback for other content types
                try: num_tokens += len(encoding.encode(str(content)))
                except Exception as e: logger.debug(f"Tiktoken content encode error (other type): {e}")
        tool_calls = message.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict) and "function" in tool_call:
                    if tc_id := tool_call.get("id"):
                        try: num_tokens += len(encoding.encode(tc_id))
                        except Exception as e: logger.debug(f"Tiktoken tool_call.id encode error: {e}")
                    function_data = tool_call.get("function", {}); name = function_data.get("name"); arguments = function_data.get("arguments")
                    try:
                        if name: num_tokens += len(encoding.encode(name))
                        if arguments and isinstance(arguments, str): num_tokens += len(encoding.encode(arguments))
                    except Exception as e: logger.debug(f"Tiktoken tool data encode error: {e}")
                    num_tokens += 5 # Overhead for tool call structure
        if message.get("role") == "tool":
            if tool_call_id_val := message.get("tool_call_id"):
                try: num_tokens += len(encoding.encode(tool_call_id_val))
                except Exception as e: logger.debug(f"Tiktoken tool_call_id encode error (tool role): {e}")
    num_tokens += 3 # Every reply is primed with <|start|>assistant<|message|>
    return num_tokens


class PathosInterface:
    INTENT_TO_SEARCH_PHRASES = [
        "look that up", "check online", "find out about that",
        "search for that", "see what i can find", "let me check",
        "i'll try to find that", "i should look into that", "wonder what the web says",
        "let me search that", "i'll google that"
    ]

    def __init__(self, config: Config, ethos_core: EthosCore, logos_core: LogosCore, connection_manager: 'ConnectionManager'):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.connection_manager = connection_manager
        self.pathos_llm_config: Optional[LLMConfig] = config.get_llm_config('PATHOS')
        self._enhanced_pathos_llm_config: Optional[LLMConfig] = None
        self.current_active_user_id: str = "default_user"
        self.eidos_tts_service_instance: Optional['ExternalTTSService'] = None
        self.audio_cache: Optional[Dict[str, bytes]] = None
        self.audio_cache_lock: Optional[asyncio.Lock] = None
        timeout_seconds_cfg = self.pathos_llm_config.get('timeout', 300.0) if self.pathos_llm_config else 300.0
        try: timeout_value = float(timeout_seconds_cfg)
        except (ValueError, TypeError): timeout_value = 300.0
        self.http_client = httpx.AsyncClient(timeout=timeout_value)
        logger.info("PathosInterface initialized.")

    async def _get_enhanced_pathos_llm_config(self) -> Optional[LLMConfig]:
        if self._enhanced_pathos_llm_config is not None:
            return self._enhanced_pathos_llm_config
        self._enhanced_pathos_llm_config = await Config.get_llm_config_with_auto_detection('PATHOS')
        if self._enhanced_pathos_llm_config:
            detected_model = self._enhanced_pathos_llm_config.get('model')
            original_model = self.pathos_llm_config.get('model') if self.pathos_llm_config else None
            if detected_model != original_model and original_model and original_model.lower() == "auto": # Log only if 'auto' was resolved
                logger.info(f"Enhanced PATHOS config: resolved 'auto' model to '{detected_model}'")
        elif self.pathos_llm_config: # Fallback to base config if auto-detection fails
            self._enhanced_pathos_llm_config = self.pathos_llm_config
            logger.warning("Failed to get auto-detected LLM config for PATHOS, using base config.")
        else:
            logger.error("No base LLM configuration found for PATHOS role.")
        return self._enhanced_pathos_llm_config

    def set_tts_service(self, tts_service: 'ExternalTTSService'):
        self.eidos_tts_service_instance = tts_service
        logger.info("ExternalTTSService instance set in PathosInterface.")

    def set_audio_cache(self, cache: Dict[str, bytes], lock: Optional[asyncio.Lock] = None):
        self.audio_cache = cache; self.audio_cache_lock = lock
        if self.audio_cache is not None: logger.info("PathosInterface: Audio cache and lock set.")
        else: logger.error("PathosInterface.set_audio_cache received a None cache object!")

    def get_static_system_prompt_content(self) -> Optional[str]: # Used for VLLM cache warming
        try:
            main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "Error: Main Pathos system prompt template could not be loaded.")
            if self.ethos_core:
                persona_directives_content = "\n".join(self.ethos_core.get_persona_directives())
            else: # Fallback if ethos_core not yet available (e.g. very early startup)
                persona_directives_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos.")

            # Minimal replacements for a static prompt
            static_prompt = main_system_prompt_template.replace("{{PATHOS_PERSONA_DIRECTIVES_FROM_FILE}}", persona_directives_content)
            # Replace other placeholders with generic static values or remove them
            placeholders_to_remove_or_static_fill = [
                "{{CURRENT_DATETIME_FOR_PROMPT}}", "{{USER_PROFILE_SUMMARY_FOR_PROMPT}}",
                "{{CURRENT_ACTIVITY_DESCRIPTION}}", "{{CURRENT_MOOD_FOR_PROMPT}}",
                "{{CURRENT_HEXUS_SCORES_FOR_PROMPT}}", "{{PATHOS_SCHEDULE_CONTEXT}}",
                "{{PATHOS_ASPIRATIONS_CONTEXT}}", "{{RELEVANT_MEMORIES_CONTEXT_FOR_PROMPT}}",
                "{{TODAYS_BRIEFING_CONTEXT_FOR_PROMPT}}", "{{VISION_ANALYSIS_CONTEXT_FOR_PROMPT}}"
            ]
            for ph in placeholders_to_remove_or_static_fill:
                static_prompt = static_prompt.replace(ph, f"[{ph.strip('{}').replace('_FOR_PROMPT','').replace('_CONTEXT','')} context placeholder]")
            
            # Include tools as they are part of the static structure the LLM needs to learn
            tools_to_include = getattr(self, 'AVAILABLE_TOOLS_FOR_PATHOS_LLM', ALL_AVAILABLE_SYSTEM_TOOLS)
            static_prompt = static_prompt.replace("{{AVAILABLE_TOOLS_JSON_FOR_PROMPT}}", json.dumps(tools_to_include, indent=2))
            return static_prompt
        except Exception as e:
            logger.error(f"Error loading static system prompt content for cache warming: {e}", exc_info=True)
            return "You are a helpful AI named Pathos." # Basic fallback

    def _update_active_user(self, new_user_id: str, set_by_statement: bool = False):
        normalized_id = (new_user_id.lower().strip().replace(" ", "_") if new_user_id else "unknown_user") or "unknown_user"
        if not normalized_id: normalized_id = "unknown_user"
        if self.current_active_user_id != normalized_id:
            logger.info(f"PathosInterface: Active user changed from '{self.current_active_user_id}' to '{normalized_id}'.")
            self.current_active_user_id = normalized_id

    async def _build_main_llm_messages(
        self, user_id: str, user_input_text: str, history_context: List[Dict[str, Any]],
        image_data_b64: Optional[str] = None, vision_description_if_non_multimodal: Optional[str] = None,
        document_text: Optional[str] = None, force_web_search: bool = False, engaged_proactive_id: Optional[str] = None,
        system_provided_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], List[MemoryEntry], Dict[str, float], Dict[str, float], int]:

        main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "ERROR: Main Pathos system prompt template not found.")
        
        if self.ethos_core:
            persona_directives_content = "\n".join(self.ethos_core.get_persona_directives())
        else:
            persona_directives_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos.")

        current_mood_dict = self.ethos_core.get_current_mood() if self.ethos_core else {'valence': 0.0, 'arousal': 0.0}
        current_mood_str = f"Valence: {current_mood_dict['valence']:.2f}, Arousal: {current_mood_dict['arousal']:.2f}"
        current_activity_description = (await self.ethos_core.get_current_activity_description()) if self.ethos_core else "Currently idle."
        hexus_scores_dict = self.ethos_core.get_hexus_scores() if self.ethos_core else {}
        hexus_scores_str = ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_dict.items()]) or "N/A"
        user_profile_summary = (await self.ethos_core.get_user_profile_summary(user_id)) if self.ethos_core else "No profile info."
        
        try:
            current_time_str = await self.logos_core.execute_get_time(location=None) if self.logos_core else datetime.now(timezone.utc).strftime("%A, %B %d, %Y, %I:%M %p %Z")
            if not isinstance(current_time_str, str) or "Error" in current_time_str or "error" in current_time_str.lower():
                 current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")
        except Exception: current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")
        
        memory_query_parts = [user_input_text]
        if document_text: memory_query_parts.append("[Document content attached]")
        retrieved_memories_raw: List[MemoryEntry] = []
        if self.ethos_core:
            retrieved_memories_raw = await self.ethos_core.retrieve_relevant_memories(
                " ".join(memory_query_parts),
                top_k=Config.get_nested_value(self.config.ETHOS, ['retrieval_limit_for_pathos_context'], 3),
                user_id_context=user_id
            )
        memories_formatted_for_prompt = "\n".join([f"- {m['content'][:300]}..." for m in retrieved_memories_raw if isinstance(m, dict) and 'content' in m]) or "No specific memories retrieved."

        enhanced_config = await self._get_enhanced_pathos_llm_config()
        is_multimodal_llm = enhanced_config and enhanced_config.get('supports_vision', False)
        vision_analysis_context_for_prompt = "No image provided this turn."
        if image_data_b64:
            if is_multimodal_llm: vision_analysis_context_for_prompt = "Image data provided directly in user message."
            elif vision_description_if_non_multimodal: vision_analysis_context_for_prompt = vision_description_if_non_multimodal
            else: vision_analysis_context_for_prompt = "Image provided, but no description generated (non-multimodal LLM)."
        
        pathos_schedule_context = (await self.ethos_core.get_pathos_schedule_context_for_prompt()) if self.ethos_core else "No schedule info."
        pathos_aspirations_context = (await self.ethos_core.get_pathos_aspirations_context_for_prompt()) if self.ethos_core else "No aspirations info."
        todays_briefing_context = (await self.ethos_core.get_todays_briefing_context_for_prompt(user_id)) if self.ethos_core else "No briefing info."
        
        tools_to_include_in_prompt = getattr(self, 'AVAILABLE_TOOLS_FOR_PATHOS_LLM', ALL_AVAILABLE_SYSTEM_TOOLS)
        available_tools_json_for_prompt = json.dumps(tools_to_include_in_prompt, indent=2)

        system_prompt_replacements = {
            "{{PATHOS_PERSONA_DIRECTIVES_FROM_FILE}}": persona_directives_content,
            "{{CURRENT_DATETIME_FOR_PROMPT}}": current_time_str,
            "{{USER_PROFILE_SUMMARY_FOR_PROMPT}}": user_profile_summary,
            "{{CURRENT_ACTIVITY_DESCRIPTION}}": current_activity_description,
            "{{CURRENT_MOOD_FOR_PROMPT}}": current_mood_str,
            "{{CURRENT_HEXUS_SCORES_FOR_PROMPT}}": hexus_scores_str,
            "{{PATHOS_SCHEDULE_CONTEXT}}": pathos_schedule_context,
            "{{PATHOS_ASPIRATIONS_CONTEXT}}": pathos_aspirations_context,
            "{{RELEVANT_MEMORIES_CONTEXT_FOR_PROMPT}}": memories_formatted_for_prompt,
            "{{TODAYS_BRIEFING_CONTEXT_FOR_PROMPT}}": todays_briefing_context,
            "{{VISION_ANALYSIS_CONTEXT_FOR_PROMPT}}": vision_analysis_context_for_prompt,
            "{{AVAILABLE_TOOLS_JSON_FOR_PROMPT}}": available_tools_json_for_prompt
        }
        
        final_system_prompt_content = main_system_prompt_template
        for placeholder, value in system_prompt_replacements.items():
            final_system_prompt_content = final_system_prompt_content.replace(placeholder, str(value) if value is not None else "")

        if force_web_search:
            final_system_prompt_content += "\n\nIMPORTANT_NOTE: User requested web search. Prioritize web_search tool if appropriate."
        
        if system_provided_info: # For weather, time etc. handled by PathosInterface
            final_system_prompt_content += "\n\n--- System Provided Information (for your awareness) ---"
            if info := system_provided_info.get("weather"): final_system_prompt_content += f"\nCurrent Weather Context: Location: {info.get('location')}, Conditions: {info.get('temperature')}{info.get('unit')} {info.get('description')}."
            if info := system_provided_info.get("current_time_info"): final_system_prompt_content += f"\nCurrent Time Context: {info}"
            if info := system_provided_info.get("news_headlines"): final_system_prompt_content += f"\nRecent News Headlines Context: {str(info)[:500]}..."
            if info := system_provided_info.get("web_search_summary"): final_system_prompt_content += f"\nQuick Web Search Summary: {info}"
            final_system_prompt_content += "\n--- End System Provided Information ---"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": final_system_prompt_content}]
        
        # Ensure history is clean of residual system messages if they are identical to the new one
        # or if they are old error messages. This is a simple cleanup.
        cleaned_history = []
        for msg in history_context:
            if msg.get("role") == "system":
                # Skip if it's identical to what we are about to send, or a known problematic default
                if msg.get("content") == final_system_prompt_content or \
                   "Error: Main Pathos system prompt not found" in msg.get("content","") or \
                   msg.get("content") == "You are a helpful assistant":
                    continue
            cleaned_history.append(msg)
        
        if cleaned_history: messages.extend(cleaned_history)
        
        user_message_content_parts: List[Dict[str, Any]] = []
        current_user_input_full = user_input_text
        if document_text: current_user_input_full += f"\n\n--- Attached Document Content ---\n{document_text}\n--- End of Document ---"
        user_message_content_parts.append({"type": "text", "text": current_user_input_full})
        
        if image_data_b64 and is_multimodal_llm:
            image_mime_type = "image/jpeg"
            if image_data_b64.startswith("iVBORw0KGgo"): image_mime_type = "image/png"
            elif image_data_b64.startswith("/9j/"): image_mime_type = "image/jpeg"
            user_message_content_parts.append({"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{image_data_b64}"}})
        
        final_user_content: Union[str, List[Dict[str,Any]]] = user_message_content_parts[0]["text"] if len(user_message_content_parts) == 1 and user_message_content_parts[0]["type"] == "text" else user_message_content_parts
        messages.append({"role": "user", "content": final_user_content})
            
        estimated_tokens = -1
        if enhanced_config:
            model_name_for_tiktoken = enhanced_config.get('model_name_for_tiktoken', enhanced_config.get('model', 'cl100k_base'))
            estimated_tokens = estimate_tokens_for_messages(messages, model_name_for_tiktoken)
            logger.info(f"Estimated tokens for _build_main_llm_messages (user: {user_id}, model for tiktoken: {model_name_for_tiktoken}): {estimated_tokens}")
        
        logger.info(f"Built main LLM messages for user '{user_id}'. System prompt length: {len(final_system_prompt_content)}. Total messages: {len(messages)}")
        # logger.debug(f"Full system prompt for user '{user_id}':\n{final_system_prompt_content}") # Uncomment for extreme debug
        
        return messages, retrieved_memories_raw, current_mood_dict, hexus_scores_dict, estimated_tokens

    async def _call_llm_directly(
        self, llm_config_to_use: LLMConfig, messages: List[Dict[str, Any]],
        tools_definition: Optional[List[Dict[str, Any]]] = None,
        temperature_override: Optional[float] = None, max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None, pathos_model_override: Optional[str] = None,
        stream: bool = False
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        request_id = str(uuid.uuid4())
        logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Initiating. Stream: {stream}")

        if not llm_config_to_use:
            logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: LLM configuration missing.")
            yield {"type": "error_chunk", "payload": "LLM configuration missing."}; return
        
        api_key = llm_config_to_use.get('api_key')
        base_url_from_config = llm_provider_url_override or llm_config_to_use.get('base_url') or llm_config_to_use.get('url')
        model_name = pathos_model_override or llm_config_to_use.get('model_name') or llm_config_to_use.get('model')
        
        if not base_url_from_config or not model_name:
            logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: LLM config incomplete. URL: {base_url_from_config}, Model: {model_name}")
            yield {"type": "error_chunk", "payload": "LLM configuration incomplete (URL or model name)."}; return
        
        request_url = f"{str(base_url_from_config).rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
            headers["Authorization"] = f"Bearer {api_key}"

        payload: Dict[str, Any] = {"model": model_name, "messages": messages, "stream": stream}
        if tools_definition: payload["tools"] = tools_definition; payload["tool_choice"] = "auto"
        
        # Temperature
        final_temp_val = temperature_override if temperature_override is not None else llm_config_to_use.get('temperature')
        if final_temp_val is not None: # Check if it's not None before casting
            try:
                payload["temperature"] = float(final_temp_val)
            except (ValueError, TypeError):
                logger.warning(f"Invalid temperature value '{final_temp_val}', using default 0.7.")
                payload["temperature"] = 0.7
        else: # Default if not in config and no override
            payload["temperature"] = 0.7

        # Top_p - Corrected Handling
        top_p_val_from_config = llm_config_to_use.get('top_p')
        if top_p_val_from_config is not None: # Only add to payload if it's explicitly set and not None
            try:
                payload["top_p"] = float(top_p_val_from_config)
            except (ValueError, TypeError):
                logger.warning(f"Invalid top_p value '{top_p_val_from_config}' in LLM config, omitting from payload (server will use its default).")
        # If top_p_val_from_config is None, we don't add 'top_p' to the payload,
        # allowing the LLM server to use its own default for top_p.

        # Max Tokens
        final_max_tokens = max_tokens_override if max_tokens_override is not None else llm_config_to_use.get('max_tokens')
        if final_max_tokens is not None: payload["max_tokens"] = int(final_max_tokens)
        
        # Removed chat_template_kwargs for Qwen3 on VLLM, relying on VLLM's native handling or --chat-template flag
        
        logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Payload for {request_url} (Model: {model_name}): {json.dumps(payload, indent=2)}")

        try:
            logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Attempting stream POST to {request_url}")
            async with self.http_client.stream("POST", request_url, headers=headers, json=payload) as response:
                logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Stream opened. Initial status: {response.status_code}")
                
                if response.status_code == 200:
                    current_tool_call_parts_by_index: Dict[int, Dict[str, Any]] = {}
                    line_count = 0; yielded_any_content = False

                    async for line_bytes in response.aiter_lines():
                        line = line_bytes.strip(); line_count += 1
                        logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Raw stream line {line_count}: '{line[:200]}...'")

                        if not line: continue
                        if line.startswith("data: "):
                            line_content = line[len("data: "):].strip()
                            if line_content == "[DONE]":
                                logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Stream [DONE] received.")
                                if current_tool_call_parts_by_index:
                                    finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc["function"].get("name")]
                                    if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                break
                            try:
                                chunk = json.loads(line_content)
                                logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Parsed chunk: {json.dumps(chunk, indent=2)}")
                                if not chunk.get("choices"): continue
                                choice = chunk.get("choices", [{}])[0]; delta = choice.get("delta", {}); finish_reason = choice.get("finish_reason")
                                
                                if content_delta := delta.get("content"):
                                    if content_delta is not None: yield content_delta; yielded_any_content = True
                                
                                if tool_calls_delta := delta.get("tool_calls"):
                                    yielded_any_content = True # Tool calls are also "content" in a sense
                                    for tc_item_delta in tool_calls_delta:
                                        idx = tc_item_delta.get("index", 0)
                                        if idx not in current_tool_call_parts_by_index: current_tool_call_parts_by_index[idx] = {"id": tc_item_delta.get("id"), "type": "function", "function": {"name": "", "arguments": ""}}
                                        current_call = current_tool_call_parts_by_index[idx]
                                        if tc_item_delta.get("id"): current_call["id"] = tc_item_delta["id"]
                                        if func_delta := tc_item_delta.get("function"):
                                            if func_delta.get("name"): current_call["function"]["name"] += func_delta["name"]
                                            if func_delta.get("arguments"): current_call["function"]["arguments"] += func_delta["arguments"]
                                
                                if finish_reason:
                                    logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Finish reason: {finish_reason}")
                                    if finish_reason == "tool_calls":
                                        finalized_tools = [tc for tc in current_tool_call_parts_by_index.values() if tc.get("id") and tc["function"].get("name")]
                                        if finalized_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": finalized_tools}}
                                        current_tool_call_parts_by_index = {}
                                    if usage_data := chunk.get("usage"): yield {"type": "usage_chunk", "payload": usage_data}
                            except json.JSONDecodeError as e_json: logger.warning(f"CALL_LLM_DIRECTLY [{request_id}]: Stream JSON decode error for line: '{line_content}'. Error: {e_json}")
                        elif line.startswith('{"error":'): # VLLM might send a single JSON error object
                            try: error_data = json.loads(line); error_msg = error_data.get('error', {}).get('message', 'Unknown stream error object'); yield {"type": "error_chunk", "payload": f"LLM Stream Error Object: {error_msg}"}; return
                            except json.JSONDecodeError: yield {"type": "error_chunk", "payload": "Malformed error from LLM stream."}; return
                        else: logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Skipping non-SSE line: {line[:100]}")
                    
                    if not yielded_any_content and not current_tool_call_parts_by_index: # If stream ended (or [DONE]) but nothing useful was yielded
                        logger.warning(f"CALL_LLM_DIRECTLY [{request_id}]: Stream finished but no content or tool calls were yielded.")
                        # This might be where an "Unknown LLM error" could be generated by the consuming function if it expects output
                else: # Non-200 status
                    error_content_bytes = await response.aread(); error_content_str = str(error_content_bytes, 'utf-8', errors='replace')
                    logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: LLM API Error {response.status_code}: {error_content_str[:500]}")
                    yield {"type": "error_chunk", "payload": f"LLM API Error {response.status_code}: {error_content_str[:200]}"}
        
        except httpx.ReadTimeout: logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: LLM API request to {request_url} timed out."); yield {"type": "error_chunk", "payload": "LLM API request timed out."}
        except httpx.RequestError as e_req: logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: LLM request error to {request_url}: {str(e_req)}"); yield {"type": "error_chunk", "payload": f"LLM request error: {str(e_req)}"}
        except Exception as e: logger.error(f"CALL_LLM_DIRECTLY [{request_id}]: Unexpected error in LLM call to {request_url}: {str(e)}", exc_info=True); yield {"type": "error_chunk", "payload": f"Unexpected error in LLM call: {str(e)}"}
        
        logger.debug(f"CALL_LLM_DIRECTLY [{request_id}]: Call finished.")

    async def _call_llm_with_tools(
        self, llm_config_to_use: LLMConfig, messages: List[Dict[str, Any]],
        tools_definition: List[Dict[str, Any]], user_id: str, stream_tool_calls: bool = False,
        temperature_override: Optional[float] = None, max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None, pathos_model_override: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        current_messages = list(messages)
        max_iterations = llm_config_to_use.get('max_tool_iterations', 3)
        llm_error_occurred_in_loop = False

        for i in range(max_iterations):
            logger.info(f"LLM tool iteration {i + 1}/{max_iterations} for user '{user_id}'. Message count: {len(current_messages)}")
            accumulated_content_chunks: List[str] = []
            llm_had_tool_calls_this_iter = False
            llm_usage_this_iter: Optional[Dict[str, Any]] = None
            assistant_msg_obj_this_iter: Optional[Dict[str, Any]] = None # To store the assistant message that contains tool_calls

            async for llm_item in self._call_llm_directly(
                llm_config_to_use=llm_config_to_use, messages=current_messages,
                tools_definition=tools_definition, stream=True,
                temperature_override=temperature_override, max_tokens_override=max_tokens_override,
                llm_provider_url_override=llm_provider_url_override, pathos_model_override=pathos_model_override
            ):
                item_type = llm_item.get("type") if isinstance(llm_item, dict) else "text_chunk_direct_str"
                payload = llm_item.get("payload") if isinstance(llm_item, dict) else llm_item

                if item_type == "text_chunk_direct_str" and isinstance(payload, str): # Direct string yield
                    if not llm_had_tool_calls_this_iter: accumulated_content_chunks.append(payload)
                    if stream_tool_calls: yield {"type": "text_chunk", "payload": payload}
                elif item_type == "tool_calls_chunk" and isinstance(payload, dict):
                    llm_had_tool_calls_this_iter = True
                    assistant_msg_obj_this_iter = payload # This payload is like {"role": "assistant", "tool_calls": [...]}
                    accumulated_content_chunks = [] # Clear any text if tools are called
                elif item_type == "error_chunk":
                    logger.error(f"CALL_LLM_WITH_TOOLS: Error chunk received from _call_llm_directly: {payload}")
                    yield llm_item; llm_error_occurred_in_loop = True; return
                elif item_type == "usage_chunk": llm_usage_this_iter = payload
            
            if llm_error_occurred_in_loop: return # Stop if an error was propagated

            if llm_had_tool_calls_this_iter and assistant_msg_obj_this_iter:
                current_messages.append(assistant_msg_obj_this_iter)
                yield {"type": "assistant_message_chunk", "payload": assistant_msg_obj_this_iter}
                
                actual_tool_calls = assistant_msg_obj_this_iter.get("tool_calls", [])
                if not actual_tool_calls:
                    final_text_on_bad_tool = "".join(accumulated_content_chunks).strip() or "Tool call error: No tools found in assistant message."
                    logger.warning(f"LLM indicated tool calls but none were found in message: {assistant_msg_obj_this_iter}")
                    final_msg_obj = {"role": "assistant", "content": final_text_on_bad_tool}
                    current_messages.append(final_msg_obj); yield {"type": "final_assistant_message", "payload": final_msg_obj}
                    if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                    return

                tool_results = await self._execute_tools(actual_tool_calls, user_id)
                for res_msg in tool_results: current_messages.append(res_msg); yield {"type": "tool_result_chunk", "payload": res_msg}
                
                if i == max_iterations - 1:
                    logger.warning(f"Max tool iterations ({max_iterations}) reached for user '{user_id}'. Forcing final response.")
                    final_prompt_msgs_max = list(current_messages) + [{"role": "user", "content": "Max tool uses reached. Provide your final answer to the original query now based on all available information."}]
                    final_text_acc_max = []; final_usage_max_iter: Optional[Dict[str, Any]] = None
                    async for item_max in self._call_llm_directly(llm_config_to_use, final_prompt_msgs_max, None, True, temperature_override, max_tokens_override, llm_provider_url_override, pathos_model_override):
                        if isinstance(item_max, str): final_text_acc_max.append(item_max)
                        if stream_tool_calls and isinstance(item_max, str): yield {"type": "text_chunk", "payload": item_max}
                        elif isinstance(item_max, dict) and item_max.get("type") == "error_chunk": yield item_max; return
                        elif isinstance(item_max, dict) and item_max.get("type") == "usage_chunk": final_usage_max_iter = item_max.get("payload")
                    final_text_max = "".join(final_text_acc_max).strip() or "Tool limit reached; processing complete."
                    final_msg_obj_max = {"role": "assistant", "content": final_text_max}
                    current_messages.append(final_msg_obj_max); yield {"type": "final_assistant_message", "payload": final_msg_obj_max}
                    if final_usage_max_iter: yield {"type": "usage_chunk", "payload": final_usage_max_iter}
                    elif llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                    return
            else: # No tool calls this iteration, should be a direct text response
                final_text_response = "".join(accumulated_content_chunks).strip()
                if not final_text_response and not llm_error_occurred: # Check if any error occurred during _call_llm_directly
                    logger.warning(f"No text content accumulated and no tool calls in iteration {i+1} for user \'{user_id}\'.")
                    final_text_response = "I'm not sure how to respond to that. Can you try rephrasing?" if i == 0 else "Okay, I've processed that."
                
                final_msg_obj = {"role": "assistant", "content": final_text_response}
                current_messages.append(final_msg_obj)
                yield {"type": "final_assistant_message", "payload": final_msg_obj}
                if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                return
        
        logger.warning(f"Tool call loop completed all iterations without a definitive response for user '{user_id}'.")
        fallback_text = "I've completed a series of actions. If you need more help, please let me know!"
        if stream_tool_calls and not accumulated_content_chunks: yield {"type": "text_chunk", "payload": fallback_text}
        final_fallback_msg_obj = {"role": "assistant", "content": fallback_text}
        current_messages.append(final_fallback_msg_obj); yield {"type": "final_assistant_message", "payload": final_fallback_msg_obj}
        if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}

    async def _execute_tools(self, tool_calls: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        tool_results_messages = []
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name"); function_args_str = tool_call.get("function", {}).get("arguments", "{}"); tool_call_id = tool_call.get("id")
            if not function_name or not tool_call_id:
                tool_results_messages.append({"tool_call_id": tool_call_id or "unknown_tool_id", "role": "tool", "name": function_name or "unknown_function", "content": json.dumps({"error": "Tool call missing function name or ID."})}); continue
            logger.info(f"Executing tool: {function_name} (ID: {tool_call_id}) for user '{user_id}'. Args: {function_args_str[:100]}")
            try: function_args = json.loads(function_args_str)
            except json.JSONDecodeError as e:
                tool_results_messages.append({"tool_call_id": tool_call_id, "role": "tool", "name": function_name, "content": json.dumps({"error": f"Invalid JSON arguments: {e}"})}); continue
            tool_response_content_str = ""
            try:
                if function_name == "get_current_time": tool_response_content_str = await self.logos_core.execute_get_time(function_args.get("location"))
                elif function_name == "web_search": tool_response_content_str = json.dumps(await self.logos_core.execute_web_search(function_args.get("query")))
                elif function_name == "math_calculator": tool_response_content_str = await self.logos_core.execute_math_calculation(function_args.get("expression"))
                elif function_name == "get_weather": tool_response_content_str = json.dumps(await self.logos_core.execute_get_weather(function_args.get("location"), user_id_context=user_id))
                elif function_name == "store_user_fact": tool_response_content_str = await self.logos_core.execute_store_user_fact(function_args.get("attribute_name"), function_args.get("attribute_value"), function_args.get("user_statement_context"), user_id)
                elif function_name == "store_world_fact": tool_response_content_str = await self.logos_core.execute_store_world_fact(function_args.get("fact_statement"), function_args.get("source_description"), function_args.get("topic_tags"), function_args.get("confidence_level", 0.8))
                elif function_name == "perform_deep_research": tool_response_content_str = await self.logos_core.execute_deep_research(function_args.get("research_query"), function_args.get("number_of_searches", 3))
                elif function_name == "get_news_headlines": tool_response_content_str = await self.logos_core.execute_get_news_headlines()
                elif function_name == "add_pathos_event":
                    event_id = await self.ethos_core.chronos_bridge_add_event(title=function_args.get("title"), start_date_str=function_args.get("start_date"), end_date_str=function_args.get("end_date"), event_type_str=function_args.get("event_type"), description=function_args.get("description"), location=function_args.get("location"), activity_theme=function_args.get("activity_theme"), planned_sites_or_tasks=function_args.get("planned_sites_or_tasks"), user_id_for_event=PATHOS_USER_ID)
                    tool_response_content_str = json.dumps({"status": "success", "event_id": event_id, "message": f"Event '{function_args.get('title')}' scheduled."}) if event_id else json.dumps({"status": "error", "message": f"Failed to schedule event '{function_args.get('title')}'."})
                elif function_name == "initiate_simulated_interaction": tool_response_content_str = json.dumps(await simulation_module.initiate_simulated_interaction(function_args.get("npc_name"), function_args.get("npc_role"), function_args.get("npc_description"), function_args.get("initial_context"), function_args.get("pathos_opening_statement")))
                elif function_name == "send_message_to_simulated_npc": tool_response_content_str = json.dumps(await simulation_module.send_message_to_simulated_npc(function_args.get("message_to_npc")))
                elif function_name == "end_simulated_interaction": tool_response_content_str = json.dumps(await simulation_module.end_simulated_interaction())
                else: tool_response_content_str = json.dumps({"error": f"Tool '{function_name}' not implemented."})
            except Exception as e: logger.error(f"Error executing tool {function_name} for user '{user_id}': {e}", exc_info=True); tool_response_content_str = json.dumps({"error": f"Error in tool {function_name}: {str(e)}"})
            tool_results_messages.append({"tool_call_id": tool_call_id, "role": "tool", "name": function_name, "content": tool_response_content_str})
        return tool_results_messages

    async def generate_response(
        self,
        user_id: str, # <<< ENSURE THIS IS THE FIRST POSITIONAL ARGUMENT (after self)
        user_input: str,
        image_data_b64: Optional[str] = None,
        document_text: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None,
        # Add **kwargs to accept any other potential arguments without breaking
        **kwargs: Any 
    ) -> Dict[str, Any]:
        response_metadata: Dict[str, Any] = {}
        req_meta = request_metadata if request_metadata is not None else {}
        user_id_for_response = user_id # Use the passed user_id
        self._update_active_user(user_id_for_response)
        should_stream_tts_for_this_response = req_meta.get('auto_tts_enabled_for_response', False)
        response_metadata["tts_stream_attempted"] = should_stream_tts_for_this_response
        if engaged_proactive_id := req_meta.get('engaged_proactive_id'): response_metadata["engaged_proactive_id"] = engaged_proactive_id
        
        logger.info(f"PathosInterface: Processing request for user '{user_id_for_response}' with Main PATHOS LLM.")
        
        vision_description_for_non_multimodal_pathos: Optional[str] = None
        enhanced_pathos_config = await self._get_enhanced_pathos_llm_config()
        if image_data_b64 and enhanced_pathos_config and not enhanced_pathos_config.get('supports_vision', False) and self.logos_core:
            logger.info(f"Pathos LLM for '{user_id_for_response}' not multimodal. Requesting image description.")
            vision_prompt = user_input if user_input.strip() else "Describe this image in detail."
            try:
                vision_description_for_non_multimodal_pathos = await self.logos_core.execute_describe_image(image_data_b64, vision_prompt)
                if vision_description_for_non_multimodal_pathos and vision_description_for_non_multimodal_pathos.startswith('{"error":'):
                    logger.warning(f"LogosCore image description failed: {vision_description_for_non_multimodal_pathos}")
                    vision_description_for_non_multimodal_pathos = "[System note: Error processing image description.]"
            except Exception as e_vision: logger.error(f"Error getting image description: {e_vision}", exc_info=True); vision_description_for_non_multimodal_pathos = "[System note: Error obtaining image description.]"
        
        # --- Pre-Pathos LLM Information Retrieval (if tools were removed from Pathos's direct list) ---
        system_provided_info_for_prompt: Dict[str, Any] = {}
        # Example: if "weather" in user_input.lower() and self.logos_core:
        #    weather_res = await self.logos_core.execute_get_weather(...)
        #    if weather_res.get("success"): system_provided_info_for_prompt["weather"] = weather_res["weather_data"]
        # Add similar logic for time, simple web search, news if those tools are removed from AVAILABLE_TOOLS_FOR_PATHOS_LLM

        initial_llm_messages, retrieved_memories, current_mood, hexus_scores, estimated_prompt_tokens = await self._build_main_llm_messages(
            user_id=user_id_for_response, user_input_text=user_input, history_context=req_meta.get('conversation_history', []),
            image_data_b64=image_data_b64, vision_description_if_non_multimodal=vision_description_for_non_multimodal_pathos,
            document_text=document_text, force_web_search=req_meta.get('force_web_search_requested', False),
            engaged_proactive_id=req_meta.get('engaged_proactive_id'), system_provided_info=system_provided_info_for_prompt
        )
        full_history_for_interaction_log: List[Dict[str, Any]] = list(initial_llm_messages)
        llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        final_pathos_response_text_parts: List[str] = []; tts_sequence_num = 0
        final_assistant_message_payload_for_response: Optional[Dict[str, Any]] = None

        if not enhanced_pathos_config:
            final_pathos_response_text_parts.append("I'm sorry, my internal configuration is incomplete."); llm_error_occurred = True
        else:
            current_conversation_messages = list(initial_llm_messages)
            async for item in self._call_llm_with_tools(
                llm_config_to_use=enhanced_pathos_config, messages=current_conversation_messages,
                tools_definition=getattr(self, 'AVAILABLE_TOOLS_FOR_PATHOS_LLM', ALL_AVAILABLE_SYSTEM_TOOLS), 
                user_id=user_id_for_response, stream_tool_calls=True, # stream_tool_calls=True to get text_chunks
                temperature_override=req_meta.get('temperature'), max_tokens_override=req_meta.get('max_tokens_override'),
                llm_provider_url_override=req_meta.get('llm_provider_url_override'), pathos_model_override=req_meta.get('pathos_model_override')
            ):
                item_type = item.get("type"); payload = item.get("payload")
                if item_type == "text_chunk" and isinstance(payload, str):
                    final_pathos_response_text_parts.append(payload)
                    # Send text chunk via WebSocket immediately for UI display
                    await self.connection_manager.send_personal_message({"type": "text_chunk", "payload": {"text": payload, "sequence": tts_sequence_num}}, user_id_for_response)
                    # TTS will be handled after full message is assembled
                elif item_type == "assistant_message_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "tool_result_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "final_assistant_message" and isinstance(payload, dict):
                    full_history_for_interaction_log.append(payload); final_assistant_message_payload_for_response = payload
                    # If final message has content, ensure it's part of the response parts
                    if final_content := payload.get("content"):
                        if not "".join(final_pathos_response_text_parts).strip() and isinstance(final_content, str): # If parts are empty, use this
                             final_pathos_response_text_parts = [final_content]
                elif item_type == "error_chunk":
                    error_content = payload if isinstance(payload, str) else "Unknown LLM error from stream"
                    final_pathos_response_text_parts.append(f"[{error_content}]")
                    llm_error_occurred = True; full_history_for_interaction_log.append({"role": "system", "content": f"LLM Error: {error_content}"})
                    logger.error(f"LLM error_chunk received: {error_content}"); break
                elif item_type == "usage_chunk": llm_usage_data = payload
        
        final_pathos_response_text = "".join(final_pathos_response_text_parts).strip()
        if final_assistant_message_payload_for_response and isinstance(final_assistant_message_payload_for_response.get("content"), str) and not final_pathos_response_text:
            final_pathos_response_text = final_assistant_message_payload_for_response["content"] # Ensure final message content is used if parts were empty
        
        final_pathos_response_text = re.sub(r"<think>.*?</think>\s*", "", final_pathos_response_text, flags=re.DOTALL).strip()
        if not final_pathos_response_text and not llm_error_occurred and not (final_assistant_message_payload_for_response and final_assistant_message_payload_for_response.get("tool_calls")):
             final_pathos_response_text = "Understood."

        if final_pathos_response_text and should_stream_tts_for_this_response and self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
            sentences = re.split(r'(?<=[.!?])\s+', final_pathos_response_text.strip())
            for sentence_text in sentences:
                sentence = sentence_text.strip();
                if not sentence: continue
                forced_chunk_id = f"chat_tts_main_{user_id_for_response}_{uuid.uuid4().hex[:8]}_{tts_sequence_num}"
                asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id_for_response, sequence_num=tts_sequence_num, forced_chunk_id=forced_chunk_id))
                tts_sequence_num += 1
        
        if self.ethos_core: self.ethos_core.update_mood_on_interaction(user_input, final_pathos_response_text, bool(image_data_b64), bool(document_text))
        
        tool_calls_for_metadata = final_assistant_message_payload_for_response.get("tool_calls") if final_assistant_message_payload_for_response else None

        # --- Intent to Search Detection Logic ---
        detected_intent_to_search = False
        original_user_query_for_search = user_input # The user's input that might have triggered Pathos's intent
        pathos_formulated_search_query = None # Placeholder

        if final_pathos_response_text and not tool_calls_for_metadata: # Only check if no tools were called by Pathos
            response_lower = final_pathos_response_text.lower()
            for phrase in self.INTENT_TO_SEARCH_PHRASES:
                if phrase.lower() in response_lower:
                    detected_intent_to_search = True
                    logger.info(f"PathosInterface: Detected intent to search in response: '{final_pathos_response_text}' (Trigger: '{phrase}') for user_id: {user_id}, conversation_id: {conversation_id}")
                    
                    pathos_formulated_search_query = f"Information related to Pathos's statement: '{final_pathos_response_text}' (Original user query: '{user_input}')" 
                    
                    response_metadata["detected_intent_to_search"] = True
                    response_metadata["pathos_stated_intent_text"] = final_pathos_response_text
                    response_metadata["original_user_query_for_search"] = user_input
                    response_metadata["pathos_formulated_search_query_mvp"] = pathos_formulated_search_query # Storing the naive query
                    
                    break
        
        if detected_intent_to_search:
            logger.info(f"PathosInterface: TODO - Call Computer Interaction Module with query. User='{original_user_query_for_search}', Pathos Response='{final_pathos_response_text}' for user_id: {user_id}, conversation_id: {conversation_id}")
            # For this phase, Pathos's original response (expressing intent) is returned.
            # The 'response_metadata' carries the detection info.
            pass 
        # --- End Intent to Search Detection ---

        response_metadata["tool_calls_from_pathos"] = tool_calls_for_metadata
        response_metadata["error_flag"] = llm_error_occurred
        response_metadata["mood_at_response"] = current_mood
        response_metadata["hexus_scores"] = hexus_scores
        response_metadata["retrieved_memory_ids"] = [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m]
        if llm_usage_data:
            response_metadata["prompt_tokens_from_llm"] = llm_usage_data.get("prompt_tokens")
            response_metadata["completion_tokens_from_llm"] = llm_usage_data.get("completion_tokens")
        if estimated_prompt_tokens > 0: response_metadata["estimated_prompt_tokens"] = estimated_prompt_tokens

        if self.ethos_core:
            await self._store_final_interaction(
                original_user_input=user_input, pathos_response=final_pathos_response_text, mood_at_response=current_mood,
                retrieved_memories=retrieved_memories, full_history_for_pathos=full_history_for_interaction_log, error=llm_error_occurred,
                image_provided_this_turn=bool(image_data_b64), vision_llm_output=vision_description_for_non_multimodal_pathos,
                is_proactive_turn=bool(engaged_proactive_id), forced_action=req_meta.get('force_web_search_requested')
            )
        if document_text and self.logos_core:
             asyncio.create_task(self.logos_core.add_document_to_rag(extracted_text=document_text, filename="uploaded_via_chat", user_id=user_id_for_response), name=f"AddDocToRAG_{user_id_for_response}_{uuid.uuid4().hex[:4]}")

        is_error_response = llm_error_occurred or (not final_pathos_response_text and not tool_calls_for_metadata)
        
        return {"success": not is_error_response, "content": final_pathos_response_text, "metadata": response_metadata}

    # ... (rest of the methods: _generate_proactive_message, send_sentence_to_tts_and_notify_client, process_feedback, close)
    # Ensure _store_final_interaction is also present and correct as per our previous fixes.

    async def _store_final_interaction(
        self, original_user_input: str, pathos_response: Optional[str], mood_at_response: Dict[str, float],
        retrieved_memories: List[MemoryEntry], full_history_for_pathos: List[Dict], error: bool = False,
        image_provided_this_turn: bool = False, vision_llm_output: Optional[str] = None,
        is_proactive_turn: bool = False, forced_action: Optional[str] = None
    ):
        user_id_for_memory = self.current_active_user_id
        interaction_type = "interaction_error" if error else "interaction"
        tool_usage_summary = []
        call_id_map: Dict[str, Dict[str, Any]] = {}

        for msg in full_history_for_pathos:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                calls = msg.get("tool_calls")
                if isinstance(calls, list):
                    for tc_dict in calls:
                        if isinstance(tc_dict, dict):
                            call_id = tc_dict.get("id")
                            func_info = tc_dict.get("function")
                            if call_id and isinstance(func_info, dict) and func_info.get("name"):
                                call_id_map[call_id] = {"tool_name": func_info.get("name"), "request_args": func_info.get("arguments")}
            elif msg.get("role") == "tool":
                call_id = msg.get("tool_call_id")
                if call_id and call_id in call_id_map:
                    tool_info = call_id_map[call_id]
                    result_content = str(msg.get("content", ""))
                    tool_info["result_summary"] = result_content[:200] + "..." if len(result_content) > 200 else result_content
                    if not any(summary_item.get("id_from_map") == call_id for summary_item in tool_usage_summary):
                        tool_info_copy = tool_info.copy(); tool_info_copy["id_from_map"] = call_id
                        tool_usage_summary.append(tool_info_copy)
        for call_id, tool_data in call_id_map.items():
            if not any(summary_item.get("id_from_map") == call_id for summary_item in tool_usage_summary):
                tool_data_copy = tool_data.copy(); tool_data_copy["id_from_map"] = call_id
                tool_data_copy.setdefault("result_summary", "[No result processed]"); tool_usage_summary.append(tool_data_copy)
        for item in tool_usage_summary: item.pop("id_from_map", None)

        input_summary = original_user_input[:250] + "..." if len(original_user_input) > 250 else original_user_input
        doc_included_in_input = "--- Uploaded Document Content ---" in original_user_input
        
        metadata = {
            "user_id": user_id_for_memory, "user_input_original_text": original_user_input,
            "image_provided_this_turn": image_provided_this_turn, "document_included_this_turn": doc_included_in_input,
            "vision_module_output_if_any": vision_llm_output, "main_llm_input_summary": input_summary,
            "pathos_final_response_text": pathos_response, "mood_at_response": mood_at_response,
            "retrieved_memory_ids": [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m],
            "tool_usage_summary_by_main_llm": tool_usage_summary or None,
            "is_proactive_turn": is_proactive_turn, "error_in_turn": error
        }
        if forced_action: metadata["forced_action"] = forced_action
        
        content_parts = [f"User ({user_id_for_memory}): {original_user_input}"]
        if image_provided_this_turn: content_parts.append("[Image provided by user.]")
        if vision_llm_output: content_parts.append(f"[Vision System Description: {vision_llm_output[:150]}...]")
        if doc_included_in_input: content_parts.append("[Document content included in input.]")
        content_parts.append(f"Pathos: {pathos_response if pathos_response else '[No textual response/Tool call]'}")
        if tool_usage_summary:
            tool_summary_str_parts = [f"{t.get('tool_name', 'unknown_tool')}(args={str(t.get('request_args', ''))[:50]}, result={t.get('result_summary', 'N/A')})" for t in tool_usage_summary]
            content_parts.append(f"Tools Used by Pathos: {', '.join(tool_summary_str_parts)}")
        if forced_action: content_parts.append(f"[Action '{forced_action}' was forced by user directive.]")
        if error: content_parts.append("[Error occurred during this turn.]")
        
        content_for_memory = "\n".join(content_parts)
        if self.ethos_core: # Ensure ethos_core is available
            await self.ethos_core.add_memory_entry(
                {"type": interaction_type, "content": content_for_memory, "metadata": metadata},
                user_id_context=user_id_for_memory
            )
            logger.debug(f"Stored final interaction for user '{user_id_for_memory}'. Type: {interaction_type}.")
        else:
            logger.error("EthosCore not available in PathosInterface, cannot store final interaction.")

    async def _generate_proactive_message(self, user_id: str, proactive_type: str, context: Optional[Any] = None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        enhanced_config = await self._get_enhanced_pathos_llm_config()
        if not enhanced_config: logger.error("Cannot generate proactive message: Pathos LLM not configured."); return None, []
        
        logger.info(f"Attempting to generate proactive message of type '{proactive_type}' for user '{user_id}'. Context: {str(context)[:100]}")
        prompt_for_llm = ""
        user_name_for_prompt = user_id # Or fetch a display name if available
        
        # Construct prompt_for_llm based on proactive_type and context (as in your broken code)
        # ... (This logic needs to be complete here)
        if proactive_type == "greeting":
            time_of_day = context.get("time_of_day", "day") if isinstance(context, dict) else "day"
            prompt_for_llm = f"It's a new {time_of_day} for user '{user_name_for_prompt}'. Generate a VERY CASUAL and brief 'good {time_of_day}' greeting. Think like a relaxed friend. Examples: 'Hey {user_name_for_prompt}, what\\'s up?', 'Mornin {user_name_for_prompt}!', 'Afternoon! How\\'s it hanging?'"
        elif proactive_type == "queued_discussion" and context and isinstance(context, dict):
            topic_content = context.get("topic_content", "something I was thinking about")
            reason = context.get("reason", "earlier thoughts")
            prompt_for_llm = f"You have a queued discussion point for user '{user_name_for_prompt}': '{topic_content}' (Reason: {reason}). Casually and naturally bring this up. Examples: 'Hey {user_name_for_prompt}, something crossed my mind from {reason}... {topic_content} What do you think?', 'I had a thought about {topic_content} earlier, mind if I share?'"
        # Add other proactive types here...
        else:
            logger.warning(f"Proactive message generation: No specific prompt logic for type '{proactive_type}'."); return None, []

        if not prompt_for_llm: logger.warning(f"Proactive message generation: No prompt_for_llm constructed for type '{proactive_type}'."); return None, []

        current_mood_pm = self.ethos_core.get_current_mood() if self.ethos_core else {'valence': 0.0, 'arousal': 0.0}
        hexus_scores_pm = self.ethos_core.get_hexus_scores() if self.ethos_core else {}
        
        # Use EthosCore to get persona directives if available
        if self.ethos_core:
            persona_directives_for_proactive = "\n".join(self.ethos_core.get_persona_directives())
        else:
            persona_directives_for_proactive = "You are Pathos, a friendly AI." # Basic fallback

        system_prompt_content_parts_pm = [
            persona_directives_for_proactive, # Use loaded directives
            f"\nYou are generating a specific, brief, VERY CASUAL, and proactive message for user '{user_id}'.",
            f"Your current mood is valence {current_mood_pm['valence']:.2f}, arousal {current_mood_pm['arousal']:.2f}.",
            "(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_pm.items()]) + ")",
            "Be concise and natural, consistent with your friendly and relaxed persona. Use contractions.",
            "Your response should ONLY be the proactive message text. Do not include any other text or formatting."
        ]
        system_prompt_content_pm = "\n".join(system_prompt_content_parts_pm)
        proactive_messages_for_llm = [{"role": "system", "content": system_prompt_content_pm}, {"role": "user", "content": prompt_for_llm}]
        
        proactive_text_content_accumulator = []; llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        
        async for item in self._call_llm_directly(
            llm_config_to_use=enhanced_config, messages=proactive_messages_for_llm, 
            tools_definition=None, # No tools for proactive message generation
            temperature_override=float(enhanced_config.get('temperature', 0.4)), # Slightly lower temp for more focused proactive
            max_tokens_override=150, stream=True
        ):
            if isinstance(item, str): proactive_text_content_accumulator.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type"); payload = item.get("payload")
                if item_type == "error_chunk": 
                    logger.warning(f"Proactive message generation LLM error: {payload}")
                    proactive_text_content_accumulator.append(f"[{payload}]"); llm_error_occurred = True; break
                elif item_type == "usage_chunk": llm_usage_data = payload
        
        proactive_text_content = "".join(proactive_text_content_accumulator).strip()
        if llm_usage_data: logger.info(f"LLM usage for proactive message generation: {llm_usage_data}")
        
        if proactive_text_content and not llm_error_occurred:
            proactive_text_content = re.sub(r"<think>.*?</think>\s*", "", proactive_text_content, flags=re.DOTALL).strip()
            if not proactive_text_content: logger.warning(f"Proactive message for '{proactive_type}' empty after stripping think tags."); return None, []
            
            logger.info(f"Generated proactive message text for '{proactive_type}': {proactive_text_content[:100]}...")
            audio_chunk_info_list: List[Dict[str, Any]] = []; tts_sequence_num_proactive = 0
            if self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
                sentences = re.split(r'(?<=[.!?])\s+', proactive_text_content.strip())
                for sentence_text in sentences:
                    sentence = sentence_text.strip();
                    if not sentence: continue
                    forced_chunk_id = f"proactive_tts_{user_id}_{uuid.uuid4().hex[:10]}_{tts_sequence_num_proactive}"
                    # audio_chunk_info_list.append({"url": f"/v1/tts/audio_chunk/{forced_chunk_id}", "sequence": tts_sequence_num_proactive, "text_for_indicator": sentence}) # Not needed if TTS is fire-and-forget here
                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id, sequence_num=tts_sequence_num_proactive, forced_chunk_id=forced_chunk_id, chunk_id_prefix="proactive_tts_")) # Ensure correct prefix
                    tts_sequence_num_proactive += 1
            return proactive_text_content, audio_chunk_info_list # Return audio_chunk_info_list for consistency, even if empty
        else: 
            logger.warning(f"Proactive message generation for '{proactive_type}' failed or resulted in empty content. LLM response/error: {proactive_text_content}")
            return None, []
    
    async def send_sentence_to_tts_and_notify_client(self, sentence: str, user_id: str, sequence_num: int, forced_chunk_id: Optional[str] = None, chunk_id_prefix: str = "chat_tts_main_"): # Default prefix
        if not self.eidos_tts_service_instance or not self.connection_manager or self.audio_cache is None or not self.eidos_tts_service_instance.is_available():
            logger.error(f"TTS prerequisites missing for user {user_id}. TTS Service: {self.eidos_tts_service_instance}, ConnMgr: {self.connection_manager}, AudioCache: {self.audio_cache}, TTS Available: {self.eidos_tts_service_instance.is_available() if self.eidos_tts_service_instance else False}"); return
        
        final_chunk_id = forced_chunk_id if forced_chunk_id else f"{chunk_id_prefix}{user_id}_{uuid.uuid4().hex[:10]}_{sequence_num}"
        log_prefix = f"FORCED_ID({final_chunk_id})" if forced_chunk_id else f"PREFIX({chunk_id_prefix})" # Use final_chunk_id for logging
        logger.debug(f"TTS_SEND ({user_id}, {sequence_num}, {log_prefix}): START for sentence: '{sentence[:30]}...'")
        
        audio_bytes: Optional[bytes] = None
        try: audio_bytes = await self.eidos_tts_service_instance.synthesize(text=sentence)
        except Exception as e_synth: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception during synthesize: {e_synth}", exc_info=True); return
        
        if audio_bytes:
            logger.info(f"TTS_SEND ({user_id}, {sequence_num}): Audio bytes received. Caching with chunk_id: {final_chunk_id}.")
            cache_successful = False
            try:
                if self.audio_cache_lock:
                    async with self.audio_cache_lock:
                        if self.audio_cache is not None:
                            self.audio_cache[final_chunk_id] = audio_bytes
                            cache_successful = True
                elif self.audio_cache is not None: self.audio_cache[final_chunk_id] = audio_bytes; cache_successful = True
            except Exception as e_cache: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception caching chunk {final_chunk_id}: {e_cache}", exc_info=True); return
            
            if not cache_successful: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Caching failed for chunk {final_chunk_id}."); return
            
            audio_url = f"/v1/tts/audio_chunk/{final_chunk_id}"
            is_proactive = final_chunk_id.startswith("proactive_tts_")
            ws_payload = {"type": "tts_audio_chunk_ready", "payload": {"url": audio_url, "sequence": sequence_num, "text_for_indicator": sentence, "chunk_id": final_chunk_id, "is_proactive_audio": is_proactive}}
            
            try: await self.connection_manager.send_personal_message(ws_payload, user_id); logger.info(f"TTS_SEND ({user_id}, {sequence_num}): Notification sent for chunk {final_chunk_id}.")
            except Exception as e_ws: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception sending WebSocket for chunk {final_chunk_id}: {e_ws}", exc_info=True)
        else: logger.warning(f"TTS_SEND ({user_id}, {sequence_num}): No audio bytes from synthesis for: '{sentence[:30]}...'.")
        logger.debug(f"TTS_SEND ({user_id}, {sequence_num}, {log_prefix}): END for sentence: '{sentence[:30]}...'")

    async def process_feedback(self, feedback_data: Dict[str, Any]):
        if not self.config.ENABLE_LEARNING_FROM_FEEDBACK: logger.debug("Feedback processing skipped (disabled)."); return
        required_keys = ['user_id', 'last_user_input', 'last_pathos_response', 'feedback_type']
        if not all(key in feedback_data for key in required_keys): logger.warning("Feedback data missing required keys. Skipping."); return
        if not isinstance(feedback_data.get('user_id'), str) or not isinstance(feedback_data.get('feedback_type'), str):
            logger.warning("Feedback data has invalid types for user_id or feedback_type. Skipping."); return
        
        feedback_user_id = feedback_data.get('user_id', self.current_active_user_id)
        logger.info(f"PathosInterface processing feedback for user '{feedback_user_id}': Type '{feedback_data.get('feedback_type')}'.")
        
        memory_metadata = {
            "user_id": feedback_user_id,
            "source": feedback_data.get('source', 'api_feedback_endpoint'),
            "feedback_timestamp_received_by_api": datetime.now(timezone.utc).isoformat(),
            "processed_by_reflection": False, # Mark as unprocessed initially
            **feedback_data # Include all original feedback data in metadata
        }
        # Content should be the structured feedback itself for easier processing later
        feedback_content_str = json.dumps(feedback_data) 

        if self.ethos_core:
            await self.ethos_core.add_memory_entry(
                {"type": "feedback", "content": feedback_content_str, "metadata": memory_metadata, "salience": 1.2}, # High salience for feedback
                user_id_context=feedback_user_id
            )
            if self.config.ENABLE_MOOD_SIMULATION:
                mood_update_payload = {"feedback_type": feedback_data.get("feedback_type"), "rating": feedback_data.get("rating")}
                await self.ethos_core.update_mood_state('feedback', mood_update_payload) # Assuming update_mood_state exists
        else:
            logger.error("EthosCore not available in PathosInterface, cannot process feedback.")

    async def close(self):
        try:
            if hasattr(self, 'http_client') and self.http_client and not self.http_client.is_closed:
                await self.http_client.aclose()
                logger.info("PathosInterface: HTTP client closed.")
        except Exception as e: logger.error(f"Error closing PathosInterface resources: {e}", exc_info=True)
        logger.info("PathosInterface closed.")