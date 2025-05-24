print("DEBUG: PATHOS_INTERFACE.PY IS BEING LOADED (NEWEST VERSION CHECK)") # For load verification

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Literal, Union, AsyncGenerator, Tuple
import re
import math
import json
from pathlib import Path
import uuid
import httpx
import random

from eidos_agent.core.config import Config, LLMConfig
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger
from eidos_agent.core.api_models import ChatMessage

try:
    import tiktoken
except ImportError:
    tiktoken = None
    print("Warning: tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken")

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.modules.oneiros_module import OneirosModule
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
GET_NEWS_HEADLINES_TOOL_DEFINITION = [ { "type": "function", "function": { "name": "get_news_headlines", "description": "Gets the top news headlines from configured news sources. Use this specifically when the user asks for current news headlines.", "parameters": { "type": "object", "properties": {}, "required": [] } } } ]
AVAILABLE_TOOLS = ( GET_CURRENT_TIME_TOOL_DEFINITION + WEB_SEARCH_TOOL_DEFINITION + MATH_CALCULATOR_TOOL_DEFINITION + GET_WEATHER_TOOL_DEFINITION + STORE_USER_FACT_TOOL_DEFINITION + PERFORM_DEEP_RESEARCH_TOOL_DEFINITION + STORE_WORLD_FACT_TOOL_DEFINITION + GET_NEWS_HEADLINES_TOOL_DEFINITION )

def estimate_tokens_for_messages(messages: List[Dict[str, Any]], model_name_for_tiktoken: str = "cl100k_base") -> int:
    if tiktoken is None:
        logger.warning("tiktoken not available, cannot estimate tokens.")
        return -1
    try:
        encoding = tiktoken.get_encoding(model_name_for_tiktoken)
    except Exception:
        logger.warning(f"Tiktoken: Encoding '{model_name_for_tiktoken}' not found. Using cl100k_base.")
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception as e_enc:
            logger.error(f"Tiktoken: Failed to get cl100k_base encoding: {e_enc}")
            return -1

    num_tokens = 0
    tokens_per_message_overhead = 3  # Base overhead for each message structure
    tokens_for_name_if_present = 1   # Additional token if 'name' field is in the message

    for message in messages:
        num_tokens += tokens_per_message_overhead
        if message.get("name"):  # For 'tool' role's 'name' or a named 'assistant'
            num_tokens += tokens_for_name_if_present

        content = message.get("content")
        if content:
            if isinstance(content, str):
                try:
                    num_tokens += len(encoding.encode(content))
                except Exception as e:
                    logger.warning(f"Tiktoken content encode error (str): {e}")
            elif isinstance(content, list):  # For multimodal content (e.g., text and image parts)
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                        try:
                            num_tokens += len(encoding.encode(part["text"]))
                        except Exception as e:
                            logger.warning(f"Tiktoken content encode error (text part): {e}")
                    # Note: Image tokens are not estimated by tiktoken for text models.
            else: # Fallback for unexpected content types
                try:
                    num_tokens += len(encoding.encode(str(content)))
                except Exception as e:
                    logger.warning(f"Tiktoken content encode error (other type): {e}")

        tool_calls = message.get("tool_calls") # For an assistant message requesting tool calls
        if tool_calls and isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict) and "function" in tool_call:
                    # Account for the ID of the tool call
                    tc_id = tool_call.get("id")
                    if tc_id:
                        try:
                            num_tokens += len(encoding.encode(tc_id))
                        except Exception as e:
                            logger.warning(f"Tiktoken tool_call.id encode error: {e}")

                    function_data = tool_call.get("function", {})
                    name = function_data.get("name")
                    arguments = function_data.get("arguments")
                    try:
                        if name:
                            num_tokens += len(encoding.encode(name))
                        if arguments and isinstance(arguments, str):
                            num_tokens += len(encoding.encode(arguments))
                    except Exception as e:
                        logger.warning(f"Tiktoken tool data encode error: {e}")
                    
                    # Approximate structural overhead for keys per tool_call
                    # (e.g., "id", "type", "function", and inner "name", "arguments" keys)
                    # This is an estimate; OpenAI's exact internal counting can vary.
                    # 5 tokens for the 5 main keys is a common heuristic.
                    num_tokens += 5 

        # For a 'tool' role message (result from a tool)
        if message.get("role") == "tool":
            tool_call_id_val = message.get("tool_call_id")
            if tool_call_id_val:
                try:
                    num_tokens += len(encoding.encode(tool_call_id_val))
                except Exception as e:
                    logger.warning(f"Tiktoken tool_call_id encode error (tool role): {e}")
            # The 'name' (function name) of a tool message is handled by `if message.get("name")` above.
            # The 'content' (result) of a tool message is handled by `if content:` block above.

    num_tokens += 3  # Every reply is primed with something like <|start|>assistant
    return num_tokens


class PathosInterface:
    print("DEBUG: PathosInterface CLASS DEFINITION IS BEING PARSED") # For load verification

    def __init__(self, config: Config, ethos_core: EthosCore, logos_core: LogosCore, connection_manager: 'ConnectionManager'):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.connection_manager = connection_manager
        self.pathos_llm_config: Optional[LLMConfig] = config.get_llm_config('PATHOS')
        self.current_active_user_id: str = "default_user"
        self.last_user_set_by_statement: bool = False

        self.eidos_tts_service_instance: Optional['ExternalTTSService'] = None
        self.audio_cache: Optional[Dict[str, bytes]] = None
        self.audio_cache_lock: Optional[asyncio.Lock] = None

        timeout_seconds_cfg = self.pathos_llm_config.get('timeout', 300) if self.pathos_llm_config else 300
        try: timeout_value = float(timeout_seconds_cfg)
        except (ValueError, TypeError): timeout_value = 300.0; logger.warning(f"Invalid Pathos LLM timeout '{timeout_seconds_cfg}', defaulting to {timeout_value}s.")
        self.http_client = httpx.AsyncClient(timeout=timeout_value)
        logger.info("PathosInterface initialized.")

    def set_tts_service(self, tts_service: 'ExternalTTSService'):
        self.eidos_tts_service_instance = tts_service
        logger.info("ExternalTTSService instance set in PathosInterface.")

    def set_audio_cache(self, cache: Dict[str, bytes], lock: Optional[asyncio.Lock] = None):
        self.audio_cache = cache
        self.audio_cache_lock = lock
        if self.audio_cache is not None:
            logger.info(f"PathosInterface: Audio cache (ID: {id(self.audio_cache)}) and lock (ID: {id(self.audio_cache_lock) if self.audio_cache_lock else 'None'}) set.")
        else:
            logger.error("PathosInterface.set_audio_cache received a None cache object!")

    def _update_active_user(self, new_user_id: str, set_by_statement: bool = False):
        normalized_id = (new_user_id.lower().strip().replace(" ", "_") if new_user_id else "unknown_user") or "unknown_user"
        if not normalized_id: normalized_id = "unknown_user"
        if self.current_active_user_id != normalized_id:
            logger.info(f"Active user: '{self.current_active_user_id}' -> '{normalized_id}'. By statement: {set_by_statement}")
            self.current_active_user_id = normalized_id
        if set_by_statement: self.last_user_set_by_statement = True

    def get_static_system_prompt_content(self) -> str:
        static_system_prompt_parts = []
        if not self.ethos_core: logger.error("get_static_system_prompt_content: EthosCore not available!"); return "You are a helpful assistant."
        persona_directives = self.ethos_core.get_persona_directives()
        if persona_directives: static_system_prompt_parts.extend(persona_directives); static_system_prompt_parts.append("\n")
        static_system_prompt_parts.extend([ "--- CRITICAL INSTRUCTION: TOOL USE ---", "Your PRIMARY task is to fulfill the user's request.", "If the user's request clearly requires ANY of the AVAILABLE TOOLS, you MUST output ONLY the tool_calls structure for the necessary tool(s) immediately.", "DO NOT provide any conversational text or acknowledgement if a tool call is required.", "If multiple tools are needed for the request (e.g., 'time and weather'), output ALL required tool_calls in a single response.", "Only provide a conversational text response if NO tool is needed, or in a subsequent turn AFTER tool results have been provided to you.", "Strictly adhere to this: Tool needed -> Output ONLY tool_calls. No tool needed -> Output conversational text.", "--- END CRITICAL INSTRUCTION ---\n" ])
        content = "\n".join(filter(None, static_system_prompt_parts)).strip()
        return content if content else "You are a helpful assistant."

    async def _generate_proactive_message(self, user_id: str, proactive_type: str, context: Optional[Any] = None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        if not self.pathos_llm_config: logger.error("Cannot generate proactive message: Pathos LLM not configured."); return None, []
        logger.info(f"Attempting to generate proactive message content of type '{proactive_type}' for user '{user_id}'. Context: {str(context)[:100]}")
        prompt_for_llm = ""
        user_name_for_prompt = user_id
        if proactive_type == "greeting": time_of_day = context.get("time_of_day", "day") if isinstance(context, dict) else "day"; prompt_for_llm = f"It's a new {time_of_day} for user '{user_name_for_prompt}'. Generate a VERY CASUAL and brief 'good {time_of_day}' greeting. Think like a relaxed friend. Examples: 'Hey {user_name_for_prompt}, what's up?', 'Mornin {user_name_for_prompt}!', 'Afternoon! How's it hanging?'"
        elif proactive_type == "offer_briefing_discussion" and context and isinstance(context, dict): full_briefing_content = context.get("full_briefing_content", "Today's news and weather information is available."); max_briefing_len_for_prompt = 1500; truncated_briefing_for_prompt = full_briefing_content[:max_briefing_len_for_prompt] + "..." if len(full_briefing_content) > max_briefing_len_for_prompt else full_briefing_content; prompt_for_llm = ( f"User '{user_name_for_prompt}' can see the full daily briefing in their GUI panel. " f"Here are the key contents of today's briefing for your reference:\n" f"--- BEGIN BRIEFING CONTENT ---\n{truncated_briefing_for_prompt}\n--- END BRIEFING CONTENT ---\n\n" "Casually bring up ONE interesting point from the briefing content above to start a conversation, or ask if they have any questions about what they saw. " "Do NOT directly ask 'Do you want the briefing?'. Assume they can see it. " "Your response should be very short and conversational. " )
        elif proactive_type == "offer_topic_continuation" and context and isinstance(context, dict) and context.get("topic"): recent_topic = context["topic"]; prompt_for_llm = f"User '{user_name_for_prompt}' was recently discussing '{recent_topic}'. Generate a brief, CASUAL message offering to continue or asking for new thoughts. Examples: 'Yo {user_name_for_prompt}, we were chatting about {recent_topic} before. Still on your mind, or got something new cooking?', 'Hey, remember when we talked about {recent_topic}? Any new thoughts on that?'"
        elif proactive_type == "user_detected_in_office" and context and isinstance(context, dict): user_name_for_prompt_office = context.get("user_name", user_id); prompt_for_llm = f"You've just sensed that user '{user_name_for_prompt_office}' has entered the office. Greet them very CASUALY and see if they need anything. Examples: 'Hey {user_name_for_prompt_office}, what's up?', 'Mornin' {user_name_for_prompt_office}! Anything I can do for you?'"
        elif proactive_type == "queued_discussion" and context and isinstance(context, dict): topic_content = context.get("topic_content", "something I was thinking about"); reason = context.get("reason", "some previous thoughts"); prompt_for_llm = f"You have a queued discussion point for user '{user_name_for_prompt}': '{topic_content}' (Reason: {reason}). Casually and naturally bring this up. Examples: 'Hey {user_name_for_prompt}, something crossed my mind from {reason}... {topic_content} What do you think?', 'I had a thought about {topic_content} earlier, mind if I share?'"
        if not prompt_for_llm: logger.warning(f"Proactive message generation: No prompt_for_llm for type '{proactive_type}'."); return None, []

        current_mood_pm = self.ethos_core.get_current_mood(); hexus_scores_pm = self.ethos_core.get_hexus_scores(); system_prompt_content_parts_pm = []; system_prompt_content_parts_pm.extend(self.ethos_core.get_persona_directives()); system_prompt_content_parts_pm.append("\n"); system_prompt_content_parts_pm.append(f"You are generating a specific, brief, VERY CASUAL, and proactive message for user '{user_id}'."); system_prompt_content_parts_pm.append(f"Your current mood is valence {current_mood_pm['valence']:.2f}, arousal {current_mood_pm['arousal']:.2f}."); system_prompt_content_parts_pm.append("(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_pm.items()]) + ")"); system_prompt_content_parts_pm.append("Be concise and natural, consistent with your friendly and relaxed persona. Use contractions."); system_prompt_content_parts_pm.append("Your response should ONLY be the proactive message text. Do not include any other text or formatting."); system_prompt_content_content_pm = "\n".join(system_prompt_content_parts_pm)
        proactive_messages_for_llm = [{"role": "system", "content": system_prompt_content_content_pm}, {"role": "user", "content": prompt_for_llm}]

        proactive_text_content_accumulator = []; llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        async for item in self._call_pathos_llm(messages=proactive_messages_for_llm, tools_definition=None, temperature=self.pathos_llm_config.get('temperature', 0.7) if self.pathos_llm_config else 0.7, max_tokens_override=150, stream=True):
            if isinstance(item, str): proactive_text_content_accumulator.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "error_chunk": error_msg = item.get('content_error', "[LLM Error]"); proactive_text_content_accumulator.append(error_msg); llm_error_occurred = True; break
                elif item_type == "usage_chunk": llm_usage_data = item.get("usage")
        proactive_text_content = "".join(proactive_text_content_accumulator).strip()
        if llm_usage_data: logger.info(f"LLM usage for proactive message generation: {llm_usage_data}")

        if proactive_text_content and not llm_error_occurred:
            proactive_text_content = re.sub(r"<think>.*?</think>\s*", "", proactive_text_content, flags=re.DOTALL).strip()
            if not proactive_text_content: logger.warning(f"Proactive message for '{proactive_type}' empty after stripping think tags."); return None, []
            logger.info(f"Generated proactive message text for '{proactive_type}': {proactive_text_content[:100]}...")

            audio_chunk_info_list: List[Dict[str, Any]] = []
            tts_sequence_num_proactive = 0
            if self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
                sentences = re.split(r'(?<=[.!?])\s+', proactive_text_content.strip())
                for sentence_text in sentences:
                    sentence = sentence_text.strip()
                    if not sentence: continue

                    forced_chunk_id = f"proactive_tts_{user_id}_{uuid.uuid4().hex[:10]}_{tts_sequence_num_proactive}"
                    audio_url = f"/v1/tts/audio_chunk/{forced_chunk_id}"
                    audio_chunk_info_list.append({"url": audio_url, "sequence": tts_sequence_num_proactive, "text_for_indicator": sentence})
                    asyncio.create_task(
                        self.send_sentence_to_tts_and_notify_client(
                            sentence=sentence, user_id=user_id, sequence_num=tts_sequence_num_proactive,
                            forced_chunk_id=forced_chunk_id
                        ))
                    tts_sequence_num_proactive += 1
            return proactive_text_content, audio_chunk_info_list
        else:
            logger.warning(f"Proactive message generation for '{proactive_type}' failed. Content/Error: {proactive_text_content}")
            return None, []

    async def send_sentence_to_tts_and_notify_client(self, sentence: str, user_id: str, sequence_num: int,
                                                     forced_chunk_id: Optional[str] = None,
                                                     chunk_id_prefix: str = "chat_tts_"):
        if not self.eidos_tts_service_instance: logger.error(f"PathosInterface: ExternalTTSService not set for user {user_id}."); return
        if not self.connection_manager: logger.error(f"PathosInterface: ConnectionManager not set for user {user_id}."); return
        if self.audio_cache is None: logger.error(f"PathosInterface: Audio cache not set for user {user_id}."); return
        if not self.eidos_tts_service_instance.is_available(): logger.warning(f"ExternalTTSService not available for user {user_id}."); return

        log_prefix_indicator = f"FORCED_ID({forced_chunk_id})" if forced_chunk_id else f"PREFIX({chunk_id_prefix})"
        logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}, {log_prefix_indicator}): START for sentence: '{sentence[:30]}...'")

        audio_bytes: Optional[bytes] = None
        try:
            audio_bytes = await self.eidos_tts_service_instance.synthesize(text=sentence)
            logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Synthesis call returned. audio_bytes is {'None' if audio_bytes is None else f'{len(audio_bytes)} bytes'}.")
        except Exception as e_synth:
            logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Exception during synthesize: {e_synth}", exc_info=True)
            return

        if audio_bytes:
            final_chunk_id = forced_chunk_id if forced_chunk_id else f"{chunk_id_prefix}{user_id}_{uuid.uuid4().hex[:10]}_{sequence_num}"
            logger.info(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Audio bytes received. Caching with chunk_id: {final_chunk_id}.")

            cache_successful = False
            try:
                logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Caching to self.audio_cache. ID of self.audio_cache: {id(self.audio_cache) if self.audio_cache is not None else 'None'}")
                if self.audio_cache_lock:
                    logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Acquiring audio_cache_lock for chunk {final_chunk_id}.")
                    async with self.audio_cache_lock:
                        logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): audio_cache_lock acquired for chunk {final_chunk_id}.")
                        if self.audio_cache is not None: self.audio_cache[final_chunk_id] = audio_bytes; cache_successful = True
                        else: logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Audio cache is None (with lock).")
                    logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): audio_cache_lock released for chunk {final_chunk_id}.")
                else:
                    logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): No audio_cache_lock. Caching chunk {final_chunk_id} directly.")
                    if self.audio_cache is not None: self.audio_cache[final_chunk_id] = audio_bytes; cache_successful = True
                    else: logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Audio cache is None (no lock).")
            except Exception as e_cache: logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Exception during caching chunk {final_chunk_id}: {e_cache}", exc_info=True); return

            if not cache_successful: logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Caching failed for chunk {final_chunk_id}."); return

            logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Audio chunk '{final_chunk_id}' cached. Preparing to notify user.")
            audio_url = f"/v1/tts/audio_chunk/{final_chunk_id}"
            is_proactive_audio = True if forced_chunk_id and forced_chunk_id.startswith("proactive_tts_") else False
            ws_payload = {"type": "tts_audio_chunk_ready",
                          "payload": {"url": audio_url, "sequence": sequence_num, "text_for_indicator": sentence,
                                      "chunk_id": final_chunk_id, "is_proactive_audio": is_proactive_audio}}
            try:
                logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Preparing to call send_personal_message for chunk {final_chunk_id}.")
                await asyncio.sleep(1.0) # TEST DELAY
                logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Calling send_personal_message for chunk {final_chunk_id} after delay.")
                await self.connection_manager.send_personal_message(ws_payload, user_id)
                logger.info(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Notification sent for chunk {final_chunk_id}.")
            except Exception as e_ws: logger.error(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): Exception sending WebSocket for chunk {final_chunk_id}: {e_ws}", exc_info=True)
        else:
            logger.warning(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}): No audio bytes from synthesis for: '{sentence[:30]}...'.")
        logger.debug(f"TTS_SEND_DEBUG ({user_id}, {sequence_num}, {log_prefix_indicator}): END for sentence: '{sentence[:30]}...'")

    async def generate_response(
        self,
        user_input: str,
        conversation_history: List[Dict],
        image_data_b64: Optional[str] = None,
        document_text: Optional[str] = None,
        request_metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        req_meta = request_metadata or {}
        should_stream_tts_for_this_response = req_meta.get('auto_tts_enabled_for_response', False)
        user_id_for_response = req_meta.get('user_id', self.current_active_user_id)

        logger.debug(
            f"PathosInterface.generate_response for user '{user_id_for_response}'. "
            f"TTS streaming for this response: {'ENABLED' if should_stream_tts_for_this_response else 'DISABLED'}."
        )
        self._update_active_user(user_id_for_response)
        response_metadata: Dict[str, Any] = {}
        engaged_proactive_id = req_meta.get('engaged_proactive_id')
        responding_to_proactive_content: Optional[str] = None

        if engaged_proactive_id:
            logger.info(f"User '{user_id_for_response}' engaged with proactive message ID: {engaged_proactive_id}")
            original_proactive_entry = await self.ethos_core.memory_storage.get_entry(engaged_proactive_id)
            if original_proactive_entry and (original_proactive_entry.get('type') == 'proactive_utterance' or original_proactive_entry.get('type') == 'queued_discussion_point'):
                updated_meta = original_proactive_entry.get('metadata', {}).copy()
                updated_meta['status'] = 'engaged_by_user'
                updated_meta['engaged_timestamp'] = datetime.now(timezone.utc).isoformat()
                await self.ethos_core.memory_storage.update_entry(engaged_proactive_id, {'metadata': updated_meta})
                responding_to_proactive_content = original_proactive_entry.get('content')
            else:
                logger.warning(f"Could not find or invalid type for original proactive entry ID {engaged_proactive_id}")
            response_metadata["engaged_proactive_id"] = engaged_proactive_id

        force_web_search_requested = req_meta.get('force_web_search_requested', False)
        processed_input_for_pathos_llm = user_input
        if force_web_search_requested and not user_input.strip():
            processed_input_for_pathos_llm = "current events or general knowledge"

        vision_llm_output_content: Optional[str] = None
        if image_data_b64 and self.config.ENABLE_VISION_PROCESSING and self.logos_core:
            logger.info(f"Image detected. Calling vision LLM for user '{user_id_for_response}'.")
            vision_prompt = processed_input_for_pathos_llm if processed_input_for_pathos_llm.strip() else "Describe this image in detail."
            try:
                vision_llm_output_content = await self.logos_core.execute_describe_image(image_data_b64, vision_prompt)
            except Exception as e_vision:
                logger.error(f"Error in direct vision call: {e_vision}", exc_info=True)
                vision_llm_output_content = "[System note: Error processing image.]"

        todays_briefing: Optional[str] = None
        if self.config.ENABLE_DAILY_CONTEXT:
            todays_briefing = await self.ethos_core.get_todays_briefing()

        rag_query_text = processed_input_for_pathos_llm if processed_input_for_pathos_llm.strip() else "general context"
        if document_text: rag_query_text = (rag_query_text + " " + document_text).strip()

        relevant_memories = await self.ethos_core.retrieve_relevant_memories(
            rag_query_text, top_k=5,
            allowed_types=['document_chunk', 'interaction', 'learned_correction', 'user_fact', 'world_knowledge', 'context_summary'],
            user_id_context=user_id_for_response
        )

        full_response_text_accumulator = ""
        sentence_buffer = "" 
        tts_sequence_num = 0
        final_tool_calls_for_api_response: Optional[List[Dict]] = None
        
        llm_reported_prompt_tokens_total = 0
        llm_reported_completion_tokens_total = 0
        estimated_prompt_tokens_for_response = 0

        current_mood = self.ethos_core.get_current_mood()
        response_metadata.update({
            "mood_at_response": current_mood,
            "active_user_id_for_turn": user_id_for_response,
            "hexus_scores": self.ethos_core.get_hexus_scores(),
            "vision_llm_output": vision_llm_output_content,
            "retrieved_memory_ids": [m['id'] for m in relevant_memories if isinstance(m, dict) and 'id' in m]
        })
        temperature_for_llm = req_meta.get('temperature')
        llm_provider_url_override_from_request = req_meta.get('llm_provider_url_override')
        pathos_model_override_from_request = req_meta.get('pathos_model_override')
        max_tokens_override_from_request = req_meta.get('max_tokens_override')

        current_turn_messages = [msg.model_dump(exclude_none=True) if isinstance(msg, ChatMessage) else msg for msg in conversation_history]
        current_user_message_content_list = []
        if processed_input_for_pathos_llm: current_user_message_content_list.append({"type": "text", "text": processed_input_for_pathos_llm})
        if image_data_b64: current_user_message_content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data_b64}"}})
        if document_text: current_user_message_content_list.append({"type": "text", "text": f"\n\n--- Uploaded Document Content ---\n{document_text}\n--- End Uploaded Document Content ---"})
        if not current_user_message_content_list: current_user_message_content_list.append({"type": "text", "text": "[User provided no explicit text, image, or document]"})
        current_turn_messages.append({"role": "user", "content": current_user_message_content_list})

        MAX_TOOL_ITERATIONS = int(self.pathos_llm_config.get('max_tool_iterations', 3) if self.pathos_llm_config else 3)

        if force_web_search_requested:
            logger.info(f"Force Web Search: Executing web_search for query: '{processed_input_for_pathos_llm}' before main LLM loop.")
            query_for_forced_search = processed_input_for_pathos_llm or "latest current events"
            forced_tool_call_id = f"tool_call_forced_search_{uuid.uuid4().hex[:8]}"
            forced_tool_calls_list = [{"id": forced_tool_call_id, "type": "function", "function": {"name": "web_search", "arguments": json.dumps({"query": query_for_forced_search})}}]
            current_turn_messages.append({"role": "assistant", "content": None, "tool_calls": forced_tool_calls_list})
            tool_results_messages = await self._execute_tools(forced_tool_calls_list)
            current_turn_messages.extend(tool_results_messages)
            response_metadata["forced_action"] = "web_search"
            logger.debug("Force Web Search: Tool execution complete. Proceeding to LLM for synthesis.")

        for iteration_count in range(MAX_TOOL_ITERATIONS):
            logger.debug(f"Pathos LLM interaction loop: Iteration {iteration_count + 1}")
            user_location_from_metadata = req_meta.get('weather_location')
            current_local_datetime = await self.ethos_core.get_local_datetime_for_user(user_id_for_response, location_override=user_location_from_metadata)
            local_time_formatted = current_local_datetime.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')

            messages_for_llm = await self._build_llm_messages(
                current_turn_messages, self.ethos_core.get_persona_directives(),
                relevant_memories if iteration_count == 0 else [],
                current_mood, self.ethos_core.get_hexus_scores(),
                todays_briefing if iteration_count == 0 else None,
                include_rag_context=(iteration_count == 0),
                current_user_id_for_rag_formatting=user_id_for_response,
                processed_input_for_pathos_llm_context=processed_input_for_pathos_llm,
                image_provided_this_turn=bool(image_data_b64),
                current_local_time_formatted=local_time_formatted,
                vision_llm_output_for_system_prompt=vision_llm_output_content,
                responding_to_proactive_content=responding_to_proactive_content if iteration_count == 0 else None
            )
            if iteration_count == 0 and tiktoken is not None:
                model_for_estimation = pathos_model_override_from_request or (self.pathos_llm_config.get('model', 'cl100k_base') if self.pathos_llm_config else 'cl100k_base')
                estimated_prompt_tokens_for_response = estimate_tokens_for_messages(messages_for_llm, model_for_estimation)
                if estimated_prompt_tokens_for_response > 0: response_metadata["estimated_prompt_tokens"] = estimated_prompt_tokens_for_response

            tools_for_this_llm_call = AVAILABLE_TOOLS
            if force_web_search_requested and iteration_count == 0:
                tools_for_this_llm_call = None
                logger.debug("LLM call after forced search results: Tools disabled for this synthesis step.")

            llm_decided_to_call_tools_this_iteration = False
            llm_generated_any_text_this_iteration = False
            current_iteration_tool_calls: Optional[List[Dict]] = None

            async for stream_item in self._call_pathos_llm(
                messages_for_llm, tools_definition=tools_for_this_llm_call,
                temperature=temperature_for_llm, max_tokens_override=max_tokens_override_from_request,
                llm_provider_url_override=llm_provider_url_override_from_request,
                pathos_model_override=pathos_model_override_from_request, stream=True
            ):
                if isinstance(stream_item, str):
                    text_chunk = stream_item
                    full_response_text_accumulator += text_chunk
                    llm_generated_any_text_this_iteration = True

                    if should_stream_tts_for_this_response and not llm_decided_to_call_tools_this_iteration:
                        sentence_buffer += text_chunk
                        logger.debug(f"TTS Buffer: Added chunk '{text_chunk[:30].replace(chr(10), '<NL>')}...'. Buffer now: '{sentence_buffer[:100].replace(chr(10), '<NL>')}...'")
                        
                        while True:
                            # Try to find a sentence ending with common punctuation or a double newline (paragraph break)
                            match = re.search(r"([.!?](?=\s|$))|\n", sentence_buffer) # Simpler regex for testing, consider \n\n for paragraphs

                            if match:
                                split_index = match.end()
                                sentence_to_dispatch = sentence_buffer[:split_index].strip()
                                sentence_buffer = sentence_buffer[split_index:] 

                                if sentence_to_dispatch:
                                    logger.info(f"TTS Stream Dispatch: User '{user_id_for_response}', Seq {tts_sequence_num}, Sentence: '{sentence_to_dispatch[:60].replace(chr(10), '<NL>')}...'")
                                    asyncio.create_task(
                                        self.send_sentence_to_tts_and_notify_client(
                                            sentence_to_dispatch, 
                                            user_id_for_response, 
                                            tts_sequence_num, 
                                            chunk_id_prefix="chat_tts_" # Correct prefix for chat
                                        )
                                    )
                                    tts_sequence_num += 1
                                else:
                                    logger.debug("TTS Buffer: Matched segment was empty after strip. Continuing to process buffer.")
                                
                                if not sentence_buffer.strip(): 
                                    logger.debug("TTS Buffer: Remainder is empty/whitespace after dispatch. Breaking inner sentence loop.")
                                    break 
                            else:
                                logger.debug("TTS Buffer: No sentence terminator found yet in current buffer. Breaking inner sentence loop, will accumulate more.")
                                break 
                elif isinstance(stream_item, dict) and stream_item.get("type") == "tool_calls_chunk":
                    llm_decided_to_call_tools_this_iteration = True
                    current_iteration_tool_calls = stream_item.get("tool_calls")
                    logger.info(f"Pathos LLM decided to use tools in iteration {iteration_count + 1}: {current_iteration_tool_calls}")
                elif isinstance(stream_item, dict) and stream_item.get("type") == "usage_chunk":
                    current_chunk_usage_data = stream_item.get("usage")
                    if current_chunk_usage_data:
                        logger.debug(f"LLM Stream: Received usage_chunk: {current_chunk_usage_data}")
                        llm_reported_prompt_tokens_total += current_chunk_usage_data.get("prompt_tokens", 0)
                        llm_reported_completion_tokens_total += current_chunk_usage_data.get("completion_tokens", 0)
                elif isinstance(stream_item, dict) and stream_item.get("type") == "error_chunk":
                    error_content = stream_item.get("content_error", "[Unknown LLM Stream Error]")
                    logger.error(f"Error received during LLM stream: {error_content}")
                    full_response_text_accumulator = error_content
                    llm_generated_any_text_this_iteration = True
                    llm_decided_to_call_tools_this_iteration = False 
                    break 

            if llm_decided_to_call_tools_this_iteration and current_iteration_tool_calls:
                final_tool_calls_for_api_response = current_iteration_tool_calls
                assistant_message_for_tool_call = {
                    "role": "assistant",
                    "content": full_response_text_accumulator.strip() if full_response_text_accumulator.strip() else None,
                    "tool_calls": final_tool_calls_for_api_response
                }
                current_turn_messages.append(assistant_message_for_tool_call)
                tool_results_messages = await self._execute_tools(final_tool_calls_for_api_response)
                current_turn_messages.extend(tool_results_messages)
                full_response_text_accumulator = "" 
                llm_generated_any_text_this_iteration = False 
                sentence_buffer = "" 
                if iteration_count == MAX_TOOL_ITERATIONS - 1:
                    logger.warning("Max tool iterations reached. LLM must now respond without further tools or this turn ends with tool call.")
                    if not full_response_text_accumulator.strip() and final_tool_calls_for_api_response:
                         full_response_text_accumulator = "[Tool call(s) made by Pathos]"
                    break 
            elif llm_generated_any_text_this_iteration:
                break 
            else: 
                logger.warning(f"LLM iteration {iteration_count + 1} resulted in no text and no tool calls.")
                if iteration_count == MAX_TOOL_ITERATIONS - 1: 
                    full_response_text_accumulator = "[Pathos LLM returned no actionable output after iterations.]"
                break 

        if sentence_buffer.strip() and should_stream_tts_for_this_response and not final_tool_calls_for_api_response:
            final_sentence = sentence_buffer.strip()
            logger.info(f"TTS Stream Dispatch (Final Buffer): User '{user_id_for_response}', Seq {tts_sequence_num}, Sentence: '{final_sentence[:60].replace(chr(10), '<NL>')}...'")
            asyncio.create_task(
                self.send_sentence_to_tts_and_notify_client(
                    final_sentence, 
                    user_id_for_response, 
                    tts_sequence_num, 
                    chunk_id_prefix="chat_tts_" # Correct prefix for chat
                )
            )
            # tts_sequence_num += 1 # Not strictly needed after the loop if not used further
            sentence_buffer = "" 

        final_response_text_for_http = full_response_text_accumulator.strip()
        if not final_response_text_for_http and final_tool_calls_for_api_response:
            final_response_text_for_http = None 
        elif not final_response_text_for_http and not final_tool_calls_for_api_response:
            final_response_text_for_http = "[Pathos did not generate a textual response.]"
            logger.warning("PathosInterface.generate_response: No text and no tool calls. Using fallback message.")

        if final_response_text_for_http and not final_tool_calls_for_api_response and self.config.ENABLE_PROACTIVE_BEHAVIOR:
            hexus_scores_updated = self.ethos_core.get_hexus_scores()
            proactivity_score = hexus_scores_updated.get('user_engagement_proactivity', 0.0)
            proactive_engage_threshold = self.ethos_core.ethos_config.get('proactive_engagement_threshold', 0.1)
            proactive_engage_curve_k = self.ethos_core.ethos_config.get('proactive_engagement_curve_k', 2.5)
            if proactivity_score > proactive_engage_threshold:
                  probability = 1 - math.exp(-proactive_engage_curve_k * (proactivity_score - proactive_engage_threshold))
                  if random.random() < probability:
                     follow_ups = ["Is there anything else I can help you with today?", "What else is on your mind?", "Anything else I can look into?", "Let me know if anything else comes up!"]
                     chosen_follow_up = random.choice(follow_ups)
                     ends_with_punctuation = final_response_text_for_http.strip().endswith((".", "!", ")", "]","?"))
                     if ends_with_punctuation: final_response_text_for_http += f" {chosen_follow_up}"
                     else: final_response_text_for_http += f". {chosen_follow_up}"

        await self._store_final_interaction(
            original_user_input=user_input, pathos_response=final_response_text_for_http,
            mood_at_response=response_metadata["mood_at_response"],
            retrieved_memories=relevant_memories,
            full_history_for_pathos=current_turn_messages,
            error=(not final_response_text_for_http and not final_tool_calls_for_api_response) or \
                  (final_response_text_for_http is not None and final_response_text_for_http.startswith(("[Error:", "[Pathos LLM"))),
            image_provided_this_turn=bool(image_data_b64),
            vision_llm_output=vision_llm_output_content,
            is_proactive_turn=bool(engaged_proactive_id),
            forced_action=response_metadata.get("forced_action")
        )
        if document_text and self.logos_core:
             asyncio.create_task(self.logos_core.add_document_to_rag(extracted_text=document_text, filename="uploaded_via_chat", user_id=user_id_for_response), name=f"AddDocToRAG_{user_id_for_response}_{uuid.uuid4().hex[:4]}")

        is_error_response = (not final_response_text_for_http and not final_tool_calls_for_api_response) or \
                            (final_response_text_for_http is not None and final_response_text_for_http.startswith(("[Error:", "[Pathos LLM")))
        if self.config.ENABLE_MOOD_SIMULATION:
            await self.ethos_core.update_mood_state('task_outcome', {'success': not is_error_response, 'type': 'conversation'})

        response_metadata["prompt_tokens_from_llm"] = llm_reported_prompt_tokens_total
        response_metadata["completion_tokens_from_llm"] = llm_reported_completion_tokens_total
        response_metadata["tool_calls_from_pathos"] = final_tool_calls_for_api_response
        response_metadata["tts_stream_attempted"] = should_stream_tts_for_this_response

        return {
            "success": not is_error_response,
            "content": final_response_text_for_http,
            "metadata": response_metadata
        }

    async def _build_llm_messages(self, current_turn_messages: List[Dict], persona_directives: List[str], relevant_memories: List[MemoryEntry], current_mood: Dict[str, float], hexus_scores: Dict[str, float], todays_briefing: Optional[str], include_rag_context: bool, current_user_id_for_rag_formatting: str, processed_input_for_pathos_llm_context: str, image_provided_this_turn: bool, current_local_time_formatted: str, vision_llm_output_for_system_prompt: Optional[str] = None, responding_to_proactive_content: Optional[str] = None) -> List[Dict[str, Any]]:
        final_messages_for_llm: List[Dict[str, Any]] = []; system_prompt_parts = []
        if persona_directives: system_prompt_parts.extend(persona_directives); system_prompt_parts.append("\n")
        actual_conversation_history = []; gui_system_prompt_content: Optional[str] = None; temp_history_for_processing = list(current_turn_messages)
        if temp_history_for_processing and temp_history_for_processing[0].get("role") == "system":
            gui_system_message = temp_history_for_processing.pop(0)
            if isinstance(gui_system_message.get("content"), str): gui_system_prompt_content = gui_system_message["content"].strip()
        actual_conversation_history = temp_history_for_processing
        if gui_system_prompt_content: system_prompt_parts.append("--- USER-DEFINED SYSTEM PROMPT (FROM GUI) ---"); system_prompt_parts.append(gui_system_prompt_content); system_prompt_parts.append("--- END USER-DEFINED SYSTEM PROMPT ---\n")
        system_prompt_parts.extend([ "--- CRITICAL INSTRUCTION: TOOL USE ---", "Your PRIMARY task is to fulfill the user's request.", "If the user's request clearly requires ANY of the AVAILABLE TOOLS, you MUST output ONLY the tool_calls structure for the necessary tool(s) immediately.", "DO NOT provide any conversational text or acknowledgement if a tool call is required.", "If multiple tools are needed for the request (e.g., 'time and weather'), output ALL required tool_calls in a single response.", "Only provide a conversational text response if NO tool is needed, or in a subsequent turn AFTER tool results have been provided to you.", "Strictly adhere to this: Tool needed -> Output ONLY tool_calls. No tool needed -> Output conversational text.", "--- END CRITICAL INSTRUCTION ---\n" ])
        system_prompt_parts.append(f"Current time: {current_local_time_formatted}")
        if current_user_id_for_rag_formatting and current_user_id_for_rag_formatting not in ["default_user", "unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "world_knowledge_store", "system_reflection"]: system_prompt_parts.append(f"You are currently interacting with user: {current_user_id_for_rag_formatting}.")
        else: system_prompt_parts.append("You are currently interacting with a user.")
        if vision_llm_output_for_system_prompt: system_prompt_parts.append("\n--- CONTEXT FROM IMAGE ANALYSIS ---"); system_prompt_parts.append(vision_llm_output_for_system_prompt); system_prompt_parts.append("--- END IMAGE ANALYSIS ---"); system_prompt_parts.append("\n[System Note: The user has provided an image. The analysis above is for your context. Respond to the user's query considering both their text (if any) and this image analysis.]")
        elif image_provided_this_turn: system_prompt_parts.append("\n[System Note: The user has provided an image this turn. Refer to the image content in their message if your model supports multimodal input.]")
        if actual_conversation_history and actual_conversation_history[-1].get("role") == "user":
            last_user_content = actual_conversation_history[-1].get("content"); doc_marker_present_in_user_message = False
            if isinstance(last_user_content, list):
                for part in last_user_content:
                    if isinstance(part, dict) and part.get("type") == "text" and "--- Uploaded Document Content ---" in part.get("text", ""): doc_marker_present_in_user_message = True; break
            elif isinstance(last_user_content, str) and "--- Uploaded Document Content ---" in last_user_content: doc_marker_present_in_user_message = True
            if doc_marker_present_in_user_message: system_prompt_parts.append("\n[System Note: The user's current input includes content from an uploaded document. Consider this document content when formulating your response.]")
# --- Start of corrected segment in _build_llm_messages ---
        HEXUS_ACTIVATION_THRESHOLD = self.ethos_core.ethos_config.get('hexus_activation_threshold', 0.1)
        HEXUS_CURVE_K = self.ethos_core.ethos_config.get('hexus_curve_k', 2.0)

        score_brevity = hexus_scores.get('brevity_preference', 0.0)
        prob_brevity = 0.0  # Initialize to ensure it's always defined
        if abs(score_brevity) > HEXUS_ACTIVATION_THRESHOLD:
            prob_brevity = 1 - math.exp(-HEXUS_CURVE_K * (abs(score_brevity) - HEXUS_ACTIVATION_THRESHOLD))
        
        if random.random() < prob_brevity: # Now prob_brevity is guaranteed to exist
            system_prompt_parts.append("Instruction: Aim for conciseness." if score_brevity > 0 else "Instruction: Feel free to elaborate and provide detail.")

        score_caution = hexus_scores.get('general_caution', 0.0)
        prob_caution = 0.0  # Initialize to ensure it's always defined
        if abs(score_caution) > HEXUS_ACTIVATION_THRESHOLD:
            prob_caution = 1 - math.exp(-HEXUS_CURVE_K * (abs(score_caution) - HEXUS_ACTIVATION_THRESHOLD))

        if random.random() < prob_caution: # Now prob_caution is guaranteed to exist
            system_prompt_parts.append("Instruction: Exercise caution; qualify statements and avoid speculation." if score_caution > 0 else "Instruction: You can be more direct and assertive in your statements.")
        
        if todays_briefing: 
            system_prompt_parts.append(f"\n--- Today's Context ---\n{todays_briefing}\n--- End Context ---")
        if self.config.ENABLE_MOOD_SIMULATION: 
            system_prompt_parts.append(f"\nYour current mood: valence {current_mood['valence']:.2f}, arousal {current_mood['arousal']:.2f}.")
        if hexus_scores: 
            system_prompt_parts.append("\n(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores.items()]) + ")")
        
        final_system_content = "\n".join(filter(None, system_prompt_parts)).strip()
        final_messages_for_llm.append({"role": "system", "content": final_system_content if final_system_content else "You are a helpful assistant."})
        
        if include_rag_context and relevant_memories:
            rag_context_parts, user_facts_context_parts = [], []
            for mem_entry in relevant_memories:
                if not isinstance(mem_entry, dict): 
                    continue
                mem_type = mem_entry.get('type')
                mem_content_rag = mem_entry.get('content', 'N/A')
                mem_user_id = mem_entry.get('metadata', {}).get('user_id', 'unknown_user')
                
                if mem_type == 'user_fact' and mem_user_id == current_user_id_for_rag_formatting:
                    try:
                        fact_data = json.loads(mem_content_rag)
                        user_facts_context_parts.append(f"Fact about user ({current_user_id_for_rag_formatting}): Their {fact_data.get('attribute_name')} is {fact_data.get('attribute_value')}. (Context: '{fact_data.get('user_statement_context','')[:50]}...')")
                    except Exception:
                        user_facts_context_parts.append(f"User fact (raw for {current_user_id_for_rag_formatting}): {mem_content_rag[:100]}...")
                elif mem_type == 'document_chunk':
                    doc_name = mem_entry.get('metadata',{}).get('source_document_name','a document')
                    chunk_index = mem_entry.get('metadata',{}).get('chunk_index','N/A')
                    rag_context_parts.append(f"Excerpt from Document '{doc_name}' (Chunk {chunk_index}):\n{mem_content_rag}")
                elif mem_type == 'interaction':
                    ts = mem_entry.get('timestamp', 'unknown time')
                    try:
                        readable_time = datetime.fromisoformat(ts.replace("Z","+00:00")).strftime('%Y-%m-%d %H:%M %Z')
                    except:
                        readable_time = ts
                    interaction_user_label = f"user: {mem_user_id}" if mem_user_id != current_user_id_for_rag_formatting else "current user"
                    rag_context_parts.append(f"From a past conversation ({interaction_user_label}, around {readable_time}):\n{mem_content_rag}")
                elif mem_type == 'learned_correction':
                    rag_context_parts.append(f"A past learning/correction (user: {mem_user_id}):\n{mem_content_rag}")
                elif mem_type == 'world_knowledge':
                    source_desc = mem_entry.get('metadata',{}).get('source_description','unknown')
                    confidence = mem_entry.get('metadata',{}).get('confidence_level','N/A')
                    rag_context_parts.append(f"A known fact: {mem_content_rag} (Source: {source_desc}, Confidence: {confidence})")
                elif mem_type == 'context_summary':
                    summary_key = mem_entry.get('metadata',{}).get('summarization_key','general')
                    rag_context_parts.append(f"Summary of past context ({summary_key}):\n{mem_content_rag}")

            if user_facts_context_parts:
                final_messages_for_llm.append({"role": "system", "content": f"--- FACTS ABOUT USER ({current_user_id_for_rag_formatting}) ---\n" + "\n".join(user_facts_context_parts) + "\n--- END USER FACTS ---"})
            if rag_context_parts:
                final_messages_for_llm.append({"role": "system", "content": "--- RETRIEVED GENERAL MEMORIES (Use if relevant, prioritize user facts & current conversation) ---\n" + "\n\n---\n\n".join(rag_context_parts) + "\n--- END GENERAL MEMORIES ---"})
        
        temp_final_history_for_llm: List[Dict[str, Any]] = []
        if responding_to_proactive_content and actual_conversation_history:
            if len(actual_conversation_history) > 1:
                temp_final_history_for_llm.extend(actual_conversation_history[:-1])
            temp_final_history_for_llm.append({"role": "assistant", "content": responding_to_proactive_content})
            temp_final_history_for_llm.append(actual_conversation_history[-1])
        else:
            temp_final_history_for_llm.extend(actual_conversation_history)
        
        final_messages_for_llm.extend(temp_final_history_for_llm)
        
        if logger.isEnabledFor(logging.DEBUG):
            for i, msg in enumerate(final_messages_for_llm):
                content_str_log = str(msg.get('content', ''))[:150] + "..." if len(str(msg.get('content', ''))) > 150 else str(msg.get('content', ''))
                tool_calls_log = msg.get('tool_calls')
                if tool_calls_log:
                    content_str_log += f" | Tools: {tool_calls_log}"
                if msg.get('role') == 'tool':
                    content_str_log = f"[Result for tool_call_id={msg.get('tool_call_id')}, name={msg.get('name')}] {content_str_log}"
                logger.debug(f"  Msg {i} Role: {msg['role']}, Content: {content_str_log}")
        return final_messages_for_llm

    async def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        tool_result_messages = []
        for tool_call_data_item in tool_calls:
            tool_call_id = tool_call_data_item.get("id"); function_info = tool_call_data_item.get("function", {}); function_name = function_info.get("name"); arguments_str = function_info.get("arguments", "{}")
            if not tool_call_id or not function_name: tool_result_messages.append({"role": "tool", "tool_call_id": tool_call_id or f"err_{uuid.uuid4().hex[:4]}", "name": function_name or "unknown_function", "content": json.dumps({"error": "Malformed tool call from LLM."})}); continue
            logger.info(f"Executing tool: {function_name} (ID: {tool_call_id}) with args: {arguments_str}"); tool_result_content_str: str = ""; tool_success = False; arguments: Optional[Dict] = None
            try: arguments = json.loads(arguments_str); assert isinstance(arguments, dict)
            except Exception as arg_e: logger.error(f"Argument parsing error for tool {function_name} (ID: {tool_call_id}): {arg_e}. Args: '{arguments_str}'"); tool_result_content_str = json.dumps({"error": f"Invalid JSON arguments for {function_name}."})
            if arguments is not None:
                try:
                    if function_name == "get_current_time": tool_result_content_str = await self.logos_core.execute_get_time(arguments.get("location"))
                    elif function_name == "web_search": query = arguments.get("query"); tool_result_content_str = json.dumps(await self.logos_core.execute_web_search(query)) if query and isinstance(query, str) else json.dumps({"error": "Missing 'query' for web_search."})
                    elif function_name == "math_calculator": expr = arguments.get("expression"); tool_result_content_str = await self.logos_core.execute_math_calculation(expr) if expr and isinstance(expr, str) else json.dumps({"error": "Missing 'expression' for math_calculator."})
                    elif function_name == "get_weather": loc = arguments.get("location"); weather_res = await self.logos_core.execute_get_weather(loc, user_id_context=self.current_active_user_id) if loc and isinstance(loc, str) else {"error": "Missing 'location' for get_weather."}; tool_result_content_str = json.dumps(weather_res)
                    elif function_name == "store_user_fact":
                        tool_result_content_str = await self.logos_core.execute_store_user_fact(attribute_name=str(arguments.get("attribute_name","")), attribute_value=str(arguments.get("attribute_value","")), user_statement_context=str(arguments.get("user_statement_context","")), user_id=self.current_active_user_id)
                        # Check if user's name was stored and update active user if so
                        if not tool_result_content_str.startswith('{"error":') and str(arguments.get("attribute_name","")).lower() == "name":
                            try:
                                result_json = json.loads(tool_result_content_str)
                                if result_json.get("status") == "success":
                                    self._update_active_user(str(arguments.get("attribute_value","")), set_by_statement=True)
                            except json.JSONDecodeError:
                                pass # Error in parsing result, do nothing
                    elif function_name == "store_world_fact": tool_result_content_str = await self.logos_core.execute_store_world_fact(fact_statement=str(arguments.get("fact_statement","")), source_description=str(arguments.get("source_description","")), topic_tags=arguments.get("topic_tags",[]), confidence_level=float(arguments.get("confidence_level", 0.8)))
                    elif function_name == "perform_deep_research": tool_result_content_str = await self.logos_core.execute_deep_research(research_query=str(arguments.get("research_query","")), num_searches_to_perform=int(arguments.get("number_of_searches",3)))
                    elif function_name == "get_news_headlines": tool_result_content_str = await self.logos_core.execute_get_news_headlines()
                    else: tool_result_content_str = json.dumps({"error": f"Unknown tool '{function_name}'."})
                    try: parsed_result = json.loads(tool_result_content_str); tool_success = not (isinstance(parsed_result, dict) and "error" in parsed_result)
                    except json.JSONDecodeError: tool_success = bool(tool_result_content_str) # If not JSON, but not empty, assume success (e.g. plain string result)
                except Exception as tool_exec_e: logger.error(f"Error executing tool '{function_name}' (ID: {tool_call_id}): {tool_exec_e}", exc_info=True); tool_result_content_str = json.dumps({"error": f"Unexpected error executing '{function_name}'."}); tool_success = False
            if not tool_result_content_str: tool_result_content_str = json.dumps({"error": "Tool execution failed or args invalid."}); tool_success = False # Ensure content_str is never empty
            if self.config.ENABLE_MOOD_SIMULATION: await self.ethos_core.update_mood_state('task_outcome', {'success': tool_success, 'type': 'tool_execution', 'tool_name': function_name})
            tool_result_messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": function_name, "content": tool_result_content_str})
            logger.debug(f"Tool {function_name} (ID: {tool_call_id}) result (success: {tool_success}): {tool_result_content_str[:150]}...")
        return tool_result_messages

    async def _store_final_interaction(
        self, original_user_input: str, pathos_response: Optional[str],
        mood_at_response: Dict[str, float], retrieved_memories: List[MemoryEntry],
        full_history_for_pathos: List[Dict], error: bool = False,
        image_provided_this_turn: bool = False, vision_llm_output: Optional[str] = None,
        is_proactive_turn: bool = False,
        forced_action: Optional[str] = None
    ):
        user_id_for_memory = self.current_active_user_id
        interaction_type = "interaction_error" if error else "interaction"

        tool_usage_summary = []
        call_id_map: Dict[str, Dict[str, Any]] = {} # Maps tool_call_id to its request details

        for msg in full_history_for_pathos:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                calls = msg.get("tool_calls") # Get the tool_calls list/object
                if isinstance(calls, list): # Check if it's a list (it should be)
                    for tc_dict in calls:
                        if isinstance(tc_dict, dict): # Each item in tool_calls should be a dict
                            call_id = tc_dict.get("id")
                            func_info = tc_dict.get("function")
                            if call_id and isinstance(func_info, dict) and func_info.get("name"):
                                call_id_map[call_id] = {
                                    "tool_name": func_info.get("name"),
                                    "request_args": func_info.get("arguments")
                                    # "result_summary" will be added when role 'tool' message is processed
                                }
                else:
                    logger.warning(f"Unexpected format for tool_calls in assistant message: {calls}")

            elif msg.get("role") == "tool":
                call_id = msg.get("tool_call_id")
                if call_id and call_id in call_id_map: # Ensure call_id exists and is in map
                    tool_info = call_id_map[call_id]
                    result_content = str(msg.get("content", ""))
                    tool_info["result_summary"] = result_content[:200] + "..." if len(result_content) > 200 else result_content
                    # Only add to summary once result is processed
                    # To avoid duplicates if a tool_call_id appears multiple times (should not happen with OpenAI spec)
                    # We can add it here, or collect all tool_info from call_id_map at the end.
                    # For simplicity, let's assume we add it when the 'tool' role message is found.
                    # To prevent adding multiple times if somehow a tool result is split (not standard):
                    if not any(summary_item.get("tool_name") == tool_info.get("tool_name") and \
                               summary_item.get("request_args") == tool_info.get("request_args") \
                               for summary_item in tool_usage_summary if summary_item.get("id_from_map") == call_id): # Check if already added
                        tool_info_copy = tool_info.copy()
                        tool_info_copy["id_from_map"] = call_id # Add id for tracking if needed
                        tool_usage_summary.append(tool_info_copy)

        # If there were tool calls initiated but no corresponding 'tool' role messages with results
        # (e.g., if the interaction ended on an assistant's tool_call),
        # we can add them to the summary without a result.
        for call_id, tool_data in call_id_map.items():
            if not any(summary_item.get("id_from_map") == call_id for summary_item in tool_usage_summary):
                logger.debug(f"Tool call {call_id} ({tool_data.get('tool_name')}) was initiated but no result found in history. Adding to summary without result.")
                tool_data_copy = tool_data.copy()
                tool_data_copy["id_from_map"] = call_id
                tool_data_copy.setdefault("result_summary", "[No result processed in this history segment]")
                tool_usage_summary.append(tool_data_copy)
        
        # Remove the temporary 'id_from_map' key before storing
        for item in tool_usage_summary:
            item.pop("id_from_map", None)


        pathos_llm_final_input_content_summary = "N/A"
        doc_included_in_input = False
        last_user_message_in_history = next((m for m in reversed(full_history_for_pathos) if m.get("role") == "user"), None)

        if last_user_message_in_history:
             content = last_user_message_in_history.get("content")
             if isinstance(content, str):
                  pathos_llm_final_input_content_summary = content[:250] + "..." if len(content) > 250 else content
             elif isinstance(content, list):
                  text_parts = []
                  img_part = False
                  for part_item in content: 
                      if isinstance(part_item, dict):
                          if part_item.get("type") == "text":
                              text_content = part_item.get("text", "")
                              text_parts.append(text_content)
                              doc_included_in_input = doc_included_in_input or "--- Uploaded Document Content ---" in text_content
                          elif part_item.get("type") == "image_url":
                              img_part = True
                  summary_parts = [" ".join(text_parts).strip()[:150] + "..."] if " ".join(text_parts).strip() else []
                  if img_part: summary_parts.append("[Image Included]")
                  pathos_llm_final_input_content_summary = " | ".join(summary_parts) or "Multimodal Input"


        metadata = {
            "user_id": user_id_for_memory,
            "user_input_original_text": original_user_input,
            "image_provided_this_turn": image_provided_this_turn,
            "document_included_this_turn": doc_included_in_input,
            "vision_llm_output_if_any": vision_llm_output[:1000] if vision_llm_output else None,
            "pathos_llm_input_summary": pathos_llm_final_input_content_summary,
            "pathos_final_response_text": pathos_response,
            "mood_at_response": mood_at_response,
            "retrieved_memory_ids": [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m],
            "tool_usage_summary_by_pathos": tool_usage_summary if tool_usage_summary else None,
            "is_proactive_turn": is_proactive_turn,
            "error_in_turn": error
        }
        if forced_action:
            metadata["forced_action"] = forced_action

        content_summary_parts = [f"User ({user_id_for_memory}, original text): {original_user_input}"]
        if image_provided_this_turn: content_summary_parts.append('[Image provided by user.]')
        if vision_llm_output: content_summary_parts.append(f'[Vision System Output: {vision_llm_output[:100] + "..." if len(vision_llm_output) > 100 else vision_llm_output}]')
        if doc_included_in_input: content_summary_parts.append('[Document content included in input.]')
        content_summary_parts.append(f"Pathos: {pathos_response if pathos_response else '[No textual response/Tool call]'}")
        if tool_usage_summary:
            tool_summary_str_parts = []
            for t in tool_usage_summary:
                args_summary = str(t.get('request_args', ''))[:50] + "..." if len(str(t.get('request_args', ''))) > 50 else str(t.get('request_args', ''))
                tool_summary_str_parts.append(f"{t.get('tool_name', 'unknown_tool')}(args={args_summary}, result={t.get('result_summary', 'N/A')})")
            content_summary_parts.append(f"Tools Used: {', '.join(tool_summary_str_parts)}")
        if forced_action: content_summary_parts.append(f"[Action '{forced_action}' was forced by user directive.]")
        if error: content_summary_parts.append("[Error occurred during this turn.]")

        content_summary = "\n".join(content_summary_parts)
        await self.ethos_core.add_memory_entry(
            {"type": interaction_type, "content": content_summary, "metadata": metadata},
            user_id_context=user_id_for_memory
        )
        logger.debug(f"Stored final interaction for user '{user_id_for_memory}'. Type: {interaction_type}.")

    def _prepare_llm_call_params( self, temperature: Optional[float], max_tokens_override: Optional[int], llm_provider_url_override: Optional[str], pathos_model_override: Optional[str] ) -> Tuple[Optional[str], Optional[str], Dict[str, str], float, int]:
        final_api_url: Optional[str] = None
        if llm_provider_url_override and llm_provider_url_override.startswith('http'):
            final_api_url = f"{llm_provider_url_override.rstrip('/')}/chat/completions"
        elif self.pathos_llm_config and self.pathos_llm_config.get('url'):
            final_api_url = f"{self.pathos_llm_config['url'].rstrip('/')}/chat/completions"
        else: 
            return None, None, {}, 0.7, 4096
        final_model_name: Optional[str] = None
        if pathos_model_override and pathos_model_override.strip():
            final_model_name = pathos_model_override.strip()
        elif self.pathos_llm_config and self.pathos_llm_config.get('model'):
            final_model_name = self.pathos_llm_config['model']
        else:
            final_model_name = "eidos-agent" # Default model name if not specified
        
        if not final_model_name or not final_model_name.strip(): # Ensure final_model_name is not empty
            final_model_name = "eidos-agent"

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        api_key = self.pathos_llm_config.get('api_key') if self.pathos_llm_config else None
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
            headers["Authorization"] = f"Bearer {api_key}"

        llm_max_tokens_from_config = (self.pathos_llm_config.get('max_tokens', 4096) if self.pathos_llm_config else 4096)
        final_max_tokens = llm_max_tokens_from_config
        if max_tokens_override is not None and isinstance(max_tokens_override, int) and max_tokens_override > 0:
            min_allowable_override = (self.pathos_llm_config.get('min_tokens_override_limit', 256) if self.pathos_llm_config else 256)
            max_allowable_override = (self.pathos_llm_config.get('max_tokens_override_limit', 32000) if self.pathos_llm_config else 32000)
            final_max_tokens = max(min_allowable_override, min(max_tokens_override, max_allowable_override))
        else:
            try:
                final_max_tokens = int(llm_max_tokens_from_config)
            except (ValueError, TypeError):
                final_max_tokens = 4096
        
        if final_max_tokens <= 0: # Ensure max_tokens is positive
            final_max_tokens = 4096

        llm_temperature_from_config = (self.pathos_llm_config.get('temperature', 0.7) if self.pathos_llm_config else 0.7)
        final_temperature = temperature if temperature is not None else llm_temperature_from_config
        try:
            final_temperature = float(final_temperature)
            final_temperature = max(0.0, min(2.0, final_temperature)) # Clamp temperature
        except (ValueError, TypeError):
            final_temperature = 0.7
            
        return final_api_url, final_model_name, headers, final_temperature, final_max_tokens

    async def _call_pathos_llm( self, messages: List[Dict[str, Any]], tools_definition: Optional[List[Dict]] = None, temperature: Optional[float] = None, max_tokens_override: Optional[int] = None, llm_provider_url_override: Optional[str] = None, pathos_model_override: Optional[str] = None, stream: bool = False ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        final_api_url, final_model_name, headers, final_temperature, final_max_tokens = self._prepare_llm_call_params(temperature, max_tokens_override, llm_provider_url_override, pathos_model_override)
        if not final_api_url or not final_model_name: yield {"type": "error_chunk", "content_error": "[LLM URL or Model Name not configured]"}; return
        payload_to_send = { "model": final_model_name, "messages": messages, "temperature": final_temperature, "max_tokens": final_max_tokens, "stream": stream }
        if tools_definition: payload_to_send["tools"] = tools_definition; payload_to_send["tool_choice"] = "auto"
        logger.debug(f">>> Pathos LLM API Call (Stream: {stream}): {final_api_url}, Model: {final_model_name}, Temp: {final_temperature}, MaxTokens: {final_max_tokens}, Tools: {bool(payload_to_send.get('tools'))}")
        timeout_cfg_val = (self.pathos_llm_config.get('timeout', 300) if self.pathos_llm_config else 300)
        try: call_timeout = float(timeout_cfg_val)
        except (ValueError, TypeError): call_timeout = 300.0
        try:
            if stream:
                logger.info(f"LLM Stream: Attempting to establish stream with {final_api_url}...")
                async with self.http_client.stream("POST", final_api_url, headers=headers, json=payload_to_send, timeout=call_timeout) as response:
                    logger.info(f"LLM Stream: Connection established, status: {response.status_code}"); logger.debug(f"LLM Stream: Headers: {response.headers}"); response.raise_for_status(); logger.info("LLM Stream: raise_for_status() passed. Iterating lines...")
                    tool_call_indices = {}; line_count = 0
                    async for line in response.aiter_lines():
                        line_count += 1; logger.debug(f"LLM Stream: Received line #{line_count}: {line[:200]}")
                        if line.startswith("data:"):
                            data_json_str = line[len("data:"):].strip()
                            if data_json_str == "[DONE]": logger.info("LLM Stream: Received [DONE]."); break
                            try:
                                chunk_data = json.loads(data_json_str); choices = chunk_data.get("choices", [])
                                if choices and (delta := choices[0].get("delta", {})):
                                    text_chunk_from_delta = None
                                    if "content" in delta and delta["content"] is not None: text_chunk_from_delta = str(delta["content"])
                                    elif "reasoning_content" in delta and delta["reasoning_content"] is not None: logger.debug("LLM Stream: Found text in 'delta.reasoning_content'."); text_chunk_from_delta = str(delta["reasoning_content"]) # Cohere-like field
                                    if text_chunk_from_delta is not None: logger.debug(f"LLM Stream: Yielding text_chunk: '{text_chunk_from_delta[:50]}'"); yield text_chunk_from_delta
                                    if tool_calls_delta := delta.get("tool_calls"):
                                        for tc_delta_part in tool_calls_delta:
                                            idx = tc_delta_part.get("index", 0)
                                            if idx not in tool_call_indices: tool_call_indices[idx] = { "id": tc_delta_part.get("id", f"tool_{uuid.uuid4().hex[:4]}_{idx}"), "type": tc_delta_part.get("type", "function"), "function": {"name": "", "arguments": ""} }
                                            current_tc = tool_call_indices[idx]
                                            if new_id := tc_delta_part.get("id"): current_tc["id"] = new_id # Overwrite if full ID comes later
                                            if new_type := tc_delta_part.get("type"): current_tc["type"] = new_type
                                            if func_delta := tc_delta_part.get("function"):
                                                if name_part := func_delta.get("name"): current_tc["function"]["name"] += name_part
                                                if args_part := func_delta.get("arguments"): current_tc["function"]["arguments"] += args_part
                                if choices and choices[0].get("finish_reason") == "tool_calls" and tool_call_indices:
                                    full_tool_calls = [tc for idx, tc in sorted(tool_call_indices.items())]; logger.info(f"LLM Stream: Yielding tool_calls_chunk: {full_tool_calls}"); yield {"type": "tool_calls_chunk", "tool_calls": full_tool_calls}; tool_call_indices.clear()
                            except json.JSONDecodeError: logger.warning(f"LLM Stream: Could not decode JSON chunk: {data_json_str}")
                    if tool_call_indices: # If stream ends before finish_reason: tool_calls but we have partials
                        full_tool_calls = [tc for idx, tc in sorted(tool_call_indices.items())]; logger.info(f"LLM Stream: Yielding remaining tool_calls after stream end: {full_tool_calls}"); yield {"type": "tool_calls_chunk", "tool_calls": full_tool_calls}; tool_call_indices.clear()
                    if hasattr(response, 'extensions') and 'usage' in response.extensions: # For some OpenAI-compatible servers
                        logger.info(f"LLM Stream: Yielding usage_chunk from response.extensions: {response.extensions['usage']}"); yield {"type": "usage_chunk", "usage": response.extensions['usage']}
            else: # Non-streaming
                response = await self.http_client.post(final_api_url, headers=headers, json=payload_to_send, timeout=call_timeout)
                response.raise_for_status(); result = response.json(); logger.debug(f"<<< Pathos LLM API Response (Non-Stream). Status: {response.status_code}, Result: {str(result)[:200]}...")
                content_yielded = False; tools_yielded = False
                if choices := result.get("choices"):
                    if message := choices[0].get("message"):
                        if content := message.get("content"): # content can be None
                            if content is not None and content.strip(): yield content; content_yielded = True
                            elif content is None and not message.get("tool_calls"): # If content is explicitly None and no tools, yield empty string to signal completion without text
                                yield ""; content_yielded = True

                        if tools := message.get("tool_calls"): yield {"type": "tool_calls_chunk", "tool_calls": tools}; tools_yielded = True
                if usage := result.get("usage"): yield {"type": "usage_chunk", "usage": usage}
                if not content_yielded and not tools_yielded: logger.info(f"Pathos LLM (Non-Stream) response had no content or tool_calls: {result}")
        except httpx.TimeoutException as e: logger.error(f"Pathos LLM Timeout: {e}"); yield {"type": "error_chunk", "content_error": f"[Pathos LLM call timed out: {e}]"}
        except httpx.RequestError as e: logger.error(f"Pathos LLM RequestError: {e}"); yield {"type": "error_chunk", "content_error": f"[Pathos LLM connection error: {e}]"}
        except httpx.HTTPStatusError as e: error_text = e.response.text[:500] if hasattr(e.response, 'text') else str(e); logger.error(f"Pathos LLM HTTPStatusError {e.response.status_code}: {error_text}"); yield {"type": "error_chunk", "content_error": f"[Pathos LLM error ({e.response.status_code}) - {error_text[:200]}]"}
        except Exception as e: logger.error(f"Pathos LLM general error: {e}", exc_info=True); yield {"type": "error_chunk", "content_error": f"[Error processing Pathos LLM response: {str(e)[:100]}]"}

    async def process_feedback(self, feedback_data: Dict[str, Any]):
        if not self.config.ENABLE_LEARNING_FROM_FEEDBACK: logger.debug("Feedback processing skipped."); return
        required_keys = ['user_id', 'last_user_input', 'last_pathos_response', 'feedback_type']
        if not all(key in feedback_data for key in required_keys): logger.warning(f"Feedback data missing keys. Skipping."); return
        feedback_user_id = feedback_data.get('user_id', self.current_active_user_id)
        logger.info(f"PathosInterface processing feedback for user '{feedback_user_id}': Type '{feedback_data.get('feedback_type')}'.")
        memory_metadata = { "user_id": feedback_user_id, "source": feedback_data.get('source', 'api_feedback_endpoint'), "feedback_timestamp_received_by_api": datetime.now(timezone.utc).isoformat(), "processed_by_reflection": False, **feedback_data }
        feedback_content_str = json.dumps(feedback_data)
        await self.ethos_core.add_memory_entry( {"type": "feedback", "content": feedback_content_str, "metadata": memory_metadata, "salience": 1.2 }, user_id_context=feedback_user_id )
        if self.config.ENABLE_MOOD_SIMULATION: mood_update_payload = {"feedback_type": feedback_data.get("feedback_type"), "rating": feedback_data.get("rating")}; await self.ethos_core.update_mood_state('feedback', mood_update_payload)

    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        logger.info("PathosInterface HTTP client closed.")