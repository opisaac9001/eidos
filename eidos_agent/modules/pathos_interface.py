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
    import tiktoken
except ImportError:
    tiktoken = None
    print("Warning (PathosInterface): tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken")

from eidos_agent.core.config import Config, LLMConfig
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger
from eidos_agent.core.api_models import ChatMessage
from eidos_agent.modules.chronos_engine import PATHOS_USER_ID # For add_pathos_event tool
from eidos_agent.modules import simulation_module # For NPC interaction tools

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.services.external_tts_service import ExternalTTSService

logger = get_logger(__name__)

# --- Tool Definitions ---
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

AVAILABLE_TOOLS = [
    *GET_CURRENT_TIME_TOOL_DEFINITION, *WEB_SEARCH_TOOL_DEFINITION, *MATH_CALCULATOR_TOOL_DEFINITION,
    *GET_WEATHER_TOOL_DEFINITION, *STORE_USER_FACT_TOOL_DEFINITION, *PERFORM_DEEP_RESEARCH_TOOL_DEFINITION,
    *STORE_WORLD_FACT_TOOL_DEFINITION, *GET_NEWS_HEADLINES_TOOL_DEFINITION, *ADD_PATHOS_EVENT_TOOL_DEFINITION,
    *INITIATE_SIMULATED_INTERACTION_TOOL_DEFINITION, *SEND_MESSAGE_TO_SIMULATED_NPC_TOOL_DEFINITION,
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
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                        try: num_tokens += len(encoding.encode(part["text"]))
                        except Exception as e: logger.debug(f"Tiktoken content encode error (text part): {e}")
            else:
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
                    num_tokens += 5
        if message.get("role") == "tool":
            if tool_call_id_val := message.get("tool_call_id"):
                try: num_tokens += len(encoding.encode(tool_call_id_val))
                except Exception as e: logger.debug(f"Tiktoken tool_call_id encode error (tool role): {e}")
    num_tokens += 3
    return num_tokens


class PathosInterface:
    def __init__(self, config: Config, ethos_core: EthosCore, logos_core: LogosCore, connection_manager: 'ConnectionManager'):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.connection_manager = connection_manager
        self.pathos_llm_config: Optional[LLMConfig] = config.get_llm_config('PATHOS') # Base config
        self._enhanced_pathos_llm_config: Optional[LLMConfig] = None # For auto-detected model
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
            if detected_model != original_model:
                logger.info(f"Enhanced PATHOS config: resolved '{original_model}' to '{detected_model}'")
        return self._enhanced_pathos_llm_config

    def set_tts_service(self, tts_service: 'ExternalTTSService'):
        self.eidos_tts_service_instance = tts_service
        logger.info("ExternalTTSService instance set in PathosInterface.")

    def set_audio_cache(self, cache: Dict[str, bytes], lock: Optional[asyncio.Lock] = None):
        self.audio_cache = cache
        self.audio_cache_lock = lock
        if self.audio_cache is not None: logger.info(f"PathosInterface: Audio cache and lock set.")
        else: logger.error("PathosInterface.set_audio_cache received a None cache object!")

    def get_static_system_prompt_content(self) -> Optional[str]:
        try:
            main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "Error: Main Pathos system prompt not found.")
            persona_directives_content = load_system_prompt("pathos_directives", "Default persona: You are a helpful AI named Pathos.")
            static_prompt = main_system_prompt_template.replace("{{PATHOS_PERSONA_DIRECTIVES_FROM_FILE}}", persona_directives_content)
            return static_prompt
        except Exception as e:
            logger.error(f"Error loading static system prompt content for cache warming: {e}", exc_info=True)
            return None

    def _update_active_user(self, new_user_id: str, set_by_statement: bool = False):
        normalized_id = (new_user_id.lower().strip().replace(" ", "_") if new_user_id else "unknown_user") or "unknown_user"
        if not normalized_id: 
            normalized_id = "unknown_user"
        if self.current_active_user_id != normalized_id:
            logger.info(f"PathosInterface: Active user changed from '{self.current_active_user_id}' to '{normalized_id}'.")
            self.current_active_user_id = normalized_id

    async def _build_main_llm_messages(
        self, user_id: str, user_input_text: str, history_context: List[Dict[str, Any]],
        image_data_b64: Optional[str] = None, vision_description_if_non_multimodal: Optional[str] = None,
        document_text: Optional[str] = None, force_web_search: bool = False, engaged_proactive_id: Optional[str] = None,
        system_provided_info: Optional[Dict[str, Any]] = None # For system-initiated info
    ) -> Tuple[List[Dict[str, Any]], List[MemoryEntry], Dict[str, float], Dict[str, float], int]:

        # 1. Load base templates
        main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "ERROR: Main Pathos system prompt template not found.")
        
        # NEW - directly use EthosCore's already loaded directives
        if self.ethos_core:
            persona_directives_content = "\n".join(self.ethos_core.get_persona_directives())
        else:
            persona_directives_content = "Default persona: You are Pathos." # Fallback

        # 2. Gather all dynamic context pieces
        current_mood_dict = self.ethos_core.get_current_mood() or {'valence': 0.0, 'arousal': 0.0}
        current_mood_str = f"Valence: {current_mood_dict['valence']:.2f}, Arousal: {current_mood_dict['arousal']:.2f}"
        current_activity_description = (await self.ethos_core.get_current_activity_description()) or "Currently idle."
        hexus_scores_dict = self.ethos_core.get_hexus_scores() or {} # Ensure this is fetched
        hexus_scores_str = ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_dict.items()]) or "N/A"
        user_profile_summary = (await self.ethos_core.get_user_profile_summary(user_id)) or "No specific profile information available."
        
        try:
            current_time_str = await self.logos_core.execute_get_time(location=None)
            if not isinstance(current_time_str, str) or "Error" in current_time_str or "error" in current_time_str.lower():
                 current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")
        except Exception: current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")
        
        memory_query_parts = [user_input_text]
        if document_text: memory_query_parts.append("[Document content attached]")
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
            else: vision_analysis_context_for_prompt = "Image provided, but no description generated."

        pathos_schedule_context = (await self.ethos_core.get_pathos_schedule_context_for_prompt()) or "No schedule info."
        pathos_aspirations_context = (await self.ethos_core.get_pathos_aspirations_context_for_prompt()) or "No aspirations info."
        todays_briefing_context = (await self.ethos_core.get_todays_briefing_context_for_prompt(user_id)) or "No briefing info."
        
        # Use the refined list of tools if you implemented that, otherwise full AVAILABLE_TOOLS
        tools_to_include_in_prompt = getattr(self, 'AVAILABLE_TOOLS_FOR_PATHOS_LLM', AVAILABLE_TOOLS)
        available_tools_json_for_prompt = json.dumps(tools_to_include_in_prompt, indent=2)

        # 3. Perform replacements in the main template
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
            final_system_prompt_content += "\n\nIMPORTANT_NOTE: User requested web search. Prioritize web_search tool."
        
        # Add system_provided_info if available (for weather, time, etc., handled by PathosInterface)
        if system_provided_info:
            final_system_prompt_content += "\n\n--- System Provided Information (for your awareness) ---"
            if info := system_provided_info.get("weather"):
                final_system_prompt_content += f"\nCurrent Weather Context: Location: {info.get('location')}, Conditions: {info.get('temperature')}{info.get('unit')} {info.get('description')}."
            if info := system_provided_info.get("current_time_info"):
                final_system_prompt_content += f"\nCurrent Time Context: {info}"
            # ... add other system_provided_info keys as needed ...
            final_system_prompt_content += "\n--- End System Provided Information ---"

        # 4. Assemble final messages list
        messages: List[Dict[str, Any]] = [{"role": "system", "content": final_system_prompt_content}]
        
        if history_context:
            messages.extend(history_context)
        
        user_message_content_parts: List[Dict[str, Any]] = []
        current_user_input_full = user_input_text
        if document_text:
            current_user_input_full += f"\n\n--- Attached Document Content ---\n{document_text}\n--- End of Document ---"
        user_message_content_parts.append({"type": "text", "text": current_user_input_full})
        
        if image_data_b64 and is_multimodal_llm:
            image_mime_type = "image/jpeg"
            if image_data_b64.startswith("iVBORw0KGgo"): image_mime_type = "image/png"
            elif image_data_b64.startswith("/9j/"): image_mime_type = "image/jpeg"
            user_message_content_parts.append({"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{image_data_b64}"}})
            logger.info(f"Added image data (MIME: {image_mime_type}) to PATHOS LLM message for user {user_id}.")
        
        final_user_content = user_message_content_parts[0]["text"] if len(user_message_content_parts) == 1 and user_message_content_parts[0]["type"] == "text" else user_message_content_parts
        messages.append({"role": "user", "content": final_user_content})
            
        estimated_tokens = -1
        if enhanced_config:
            model_name_for_tiktoken = enhanced_config.get('model_name_for_tiktoken', enhanced_config.get('model', 'cl100k_base'))
            estimated_tokens = estimate_tokens_for_messages(messages, model_name_for_tiktoken)
            logger.info(f"Estimated tokens for _build_main_llm_messages (user: {user_id}, model for tiktoken: {model_name_for_tiktoken}): {estimated_tokens}")
        
        logger.info(f"Built main LLM messages for user '{user_id}'. System prompt length: {len(final_system_prompt_content)}. Total messages: {len(messages)}")
        # For very detailed debugging of the final system prompt:
        # logger.debug(f"Full system prompt for user '{user_id}':\n{final_system_prompt_content}")
        
        return messages, retrieved_memories_raw, current_mood_dict, hexus_scores_dict, estimated_tokens

    async def _store_final_interaction(
        self, original_user_input: str, pathos_response: Optional[str], mood_at_response: Dict[str, float],
        retrieved_memories: List[MemoryEntry], full_history_for_pathos: List[Dict], error: bool = False,
        image_provided_this_turn: bool = False,
        vision_llm_output: Optional[str] = None, # <<< ENSURE THIS PARAMETER IS PRESENT
        is_proactive_turn: bool = False,
        forced_action: Optional[str] = None # Aligning with the call
        # raw_intention_from_core_llm: Optional[Dict[str, Any]] = None # This was correctly commented out
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
                tool_data_copy.setdefault("result_summary", "[No result processed in this history segment]"); tool_usage_summary.append(tool_data_copy)
        for item in tool_usage_summary: item.pop("id_from_map", None)

        input_summary = original_user_input[:250] + "..." if len(original_user_input) > 250 else original_user_input
        doc_included_in_input = "--- Uploaded Document Content ---" in original_user_input
        metadata = {
            "user_id": user_id_for_memory, "user_input_original_text": original_user_input,
            "image_provided_this_turn": image_provided_this_turn, "document_included_this_turn": doc_included_in_input,
            "vision_module_output_if_any": vision_llm_output, # Use the parameter here
            "main_llm_input_summary": input_summary,
            "pathos_final_response_text": pathos_response, "mood_at_response": mood_at_response,
            "retrieved_memory_ids": [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m],
            "tool_usage_summary_by_main_llm": tool_usage_summary or None,
            "is_proactive_turn": is_proactive_turn, "error_in_turn": error
        }
        if forced_action: metadata["forced_action"] = forced_action
        content_parts = [f"User ({user_id_for_memory}): {original_user_input}"]
        if image_provided_this_turn: content_parts.append("[Image provided by user.]")
        # Vision module output is not logged here as it's part of Pathos LLM's direct processing
        if doc_included_in_input: content_parts.append("[Document content included in input.]")
        content_parts.append(f"Pathos: {pathos_response if pathos_response else '[No textual response/Tool call]'}")
        if tool_usage_summary:
            tool_summary_str_parts = [f"{t.get('tool_name', 'unknown_tool')}(args={str(t.get('request_args', ''))[:50]}, result={t.get('result_summary', 'N/A')})" for t in tool_usage_summary]
            content_parts.append(f"Tools Used by Pathos: {', '.join(tool_summary_str_parts)}")
        if forced_action: content_parts.append(f"[Action '{forced_action}' was forced by user directive.]")
        if error: content_parts.append("[Error occurred during this turn.]")
        content_for_memory = "\n".join(content_parts)
        await self.ethos_core.add_memory_entry({"type": interaction_type, "content": content_for_memory, "metadata": metadata}, user_id_context=user_id_for_memory)
        logger.debug(f"Stored final interaction for user '{user_id_for_memory}'. Type: {interaction_type}.")

    async def _generate_proactive_message(self, user_id: str, proactive_type: str, context: Optional[Any] = None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        enhanced_config = await self._get_enhanced_pathos_llm_config()
        if not enhanced_config: logger.error("Cannot generate proactive message: Pathos LLM not configured."); return None, []
        logger.info(f"Attempting to generate proactive message content of type '{proactive_type}' for user '{user_id}'. Context: {str(context)[:100]}")
        prompt_for_llm = ""
        user_name_for_prompt = user_id
        if proactive_type == "greeting":
            time_of_day = context.get("time_of_day", "day") if isinstance(context, dict) else "day"
            prompt_for_llm = f"It's a new {time_of_day} for user '{user_name_for_prompt}'. Generate a VERY CASUAL and brief 'good {time_of_day}' greeting. Think like a relaxed friend. Examples: 'Hey {user_name_for_prompt}, what\\'s up?', 'Mornin {user_name_for_prompt}!', 'Afternoon! How\\'s it hanging?'"
        elif proactive_type == "offer_briefing_discussion" and context and isinstance(context, dict):
            full_briefing_content = context.get("full_briefing_content", "Today's news and weather information is available.")
            max_briefing_len_for_prompt = 1500
            truncated_briefing_for_prompt = full_briefing_content[:max_briefing_len_for_prompt] + "..." if len(full_briefing_content) > max_briefing_len_for_prompt else full_briefing_content
            prompt_for_llm = (f"User '{user_name_for_prompt}' can see the full daily briefing in their GUI panel. Here are the key contents of today's briefing for your reference:\n--- BEGIN BRIEFING CONTENT ---\n{truncated_briefing_for_prompt}\n--- END BRIEFING CONTENT ---\n\nCasually bring up ONE interesting point from the briefing content above to start a conversation, or ask if they have any questions about what they saw. Do NOT directly ask 'Do you want the briefing?'. Assume they can see it. Your response should be very short and conversational.")
        elif proactive_type == "offer_topic_continuation" and context and isinstance(context, dict) and context.get("topic"):
            recent_topic = context["topic"]
            prompt_for_llm = f"User '{user_name_for_prompt}' was recently discussing '{recent_topic}'. Generate a brief, CASUAL message offering to continue or asking for new thoughts. Examples: 'Yo {user_name_for_prompt}, we were chatting about {recent_topic} before. Still on your mind, or got something new cooking?', 'Hey, remember when we talked about {recent_topic}? Any new thoughts on that?'"
        elif proactive_type == "user_detected_in_office" and context and isinstance(context, dict):
            user_name_for_prompt_office = context.get("user_name", user_id)
            prompt_for_llm = f"You've just sensed that user '{user_name_for_prompt_office}' has entered the office. Greet them very CASUALY and see if they need anything. Examples: 'Hey {user_name_for_prompt_office}, what\\'s up?', 'Mornin\\' {user_name_for_prompt_office}! Anything I can do for you?'"
        elif proactive_type == "queued_discussion" and context and isinstance(context, dict):
            topic_content = context.get("topic_content", "something I was thinking about")
            reason = context.get("reason", "some previous thoughts")
            prompt_for_llm = f"You have a queued discussion point for user '{user_name_for_prompt}': '{topic_content}' (Reason: {reason}). Casually and naturally bring this up. Examples: 'Hey {user_name_for_prompt}, something crossed my mind from {reason}... {topic_content} What do you think?', 'I had a thought about {topic_content} earlier, mind if I share?'"
        else:
            logger.warning(f"Proactive message generation: No specific prompt logic for type '{proactive_type}'."); return None, []
        if not prompt_for_llm: logger.warning(f"Proactive message generation: No prompt_for_llm constructed for type '{proactive_type}'."); return None, []

        current_mood_pm = self.ethos_core.get_current_mood() or {'valence': 0.0, 'arousal': 0.0}
        hexus_scores_pm = self.ethos_core.get_hexus_scores() or {}
        system_prompt_content_parts_pm = self.ethos_core.get_persona_directives()[:5] + ["\n", f"You are generating a specific, brief, VERY CASUAL, and proactive message for user '{user_id}'.", f"Your current mood is valence {current_mood_pm['valence']:.2f}, arousal {current_mood_pm['arousal']:.2f}.", "(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_pm.items()]) + ")", "Be concise and natural, consistent with your friendly and relaxed persona. Use contractions.", "Your response should ONLY be the proactive message text. Do not include any other text or formatting."]
        system_prompt_content_content_pm = "\n".join(system_prompt_content_parts_pm)
        proactive_messages_for_llm = [{"role": "system", "content": system_prompt_content_content_pm}, {"role": "user", "content": prompt_for_llm}]
        proactive_text_content_accumulator = []; llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        
        async for item in self._call_llm_directly(llm_config_to_use=enhanced_config, messages=proactive_messages_for_llm, tools_definition=None, temperature_override=(enhanced_config.get('temperature', 0.7) if enhanced_config else 0.7), max_tokens_override=150, stream=True):
            if isinstance(item, str): proactive_text_content_accumulator.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "error_chunk": proactive_text_content_accumulator.append(item.get('content_error', "[LLM Error]")); llm_error_occurred = True; break
                elif item_type == "usage_chunk": llm_usage_data = item.get("usage")
        
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
                    audio_chunk_info_list.append({"url": f"/v1/tts/audio_chunk/{forced_chunk_id}", "sequence": tts_sequence_num_proactive, "text_for_indicator": sentence})
                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id, sequence_num=tts_sequence_num_proactive, forced_chunk_id=forced_chunk_id))
                    tts_sequence_num_proactive += 1
            return proactive_text_content, audio_chunk_info_list
        else: logger.warning(f"Proactive message generation for '{proactive_type}' failed. Content/Error: {proactive_text_content}"); return None, []

    async def send_sentence_to_tts_and_notify_client(self, sentence: str, user_id: str, sequence_num: int, forced_chunk_id: Optional[str] = None, chunk_id_prefix: str = "chat_tts_"):
        if not self.eidos_tts_service_instance or not self.connection_manager or self.audio_cache is None or not self.eidos_tts_service_instance.is_available():
            logger.error(f"TTS prerequisites missing for user {user_id}. TTS Service: {self.eidos_tts_service_instance}, ConnMgr: {self.connection_manager}, AudioCache: {self.audio_cache}, TTS Available: {self.eidos_tts_service_instance.is_available() if self.eidos_tts_service_instance else False}"); return
        log_prefix = f"FORCED_ID({forced_chunk_id})" if forced_chunk_id else f"PREFIX({chunk_id_prefix})"
        logger.debug(f"TTS_SEND ({user_id}, {sequence_num}, {log_prefix}): START for sentence: '{sentence[:30]}...'")
        audio_bytes: Optional[bytes] = None
        try: audio_bytes = await self.eidos_tts_service_instance.synthesize(text=sentence)
        except Exception as e_synth: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception during synthesize: {e_synth}", exc_info=True); return
        if audio_bytes:
            final_chunk_id = forced_chunk_id if forced_chunk_id else f"{chunk_id_prefix}{user_id}_{uuid.uuid4().hex[:10]}_{sequence_num}"
            logger.info(f"TTS_SEND ({user_id}, {sequence_num}): Audio bytes received. Caching with chunk_id: {final_chunk_id}.")
            cache_successful = False
            try:
                if self.audio_cache_lock:
                    async with self.audio_cache_lock:
                        if self.audio_cache is not None: self.audio_cache[final_chunk_id] = audio_bytes; cache_successful = True
                else:
                    if self.audio_cache is not None: self.audio_cache[final_chunk_id] = audio_bytes; cache_successful = True
            except Exception as e_cache: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception caching chunk {final_chunk_id}: {e_cache}", exc_info=True); return
            if not cache_successful: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Caching failed for chunk {final_chunk_id}."); return
            audio_url = f"/v1/tts/audio_chunk/{final_chunk_id}"
            is_proactive = True if forced_chunk_id and forced_chunk_id.startswith("proactive_tts_") else False
            ws_payload = {"type": "tts_audio_chunk_ready", "payload": {"url": audio_url, "sequence": sequence_num, "text_for_indicator": sentence, "chunk_id": final_chunk_id, "is_proactive_audio": is_proactive}}
            try: await self.connection_manager.send_personal_message(ws_payload, user_id); logger.info(f"TTS_SEND ({user_id}, {sequence_num}): Notification sent for chunk {final_chunk_id}.")
            except Exception as e_ws: logger.error(f"TTS_SEND ({user_id}, {sequence_num}): Exception sending WebSocket for chunk {final_chunk_id}: {e_ws}", exc_info=True)
        else: logger.warning(f"TTS_SEND ({user_id}, {sequence_num}): No audio bytes from synthesis for: '{sentence[:30]}...'.")
        logger.debug(f"TTS_SEND ({user_id}, {sequence_num}, {log_prefix}): END for sentence: '{sentence[:30]}...'")

    async def generate_response(
        self, user_input: str, image_data_b64: Optional[str] = None, document_text: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        response_metadata: Dict[str, Any] = {}
        req_meta = request_metadata if request_metadata is not None else {}
        user_id_for_response = req_meta.get('user_id', self.current_active_user_id)
        self._update_active_user(user_id_for_response)
        should_stream_tts_for_this_response = req_meta.get('auto_tts_enabled_for_response', False)
        response_metadata["tts_stream_attempted"] = should_stream_tts_for_this_response

        engaged_proactive_id = req_meta.get('engaged_proactive_id')
        if engaged_proactive_id: response_metadata["engaged_proactive_id"] = engaged_proactive_id
        
        logger.info(f"PathosInterface: Processing request for user '{user_id_for_response}' with Main PATHOS LLM.")
        
        # Vision processing is now handled by the main Pathos LLM if it's multimodal.
        # If not multimodal, a description would need to be generated by a separate vision service (e.g., LOGOS_VISION_CONTEXT)
        # and passed into _build_main_llm_messages via vision_description_if_non_multimodal.        # For this merge, we assume Pathos LLM can be multimodal.
        vision_description_for_non_multimodal_pathos: Optional[str] = None
        enhanced_pathos_config = await self._get_enhanced_pathos_llm_config()
        if image_data_b64 and enhanced_pathos_config and not enhanced_pathos_config.get('supports_vision', False) and self.logos_core:
            logger.info(f"Main Pathos LLM for user '{user_id_for_response}' is not multimodal. Requesting image description from LogosCore.")
            vision_prompt_for_logos = user_input if user_input.strip() else "Describe this image in detail."
            try:
                vision_description_for_non_multimodal_pathos = await self.logos_core.execute_describe_image(image_data_b64, vision_prompt_for_logos)
                if vision_description_for_non_multimodal_pathos and vision_description_for_non_multimodal_pathos.startswith('{"error":'):
                    logger.warning(f"LogosCore image description failed: {vision_description_for_non_multimodal_pathos}")
                    vision_description_for_non_multimodal_pathos = "[System note: Error processing image description.]"
            except Exception as e_vision_desc:
                logger.error(f"Error getting image description from LogosCore: {e_vision_desc}", exc_info=True)
                vision_description_for_non_multimodal_pathos = "[System note: Error obtaining image description.]"
        
        # Capture the estimated_prompt_tokens
        initial_llm_messages, retrieved_memories, current_mood, hexus_scores, estimated_prompt_tokens_for_response = await self._build_main_llm_messages(
            user_id=user_id_for_response,
            user_input_text=user_input,
            history_context=req_meta.get('conversation_history', []),
            image_data_b64=image_data_b64,
            vision_description_if_non_multimodal=vision_description_for_non_multimodal_pathos,
            document_text=document_text,
            force_web_search=req_meta.get('force_web_search_requested', False),
            engaged_proactive_id=req_meta.get('engaged_proactive_id'),
            system_provided_info=req_meta.get('system_provided_info') # Pass this if you implement pre-Pathos info gathering
        )
        
        full_history_for_interaction_log: List[Dict[str, Any]] = list(initial_llm_messages)
        llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        final_pathos_response_text = ""; audio_chunk_info_list: List[Dict[str, Any]] = []; tts_sequence_num = 0
        final_assistant_message_payload_for_response: Optional[Dict[str, Any]] = None

        if not enhanced_pathos_config:
            final_pathos_response_text = "I'm sorry, my internal configuration is incomplete and I cannot process your request at this time."
            llm_error_occurred = True; logger.error(f"PATHOS LLM not configured for user '{user_id_for_response}'.")
        else:
            current_conversation_messages = list(initial_llm_messages)
            async for item in self._call_llm_with_tools(
                llm_config_to_use=enhanced_pathos_config, messages=current_conversation_messages,
                tools_definition=AVAILABLE_TOOLS, user_id=user_id_for_response, stream_tool_calls=True,
                temperature_override=req_meta.get('temperature'),
                max_tokens_override=req_meta.get('max_tokens_override'),
                llm_provider_url_override=req_meta.get('llm_provider_url_override'),
                pathos_model_override=req_meta.get('pathos_model_override')
            ):
                item_type = item.get("type"); payload = item.get("payload")
                if item_type == "text_chunk" and isinstance(payload, str):
                    # Send text chunk via WebSocket immediately
                    await self.connection_manager.send_personal_message({"type": "text_chunk", "payload": {"text": payload, "sequence": tts_sequence_num}}, user_id_for_response)
                    # Accumulate for TTS sentence splitting
                    if should_stream_tts_for_this_response:
                        # This logic will be handled by the main loop after all text chunks are received
                        pass # Sentence splitting and TTS dispatch will happen after full text is accumulated
                elif item_type == "assistant_message_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "tool_result_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "final_assistant_message" and isinstance(payload, dict):
                    full_history_for_interaction_log.append(payload); final_assistant_message_payload_for_response = payload
                elif item_type == "error_chunk":
                    error_content = payload if isinstance(payload, str) else "Unknown LLM error"
                    llm_error_occurred = True; full_history_for_interaction_log.append({"role": "system", "content": f"LLM Error: {error_content}"})
                    logger.error(f"LLM error_chunk received: {error_content}"); break
                elif item_type == "usage_chunk": llm_usage_data = payload

            # Determine final_pathos_response_text from the accumulated chunks or final message
            if final_assistant_message_payload_for_response and isinstance(final_assistant_message_payload_for_response.get("content"), str):
                final_pathos_response_text = final_assistant_message_payload_for_response["content"]
            elif llm_error_occurred:
                last_error_msg = next((msg["content"] for msg in reversed(full_history_for_interaction_log) if msg.get("role") == "system" and "LLM Error" in msg.get("content","")), "I encountered an error.")
                final_pathos_response_text = f"[{last_error_msg.replace('LLM Error: ', '')}]" if "LLM Error" in last_error_msg else f"[Error: {last_error_msg}]"
            else: # Fallback if no explicit final message content
                accumulated_text_from_history = "".join([msg.get("content","") for msg in full_history_for_interaction_log if msg.get("role") == "assistant" and isinstance(msg.get("content"), str) and not msg.get("tool_calls")])
                final_pathos_response_text = accumulated_text_from_history.strip() or "I've processed your request."
                if not accumulated_text_from_history.strip():
                    logger.warning(f"No explicit final_assistant_message content. Using accumulated or default for '{user_id_for_response}'.")
            
            final_pathos_response_text = re.sub(r"<think>.*?</think>\s*", "", final_pathos_response_text, flags=re.DOTALL).strip()
            if not final_pathos_response_text and not llm_error_occurred and not (final_assistant_message_payload_for_response and final_assistant_message_payload_for_response.get("tool_calls")):
                 final_pathos_response_text = "Understood." # Default if truly empty and no tools

        # TTS processing for the complete final_pathos_response_text
        if final_pathos_response_text and should_stream_tts_for_this_response and self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
            sentences = re.split(r'(?<=[.!?])\s+', final_pathos_response_text.strip())
            for sentence_text in sentences:
                sentence = sentence_text.strip()
                if not sentence: continue
                forced_chunk_id = f"chat_tts_main_{user_id_for_response}_{uuid.uuid4().hex[:8]}_{tts_sequence_num}"
                # audio_chunk_info_list.append({"url": f"/v1/tts/audio_chunk/{forced_chunk_id}", "sequence": tts_sequence_num, "text_for_indicator": sentence}) # This was for non-streaming TTS
                asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id_for_response, sequence_num=tts_sequence_num, forced_chunk_id=forced_chunk_id))
                tts_sequence_num += 1
        
        self.ethos_core.update_mood_on_interaction(user_input, final_pathos_response_text, bool(image_data_b64), bool(document_text))
        
        tool_calls_for_metadata = final_assistant_message_payload_for_response.get("tool_calls") if final_assistant_message_payload_for_response else None
        response_metadata["tool_calls_from_pathos"] = tool_calls_for_metadata
        response_metadata["error_flag"] = llm_error_occurred
        response_metadata["mood_at_response"] = current_mood
        response_metadata["hexus_scores"] = hexus_scores
        response_metadata["retrieved_memory_ids"] = [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m]
        if llm_usage_data:
            response_metadata["prompt_tokens_from_llm"] = llm_usage_data.get("prompt_tokens")
            response_metadata["completion_tokens_from_llm"] = llm_usage_data.get("completion_tokens")
        # Use the captured estimated_prompt_tokens_for_response
        if estimated_prompt_tokens_for_response > 0:
            response_metadata["estimated_prompt_tokens"] = estimated_prompt_tokens_for_response


        await self._store_final_interaction(
            original_user_input=user_input,
            pathos_response=final_pathos_response_text,
            mood_at_response=current_mood, # Make sure current_mood is defined in this scope
            retrieved_memories=retrieved_memories, # Make sure retrieved_memories is defined
            full_history_for_pathos=full_history_for_interaction_log, # Make sure this is defined
            error=llm_error_occurred, # Make sure this is defined
            image_provided_this_turn=bool(image_data_b64),
            vision_llm_output=vision_description_for_non_multimodal_pathos,
            is_proactive_turn=bool(req_meta.get('engaged_proactive_id')), # Use engaged_proactive_id from req_meta
            forced_action=req_meta.get('force_web_search_requested')
        )
        if document_text and self.logos_core:
             asyncio.create_task(self.logos_core.add_document_to_rag(extracted_text=document_text, filename="uploaded_via_chat", user_id=user_id_for_response), name=f"AddDocToRAG_{user_id_for_response}_{uuid.uuid4().hex[:4]}")

        is_error_response = llm_error_occurred or (not final_pathos_response_text and not tool_calls_for_metadata)
        
        # The main HTTP response does not stream text chunks anymore.
        # It sends the full text response at the end.
        # TTS audio chunks are sent via WebSocket.
        
        return {
            "success": not is_error_response,
            "content": final_pathos_response_text, # Full text
            "metadata": response_metadata
        }

    async def _call_llm_with_tools(
        self, llm_config_to_use: LLMConfig, messages: List[Dict[str, Any]], tools_definition: List[Dict[str, Any]],
        user_id: str, stream_tool_calls: bool = False, # stream_tool_calls for yielding tool call info as it happens
        temperature_override: Optional[float] = None, max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None, pathos_model_override: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        current_messages = list(messages)
        max_iterations = llm_config_to_use.get('max_tool_iterations', 3)
        for i in range(max_iterations):
            logger.info(f"LLM tool iteration {i + 1}/{max_iterations} for user '{user_id}'. Message count: {len(current_messages)}")
            accumulated_content_chunks: List[str] = []
            llm_had_tool_calls_this_iter = False
            llm_usage_this_iter: Optional[Dict[str, Any]] = None
            assistant_msg_obj_this_iter: Optional[Dict[str, Any]] = None

            async for llm_item in self._call_llm_directly(
                llm_config_to_use=llm_config_to_use, messages=current_messages,
                tools_definition=tools_definition, stream=True, # Always stream from LLM API
                temperature_override=temperature_override, max_tokens_override=max_tokens_override,
                llm_provider_url_override=llm_provider_url_override, pathos_model_override=pathos_model_override
            ):
                if isinstance(llm_item, str): # Raw text delta
                    if not llm_had_tool_calls_this_iter: # Only accumulate/yield text if no tools are being called in this iter
                        accumulated_content_chunks.append(llm_item)
                        if stream_tool_calls: yield {"type": "text_chunk", "payload": llm_item}
                elif isinstance(llm_item, dict):
                    item_type = llm_item.get("type"); payload = llm_item.get("payload")
                    if item_type == "tool_calls_chunk" and isinstance(payload, dict): # This means LLM decided to call tools
                        llm_had_tool_calls_this_iter = True
                        assistant_msg_obj_this_iter = payload # Store the full assistant message with tool_calls
                        accumulated_content_chunks = [] # Clear any text if tools are called
                        # Do not yield tool_calls_chunk here yet, wait for all parts
                    elif item_type == "usage_chunk": llm_usage_this_iter = llm_item.get("usage")
                    elif item_type == "error_chunk":
                        yield llm_item; return # Propagate error and stop

            if llm_had_tool_calls_this_iter and assistant_msg_obj_this_iter:
                current_messages.append(assistant_msg_obj_this_iter) # Add assistant's tool call message to history
                yield {"type": "assistant_message_chunk", "payload": assistant_msg_obj_this_iter} # Yield the assistant's decision to call tools
                
                actual_tool_calls = assistant_msg_obj_this_iter.get("tool_calls", [])
                if not actual_tool_calls: # Should not happen if llm_had_tool_calls_this_iter is true
                    final_text_on_bad_tool = "".join(accumulated_content_chunks).strip() or "Tool call error indicated but no tools found."
                    if stream_tool_calls and not accumulated_content_chunks and final_text_on_bad_tool: yield {"type": "text_chunk", "payload": final_text_on_bad_tool}
                    final_msg_obj = {"role": "assistant", "content": final_text_on_bad_tool}
                    current_messages.append(final_msg_obj); yield {"type": "final_assistant_message", "payload": final_msg_obj}
                    if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                    return

                tool_results = await self._execute_tools(actual_tool_calls, user_id)
                for res_msg in tool_results: current_messages.append(res_msg); yield {"type": "tool_result_chunk", "payload": res_msg}
                
                if i == max_iterations - 1: # Max iterations reached, force final response
                    final_prompt_msgs_max = list(current_messages)
                    final_prompt_msgs_max.append({"role": "user", "content": "Max tool uses reached. Provide final answer now."})
                    final_text_acc_max = []
                    final_usage_max_iter: Optional[Dict[str, Any]] = None
                    async for item_max in self._call_llm_directly(llm_config_to_use, final_prompt_msgs_max, None, True, # No tools for final summary
                        temperature_override=temperature_override, max_tokens_override=max_tokens_override,
                        llm_provider_url_override=llm_provider_url_override, pathos_model_override=pathos_model_override):
                        if isinstance(item_max, str): final_text_acc_max.append(item_max);
                        if stream_tool_calls and isinstance(item_max, str): yield {"type": "text_chunk", "payload": item_max}
                        elif isinstance(item_max, dict) and item_max.get("type") == "error_chunk": yield item_max; return
                        elif isinstance(item_max, dict) and item_max.get("type") == "usage_chunk": final_usage_max_iter = item_max.get("usage")

                    final_text_max = "".join(final_text_acc_max).strip() or "Tool limit reached; processing complete."
                    final_msg_obj_max = {"role": "assistant", "content": final_text_max}
                    current_messages.append(final_msg_obj_max); yield {"type": "final_assistant_message", "payload": final_msg_obj_max}
                    if final_usage_max_iter: yield {"type": "usage_chunk", "payload": final_usage_max_iter}
                    elif llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter} # Fallback to previous iter usage
                    return
            else: # No tool calls this iteration, should be a direct text response
                final_text_response = "".join(accumulated_content_chunks).strip()
                if not final_text_response:
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
                elif function_name == "add_pathos_event": # New tool
                    event_id = await self.ethos_core.chronos_bridge_add_event(
                        title=function_args.get("title"), start_date_str=function_args.get("start_date"),
                        end_date_str=function_args.get("end_date"), event_type_str=function_args.get("event_type"),
                        description=function_args.get("description"), location=function_args.get("location"),
                        activity_theme=function_args.get("activity_theme"),
                        planned_sites_or_tasks=function_args.get("planned_sites_or_tasks"),
                        user_id_for_event=PATHOS_USER_ID # Event is for Pathos
                    )
                    tool_response_content_str = f"Event '{function_args.get('title')}' scheduled for Pathos with ID {event_id}." if event_id else f"Failed to schedule event '{function_args.get('title')}'."
                elif function_name == "initiate_simulated_interaction": tool_response_content_str = json.dumps(await simulation_module.initiate_simulated_interaction(function_args.get("npc_name"), function_args.get("npc_role"), function_args.get("npc_description"), function_args.get("initial_context"), function_args.get("pathos_opening_statement")))
                elif function_name == "send_message_to_simulated_npc": tool_response_content_str = json.dumps(await simulation_module.send_message_to_simulated_npc(function_args.get("message_to_npc")))
                elif function_name == "end_simulated_interaction": tool_response_content_str = json.dumps(await simulation_module.end_simulated_interaction())
                else: tool_response_content_str = json.dumps({"error": f"Tool '{function_name}' not implemented."})
            except Exception as e: logger.error(f"Error executing tool {function_name} for user '{user_id}': {e}", exc_info=True); tool_response_content_str = json.dumps({"error": f"Error in tool {function_name}: {str(e)}"})
            tool_results_messages.append({"tool_call_id": tool_call_id, "role": "tool", "name": function_name, "content": tool_response_content_str})
        return tool_results_messages

    async def _call_llm_directly(
        self, llm_config_to_use: LLMConfig, messages: List[Dict[str, Any]],
        tools_definition: Optional[List[Dict[str, Any]]] = None,
        temperature_override: Optional[float] = None, max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None, pathos_model_override: Optional[str] = None,
        stream: bool = False
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        if not llm_config_to_use:
            yield {"type": "error_chunk", "content_error": "LLM configuration missing."}; return
        
        api_key = llm_config_to_use.get('api_key')
        base_url_from_config = llm_provider_url_override or llm_config_to_use.get('base_url') or llm_config_to_use.get('url')
        model_name = pathos_model_override or llm_config_to_use.get('model_name') or llm_config_to_use.get('model')
        
        if not api_key or not base_url_from_config or not model_name:
            yield {"type": "error_chunk", "content_error": "LLM configuration incomplete (key, URL, or model)."}; return
        
        request_url = f"{str(base_url_from_config).rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if api_key.lower() in ['lm-studio', 'ollama', 'vllm', 'none', '']: # No auth header for these
            headers.pop("Authorization", None)

        payload: Dict[str, Any] = {"model": model_name, "messages": messages, "stream": stream}
        if tools_definition: payload["tools"] = tools_definition; payload["tool_choice"] = "auto"
        
        final_temp = temperature_override if temperature_override is not None else llm_config_to_use.get('temperature', 0.7)
        payload["temperature"] = float(final_temp) if final_temp is not None else 0.7

        final_max_tokens = max_tokens_override if max_tokens_override is not None else llm_config_to_use.get('max_tokens')
        if final_max_tokens is not None: payload["max_tokens"] = int(final_max_tokens)
        
        logger.debug(f"Final LLM Payload for {request_url}: {json.dumps(payload, indent=2)}")

        try:
            response = await self.http_client.post(request_url, headers=headers, json=payload)
            if response.status_code == 200:
                if stream:
                    accumulated_tool_calls_stream: List[Dict[str, Any]] = []
                    async for line_bytes in response.aiter_bytes():
                        line = line_bytes.decode('utf-8').strip()
                        if not line: continue
                        if not line.startswith("data:") and line.startswith('{"error":'):
                            try: error_data = json.loads(line); error_msg = error_data.get('error', 'Unknown stream error'); yield {"type": "error_chunk", "content_error": f"LLM Stream Error: {error_msg}"}; return
                            except json.JSONDecodeError: logger.warning(f"Unexpected non-SSE line: {line}"); continue
                        if line.startswith("data: "):
                            line_content = line[len("data: "):].strip()
                            if line_content == "[DONE]":
                                if accumulated_tool_calls_stream: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": accumulated_tool_calls_stream}}
                                break
                            try:
                                chunk = json.loads(line_content)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                                if content_delta := delta.get("content"): yield content_delta
                                if tool_calls_delta := delta.get("tool_calls"):
                                    for tc_item in tool_calls_delta:
                                        idx = tc_item.get("index", 0) # Default to 0 if index missing
                                        while len(accumulated_tool_calls_stream) <= idx: accumulated_tool_calls_stream.append({"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                                        if "id" in tc_item: accumulated_tool_calls_stream[idx]["id"] = tc_item["id"]
                                        if func_delta := tc_item.get("function"):
                                            if "name" in func_delta: accumulated_tool_calls_stream[idx]["function"]["name"] += func_delta["name"]
                                            if "arguments" in func_delta: accumulated_tool_calls_stream[idx]["function"]["arguments"] += func_delta["arguments"]
                                if finish_reason == "tool_calls":
                                    final_tools = delta.get("tool_calls") or accumulated_tool_calls_stream
                                    if final_tools: yield {"type": "tool_calls_chunk", "payload": {"role": "assistant", "tool_calls": final_tools}}
                                    accumulated_tool_calls_stream = []
                                if usage := chunk.get("usage"): yield {"type": "usage_chunk", "usage": usage}
                            except json.JSONDecodeError: yield {"type": "error_chunk", "content_error": f"Stream JSON decode error: {line_content}"}
                else: # Non-streaming
                    full_response_json = await response.json()
                    message_obj = full_response_json.get("choices", [{}])[0].get("message", {})
                    if message_obj.get("tool_calls"): yield {"type": "tool_calls_chunk", "payload": message_obj}
                    elif message_obj.get("content"): yield message_obj["content"]
                    else: yield ""
                    if usage_data := full_response_json.get("usage"): yield {"type": "usage_chunk", "usage": usage_data}
            else:
                error_content = await response.text(); yield {"type": "error_chunk", "content_error": f"LLM API Error {response.status_code}: {error_content[:200]}"}
        except httpx.ReadTimeout: yield {"type": "error_chunk", "content_error": "LLM API request timed out."}
        except httpx.RequestError as e_req: yield {"type": "error_chunk", "content_error": f"LLM request error: {str(e_req)}"}
        except Exception as e: yield {"type": "error_chunk", "content_error": f"Unexpected error in LLM call: {str(e)}"}

    async def process_feedback(self, feedback_data: Dict[str, Any]):
        if not self.config.ENABLE_LEARNING_FROM_FEEDBACK: logger.debug("Feedback processing skipped."); return
        required_keys = ['user_id', 'last_user_input', 'last_pathos_response', 'feedback_type']
        if not all(key in feedback_data for key in required_keys): logger.warning(f"Feedback data missing keys. Skipping."); return
        if not isinstance(feedback_data.get('user_id'), str) or not isinstance(feedback_data.get('feedback_type'), str):
            logger.warning("Feedback data has invalid types. Skipping."); return
        feedback_user_id = feedback_data.get('user_id', self.current_active_user_id)
        logger.info(f"PathosInterface processing feedback for user '{feedback_user_id}': Type '{feedback_data.get('feedback_type')}'.")
        memory_metadata = { "user_id": feedback_user_id, "source": feedback_data.get('source', 'api_feedback_endpoint'), "feedback_timestamp_received_by_api": datetime.now(timezone.utc).isoformat(), "processed_by_reflection": False, **feedback_data }
        feedback_content_str = json.dumps(feedback_data)
        await self.ethos_core.add_memory_entry( {"type": "feedback", "content": feedback_content_str, "metadata": memory_metadata, "salience": 1.2 }, user_id_context=feedback_user_id )
        if self.config.ENABLE_MOOD_SIMULATION: mood_update_payload = {"feedback_type": feedback_data.get("feedback_type"), "rating": feedback_data.get("rating")}; await self.ethos_core.update_mood_state('feedback', mood_update_payload)

    async def close(self):
        try:
            if hasattr(self, 'http_client') and self.http_client and not self.http_client.is_closed:
                await self.http_client.aclose()
                logger.info("PathosInterface: HTTP client closed.")
        except Exception as e: logger.error(f"Error closing PathosInterface resources: {e}", exc_info=True)
        logger.info("PathosInterface closed.")
