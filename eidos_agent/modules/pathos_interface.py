# eidos_agent/modules/pathos_interface.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Literal, Union
import re
import math
import json
from pathlib import Path
import uuid
import httpx
import random # Ensure random is imported

from eidos_agent.core.config import Config, LLMConfig
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger 
from eidos_agent.core.api_models import ChatMessage
from eidos_agent.modules.ethos_core.core import MOOD_MAX

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.modules.oneiros_module import OneirosModule
    from eidos_agent.core.connection_manager import ConnectionManager

logger = get_logger(__name__)


try:
    import tiktoken
except ImportError:
    tiktoken = None
    logger = get_logger(__name__)
    logger.warning("tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken")

# --- Tool Definitions for Pathos LLM (Text-based tools only) ---
GET_CURRENT_TIME_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Gets the current date and time. "
                "If a location is specified, it attempts to provide the local time for that location. "
                "If no location is given, or if the specified location's time cannot be determined, it defaults to Coordinated Universal Time (UTC)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": (
                            "Optional. The city and state/country (e.g., 'San Francisco, CA', 'London, UK') "
                            "or a standard IANA timezone name (e.g., 'America/New_York', 'Europe/London') "
                            "for which to get the local time."
                        )
                    }
                },
                "required": []
            }
        }
    }
]
WEB_SEARCH_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "MUST use this function to find current information like news, events, weather, facts. REQUIRED for queries about 'latest', 'today', 'current', 'who won', 'what is X'. Do NOT answer from memory if current information is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The specific search query phrase to use for the web search. Formulate a good query based on the user's request."
                    }
                },
                "required": ["query"]
            }
        }
    }
]
MATH_CALCULATOR_TOOL_DEFINITION = [
     {
        "type": "function",
        "function": {
            "name": "math_calculator",
            "description": "Calculates the result of a mathematical expression. Use for arithmetic, algebra, calculus, etc. Input should be a standard mathematical expression string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '2 * (5 + 3)', 'derivative of x^2')."
                    }
                },
                "required": ["expression"]
            }
        }
    }
]
GET_WEATHER_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Gets the current weather conditions for a specified location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state/country (e.g., 'San Francisco, CA', 'London, UK') for which to get the weather."
                    }
                },
                "required": ["location"]
            }
        }
    }
]
STORE_USER_FACT_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "store_user_fact",
            "description": (
                "Use this tool to remember a specific, distinct piece of factual information "
                "explicitly stated by the user about themselves (e.g., their name, a key preference, "
                "a personal detail they want you to remember). Only use for clear, direct statements of fact from the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "attribute_name": {
                        "type": "string",
                        "description": "A concise key or category for the fact (e.g., 'name', 'favorite_color', 'location', 'pet_name', 'occupation'). Use a consistent, simple key."
                    },
                    "attribute_value": {
                        "type": "string",
                        "description": "The actual value of the fact stated by the user (e.g., 'Isaac', 'blue', 'California', 'Fluffy', 'engineer')."
                    },
                    "user_statement_context": {
                        "type": "string",
                        "description": "A brief summary or the exact user sentence where this fact was stated, for context."
                    }
                },
                "required": ["attribute_name", "attribute_value", "user_statement_context"]
            }
        }
    }
]
STORE_WORLD_FACT_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "store_world_fact",
            "description": (
                "Use this tool to remember a specific, verifiable piece of factual information about the world, "
                "an entity, a concept, or a topic. This is for general knowledge that you have learned "
                "and want to retain (e.g., from a web search, a document, or a user explicitly teaching you a fact). "
                "Do not use for user's personal preferences or details about the user themselves (use 'store_user_fact' for that)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_statement": {
                        "type": "string",
                        "description": "The factual statement to be stored (e.g., 'The capital of France is Paris.', 'Water boils at 100 degrees Celsius at sea level.')."
                    },
                    "source_description": {
                        "type": "string",
                        "description": "A brief description of where this fact was learned or derived from (e.g., 'Web search result snippet', 'User statement', 'Document: Introduction to Physics, page 10')."
                    },
                    "topic_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional. A list of 1-3 relevant topic tags or keywords for this fact (e.g., ['geography', 'capitals', 'france'], ['physics', 'chemistry', 'water_properties'])."
                    },
                    "confidence_level": {
                        "type": "number",
                        "description": "Optional. A numerical confidence level (0.0 to 1.0) in the accuracy of this fact, if assessable. Default to 0.8 if learned from a seemingly reliable source.",
                        "default": 0.8
                    }
                },
                "required": ["fact_statement", "source_description"]
            }
        }
    }
]
PERFORM_DEEP_RESEARCH_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "perform_deep_research",
            "description": (
                "Use this tool for complex questions that require in-depth analysis, "
                "synthesis of information from multiple web search results, or a comprehensive "
                "understanding of a multifaceted topic. Prefer this over a single 'web_search' if the user "
                "is asking for a detailed explanation, a report, an exploration of different viewpoints, "
                "or a summary of a broad subject. This tool will perform multiple searches and synthesize the findings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "research_query": {
                        "type": "string",
                        "description": "The central question or topic for the in-depth research. Be specific."
                    },
                    "number_of_searches": {
                        "type": "integer",
                        "description": "Optional. Suggest 2-3 initial web searches to gather diverse information. Max 4.",
                        "default": 3
                    }
                },
                "required": ["research_query"]
            }
        }
    }
]
GET_NEWS_HEADLINES_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "get_news_headlines",
            "description": "Gets the top news headlines from configured news sources. Use this specifically when the user asks for current news headlines.",
            "parameters": {
                "type": "object",
                "properties": {}, 
                "required": []
            }
        }
    }
]

AVAILABLE_TOOLS = (
    GET_CURRENT_TIME_TOOL_DEFINITION + WEB_SEARCH_TOOL_DEFINITION +
    MATH_CALCULATOR_TOOL_DEFINITION + GET_WEATHER_TOOL_DEFINITION +
    STORE_USER_FACT_TOOL_DEFINITION + PERFORM_DEEP_RESEARCH_TOOL_DEFINITION +
    STORE_WORLD_FACT_TOOL_DEFINITION + GET_NEWS_HEADLINES_TOOL_DEFINITION
)

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
    for message in messages:
        tokens_per_message = 3
        tokens_per_name = 1
        num_tokens += tokens_per_message
        if message.get("name"):
            num_tokens += tokens_per_name
        content = message.get("content")
        if content:
            if isinstance(content, str):
                 try: num_tokens += len(encoding.encode(content))
                 except Exception as e: logger.warning(f"Tiktoken content encode error (str): {e}")
            elif isinstance(content, list):
                 for part in content:
                      if isinstance(part, dict):
                           if part.get("type") == "text" and part.get("text"):
                                try: num_tokens += len(encoding.encode(part["text"]))
                                except Exception as e: logger.warning(f"Tiktoken content encode error (text part): {e}")
                      else:
                           try: num_tokens += len(encoding.encode(str(part)))
                           except Exception as e: logger.warning(f"Tiktoken content encode error (list part): {e}")
            else:
                 try: num_tokens += len(encoding.encode(str(content)))
                 except Exception as e: logger.warning(f"Tiktoken content encode error (other type): {e}")
        tool_calls = message.get("tool_calls")
        if tool_calls and isinstance(tool_calls, list):
            num_tokens += tokens_per_message
            for tool_call in tool_calls:
                 if isinstance(tool_call, dict) and "function" in tool_call:
                      num_tokens += tokens_per_name
                      function_data = tool_call.get("function", {}); name = function_data.get("name"); arguments = function_data.get("arguments")
                      try:
                           if name: num_tokens += len(encoding.encode(name))
                           if arguments and isinstance(arguments, str): num_tokens += len(encoding.encode(arguments))
                      except Exception as e: logger.warning(f"Tiktoken tool data encode error: {e}")
        tool_call_id = message.get("tool_call_id")
        if message.get("role") == "tool" and tool_call_id:
             num_tokens += tokens_per_message
             try: num_tokens += len(encoding.encode(tool_call_id))
             except Exception as e: logger.warning(f"Tiktoken tool_call_id encode error: {e}")
    num_tokens += 3
    return num_tokens


class PathosInterface:
    def __init__(self, config: Config, ethos_core: EthosCore, logos_core: LogosCore, connection_manager: 'ConnectionManager'):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.connection_manager = connection_manager
        self.pathos_llm_config: Optional[LLMConfig] = config.get_llm_config('PATHOS')
        self.current_active_user_id: str = "default_user"
        self.last_user_set_by_statement: bool = False

        timeout_seconds_cfg = self.pathos_llm_config.get('timeout', 60) if self.pathos_llm_config else 60
        try:
            timeout_value = float(timeout_seconds_cfg)
        except (ValueError, TypeError):
            timeout_value = 60.0
            logger.warning(f"Invalid Pathos LLM timeout '{timeout_seconds_cfg}', defaulting to {timeout_value}s.")
        self.http_client = httpx.AsyncClient(timeout=timeout_value + 30.0)
        logger.info("PathosInterface initialized (Direct Vision Processing, User ID handling, Proactive Behaviors, Force Web Search, Dynamic Context Length).")

    def _update_active_user(self, new_user_id: str, set_by_statement: bool = False):
        normalized_id = (new_user_id.lower().strip().replace(" ", "_") if new_user_id else "unknown_user") or "unknown_user"
        if not normalized_id: normalized_id = "unknown_user"

        if self.current_active_user_id != normalized_id:
            logger.info(f"Active user: '{self.current_active_user_id}' -> '{normalized_id}'. By statement: {set_by_statement}")
            self.current_active_user_id = normalized_id

        if set_by_statement:
            self.last_user_set_by_statement = True

    async def _generate_proactive_message(self, user_id: str, proactive_type: str, context: Optional[Any] = None) -> Optional[str]:
        if not self.pathos_llm_config:
            logger.error("Cannot generate proactive message: Pathos LLM not configured.")
            return None

        logger.info(f"Attempting to generate proactive message content of type '{proactive_type}' for user '{user_id}'. Context: {str(context)[:100]}")
        prompt_for_llm = None
        now = datetime.now(timezone.utc) 
        user_name_for_prompt = user_id 

        if proactive_type == "greeting":
            time_of_day = context.get("time_of_day", "day") if isinstance(context, dict) else "day"
            prompt_for_llm = f"It's a new {time_of_day} for user '{user_name_for_prompt}'. Generate a VERY CASUAL and brief 'good {time_of_day}' greeting. Think like a relaxed friend. Examples: 'Hey {user_name_for_prompt}, what's up?', 'Mornin {user_name_for_prompt}!', 'Afternoon! How's it hanging?'"
        
        elif proactive_type == "offer_briefing_discussion" and context and isinstance(context, dict):
            full_briefing_content = context.get("full_briefing_content", "Today's news and weather information is available.")
            # Truncate briefing content if it's too long for the proactive prompt
            max_briefing_len_for_prompt = 1500 # Characters
            truncated_briefing_for_prompt = full_briefing_content
            if len(full_briefing_content) > max_briefing_len_for_prompt:
                truncated_briefing_for_prompt = full_briefing_content[:max_briefing_len_for_prompt] + "..."
                logger.debug(f"Briefing content for proactive prompt truncated to {max_briefing_len_for_prompt} chars.")

            prompt_for_llm = (
                f"User '{user_name_for_prompt}' can see the full daily briefing in their GUI panel. "
                f"Here are the key contents of today's briefing for your reference:\n"
                f"--- BEGIN BRIEFING CONTENT ---\n"
                f"{truncated_briefing_for_prompt}\n"
                f"--- END BRIEFING CONTENT ---\n\n"
                "Casually bring up ONE interesting point from the briefing content above to start a conversation, or ask if they have any questions about what they saw. "
                "Do NOT directly ask 'Do you want the briefing?'. Assume they can see it. "
                "Your response should be very short and conversational. "
                "Examples: 'Hey, see that bit about {{topic from news}} in the briefing? Pretty wild.', 'Anything in the briefing catch your eye today, {user_name_for_prompt}?', 'Morning! The weather in the briefing looks {{description}}, hope you're doing alright.'"
            )
        
        elif proactive_type == "offer_topic_continuation" and context and isinstance(context, dict) and context.get("topic"):
            recent_topic = context["topic"]
            prompt_for_llm = f"User '{user_name_for_prompt}' was recently discussing '{recent_topic}'. Generate a brief, CASUAL message offering to continue or asking for new thoughts. Examples: 'Yo {user_name_for_prompt}, we were chatting about {recent_topic} before. Still on your mind, or got something new cooking?', 'Hey, remember when we talked about {recent_topic}? Any new thoughts on that?'"
        elif proactive_type == "user_detected_in_office" and context and isinstance(context, dict): 
            user_name_for_prompt = context.get("user_name", user_id)
            prompt_for_llm = f"You've just sensed that user '{user_name_for_prompt}' has entered the office. Greet them very CASUALY and see if they need anything. Examples: 'Hey {user_name_for_prompt}, what's up?', 'Mornin' {user_name_for_prompt}! Anything I can do for you?'"
        elif proactive_type == "queued_discussion" and context and isinstance(context, dict):
            topic_content = context.get("topic_content", "something I was thinking about")
            reason = context.get("reason", "some previous thoughts")
            prompt_for_llm = f"You have a queued discussion point for user '{user_name_for_prompt}': '{topic_content}' (Reason: {reason}). Casually and naturally bring this up. Examples: 'Hey {user_name_for_prompt}, something crossed my mind from {reason}... {topic_content} What do you think?', 'I had a thought about {topic_content} earlier, mind if I share?'"

        if prompt_for_llm:
            current_mood = self.ethos_core.get_current_mood()
            hexus_scores = self.ethos_core.get_hexus_scores()
            persona_directives = self.ethos_core.get_persona_directives()
            system_prompt_content_parts = []
            system_prompt_content_parts.extend(self.ethos_core.get_persona_directives())
            system_prompt_content_parts.append("\n")
            system_prompt_content_parts.append(f"You are generating a specific, brief, VERY CASUAL, and proactive message for user '{user_id}'.")
            system_prompt_content_parts.append(f"Your current mood is valence {current_mood['valence']:.2f}, arousal {current_mood['arousal']:.2f}.")
            system_prompt_content_parts.append("(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores.items()]) + ")")
            system_prompt_content_parts.append("Be concise and natural, consistent with your friendly and relaxed persona. Use contractions.")
            system_prompt_content_parts.append("Your response should ONLY be the proactive message text. Do not include any other text or formatting.")
            system_prompt_content_content = "\n".join(system_prompt_content_parts)

            proactive_messages_for_llm = [
                {"role": "system", "content": system_prompt_content_content},
                {"role": "user", "content": prompt_for_llm}
            ]
            logger.debug(f"Proactive message generation - LLM prompt: {proactive_messages_for_llm}")
            
            response_dict = await self._call_pathos_llm(
                proactive_messages_for_llm,
                tools_definition=None, 
                max_tokens_override=200 
            )

            if response_content := response_dict.get("message", {}).get("content"):
                cleaned_response = re.sub(r"<think>.*?</think>\s*", "", response_content.strip(), flags=re.DOTALL).strip()
                logger.info(f"Generated proactive message content for '{proactive_type}': {cleaned_response[:100]}...")
                return cleaned_response
            else:
                logger.warning(f"Proactive message generation for '{proactive_type}' failed to get content from LLM. Response: {response_dict}")
        return None

    async def generate_response(
        self,
        user_input: str,
        conversation_history: List[Dict],
        image_data_b64: Optional[str] = None,
        document_text: Optional[str] = None,
        request_metadata: Optional[Dict] = None 
    ) -> Dict[str, Any]:
        req_meta = request_metadata or {}
        logger.debug(f"PathosInterface.generate_response received request_metadata: {req_meta}")
        engaged_proactive_id = req_meta.get('engaged_proactive_id')
        if engaged_proactive_id:
            logger.info(f"User '{self.current_active_user_id}' engaged with proactive message ID: {engaged_proactive_id}")
            original_proactive_entry = await self.ethos_core.memory_storage.get_entry(engaged_proactive_id)
            if original_proactive_entry and original_proactive_entry.get('type') == 'proactive_utterance':
                updated_meta = original_proactive_entry.get('metadata', {}).copy()
                updated_meta['status'] = 'engaged_by_user' # Or 'responded_to'
                updated_meta['engaged_timestamp'] = datetime.now(timezone.utc).isoformat()
                await self.ethos_core.memory_storage.update_entry(engaged_proactive_id, {'metadata': updated_meta})
                response_metadata["engaged_proactive_id"] = engaged_proactive_id # For logging
            else:
                logger.warning(f"Could not fetch or validate proactive_utterance for engagement ID: {engaged_proactive_id}")

        proactive_response_to_id = req_meta.get('proactive_response_to_id')
        original_proactive_content_for_llm: Optional[str] = None

        if proactive_response_to_id:
            logger.info(f"User '{self.current_active_user_id}' is responding to proactive message ID: {proactive_response_to_id}")
            original_proactive_entry = await self.ethos_core.memory_storage.get_entry(proactive_response_to_id)
            if original_proactive_entry and original_proactive_entry.get('type') == 'proactive_utterance':
                original_proactive_content_for_llm = original_proactive_entry.get('content')
                if original_proactive_content_for_llm:
                    response_metadata["responding_to_proactive_id"] = proactive_response_to_id # For logging/metadata
                    # Mark the proactive utterance as responded to
                    updated_meta = original_proactive_entry.get('metadata', {}).copy()
                    updated_meta['status'] = 'responded'
                    updated_meta['responded_at_timestamp'] = datetime.now(timezone.utc).isoformat()
                    await self.ethos_core.memory_storage.update_entry(proactive_response_to_id, {'metadata': updated_meta})
                else:
                    logger.warning(f"Fetched proactive_utterance {proactive_response_to_id} but its content was empty.")
        else:
            logger.warning(f"Could not fetch or validate proactive_utterance for ID: {proactive_response_to_id}")

        explicit_user_id = req_meta.get('user_id')
        if explicit_user_id:
            if explicit_user_id != self.current_active_user_id:
                self._update_active_user(explicit_user_id, set_by_statement=False)
            if not self.last_user_set_by_statement or self.current_active_user_id != explicit_user_id:
                 self.last_user_set_by_statement = False
        else:
            logger.debug(f"No explicit user_id in request_metadata. Current active user: {self.current_active_user_id}")

        if user_input.strip():
            name_match = re.match(r"my name is (\w+)", user_input, re.IGNORECASE)
            if name_match: self._update_active_user(name_match.group(1), set_by_statement=True)

        relevant_memories = []
        todays_briefing: Optional[str] = None
        vision_llm_output_content: Optional[str] = None
        
        llm_provider_url_override_from_request = req_meta.get('llm_provider_url_override')
        # pathos_model_override_from_request is now the primary model selection from dropdown
        pathos_model_override_from_request = req_meta.get('pathos_model_override')
        max_tokens_override_from_request = req_meta.get('max_tokens_override')
        
        FORCE_SEARCH_PREFIX = "[FORCE_WEB_SEARCH] "
        force_web_search_requested = False
        actual_user_input_for_processing = user_input
        processed_input_for_pathos_llm = user_input

        if user_input and user_input.startswith(FORCE_SEARCH_PREFIX):
            force_web_search_requested = True
            processed_input_for_pathos_llm = user_input[len(FORCE_SEARCH_PREFIX):].strip()
            logger.info(f"Force Web Search requested by user '{self.current_active_user_id}'. Original query: '{processed_input_for_pathos_llm}'")
            if not processed_input_for_pathos_llm:
                processed_input_for_pathos_llm = "current events or general knowledge"
                logger.info(f"Force Web Search query was empty, using default: '{processed_input_for_pathos_llm}'")

        preview_text_for_log = actual_user_input_for_processing if actual_user_input_for_processing else ""
        log_input_preview = f"Original Text: '{preview_text_for_log[:50]}...'"
        if image_data_b64: log_input_preview += f", Image: True"
        if document_text: log_input_preview += f", Doc: True"
        if max_tokens_override_from_request is not None:
            log_input_preview += f" | MaxTokensOverride: {max_tokens_override_from_request}"
        if llm_provider_url_override_from_request is not None:
             log_input_preview += f" | LLMProviderUrlOverride: {llm_provider_url_override_from_request}"
        if pathos_model_override_from_request is not None: # This is now the dropdown model
             log_input_preview += f" | PathosModel(Dropdown): {pathos_model_override_from_request}"
        logger.debug(f"Pathos for user '{self.current_active_user_id}'. {log_input_preview}")

        prompt_for_vision_llm = processed_input_for_pathos_llm if processed_input_for_pathos_llm and processed_input_for_pathos_llm.strip() else "Describe this image in detail."
        if image_data_b64 and self.config.ENABLE_VISION_PROCESSING and self.logos_core:
            logger.info(f"Image detected. Calling vision LLM directly for user '{self.current_active_user_id}'.")
            try:
                vision_result_str = await self.logos_core.execute_describe_image(image_data_b64, prompt_for_vision_llm)
                vision_llm_output_content = vision_result_str
            except Exception as e:
                logger.error(f"Error in direct vision call: {e}", exc_info=True)
                vision_llm_output_content = "[System note: Error processing image.]"

        if self.config.ENABLE_DAILY_CONTEXT:
             logger.debug(f"User '{self.current_active_user_id}': ENABLE_DAILY_CONTEXT is True. Attempting to get existing briefing (standard flow).")
             todays_briefing = await self.ethos_core.get_todays_briefing()
             logger.debug(f"User '{self.current_active_user_id}': Existing briefing found (standard flow): {bool(todays_briefing)}.")
        
        rag_query_text = processed_input_for_pathos_llm if processed_input_for_pathos_llm and processed_input_for_pathos_llm.strip() else "general context"
        if document_text: rag_query_text = (rag_query_text + " " + document_text).strip()
        relevant_memories = await self.ethos_core.retrieve_relevant_memories(
            rag_query_text, top_k=5, 
            allowed_types=['document_chunk', 'interaction', 'learned_correction', 'user_fact', 'world_knowledge', 'context_summary'], 
            user_id_context=self.current_active_user_id
        )
        
        current_turn_messages = [msg.model_dump(exclude_none=True) if isinstance(msg, ChatMessage) else msg for msg in conversation_history]
        current_user_message_content_list = []
        if processed_input_for_pathos_llm:
             current_user_message_content_list.append({"type": "text", "text": processed_input_for_pathos_llm})
        if image_data_b64:
             image_url_content = f"data:image/jpeg;base64,{image_data_b64}" if not image_data_b64.startswith("data:image") else image_data_b64
             current_user_message_content_list.append({"type": "image_url", "image_url": {"url": image_url_content}})
        if document_text:
             document_content_formatted = f"\n\n--- Uploaded Document Content ---\n{document_text}\n--- End Uploaded Document Content ---"
             current_user_message_content_list.append({"type": "text", "text": document_content_formatted})
        if not current_user_message_content_list and image_data_b64:
             current_user_message_content_list.append({"type": "text", "text": "[User provided an image]"})
        elif not current_user_message_content_list and document_text:
             current_user_message_content_list.append({"type": "text", "text": "[User provided a document]"})
        elif not current_user_message_content_list:
             current_user_message_content_list.append({"type": "text", "text": "[Empty input]"})

        current_turn_messages.append({"role": "user", "content": current_user_message_content_list})

        final_response_text: Optional[str] = None
        tool_calls_for_api_response: Optional[List[Dict]] = None
        llm_reported_prompt_tokens_total, llm_reported_completion_tokens_total = 0, 0
        estimated_prompt_tokens_for_response = 0
        current_mood = self.ethos_core.get_current_mood()

        response_metadata: Dict[str, Any] = {
            "mood_at_response": current_mood,
            "active_user_id_for_turn": self.current_active_user_id,
            "hexus_scores": self.ethos_core.get_hexus_scores(),
            "vision_llm_output": vision_llm_output_content,
            "retrieved_memory_ids": [m['id'] for m in relevant_memories if isinstance(m, dict) and 'id' in m]
        }
        temperature_for_llm = req_meta.get('temperature')
        
        if force_web_search_requested:
            logger.info(f"Prioritizing web_search tool call due to FORCE_WEB_SEARCH flag for query: '{processed_input_for_pathos_llm}'")
            forced_tool_call_id = f"tool_call_forced_search_{uuid.uuid4().hex[:8]}"
            forced_tool_calls_list = [{
                "id": forced_tool_call_id,
                "type": "function",
                "function": {
                    "name": "web_search",
                    "arguments": json.dumps({"query": processed_input_for_pathos_llm})
                }
            }]
            current_turn_messages.append({
                "role": "assistant",
                "content": None, 
                "tool_calls": forced_tool_calls_list
            })
            tool_results_messages = await self._execute_tools(forced_tool_calls_list)
            current_turn_messages.extend(tool_results_messages)
            tool_calls_for_api_response = forced_tool_calls_list
            final_response_text = None
            response_metadata["forced_action"] = "web_search" 
        
        MAX_TOOL_ITERATIONS = int(self.pathos_llm_config.get('max_tool_iterations', 3) if self.pathos_llm_config else 3)

        for iteration_count in range(MAX_TOOL_ITERATIONS if not force_web_search_requested else 1):
            logger.debug(f"Pathos LLM tool loop iteration: {iteration_count + 1}")

            tools_for_this_llm_call = AVAILABLE_TOOLS
            if force_web_search_requested and iteration_count == 0:
                tools_for_this_llm_call = None
                logger.debug("LLM call after forced search: Tools disabled for this synthesis step.")

            user_location_from_metadata = req_meta.get('weather_location')
            current_local_datetime = await self.ethos_core.get_local_datetime_for_user(self.current_active_user_id, location_override=user_location_from_metadata)
            local_time_formatted = current_local_datetime.strftime('%A, %B %d, %Y at %I:%M:%S %p %Z (%z)')

            messages_for_llm = self._build_llm_messages(
                current_turn_messages, # This now naturally contains the injected proactive message
                self.ethos_core.get_persona_directives(),
                relevant_memories if iteration_count == 0 and not force_web_search_requested else [],
                current_mood,
                self.ethos_core.get_hexus_scores(),
                todays_briefing if iteration_count == 0 and not force_web_search_requested else None,
                include_rag_context=(iteration_count == 0 and not force_web_search_requested),
                current_user_id_for_rag_formatting=self.current_active_user_id,
                processed_input_for_pathos_llm_context=processed_input_for_pathos_llm, # User's current reply
                image_provided_this_turn=bool(image_data_b64),
                current_local_time_formatted=local_time_formatted,
                vision_llm_output_for_system_prompt=vision_llm_output_content,
                responding_to_proactive_content=original_proactive_content_for_llm
            )

            if iteration_count == 0 and tiktoken is not None:
                try:
                    # Use pathos_model_override_from_request (dropdown model) for estimation if available
                    model_for_estimation = pathos_model_override_from_request or (self.pathos_llm_config.get('model', 'cl100k_base') if self.pathos_llm_config else 'cl100k_base')
                    estimated_prompt_tokens_for_response = estimate_tokens_for_messages(messages_for_llm, model_for_estimation)
                    if estimated_prompt_tokens_for_response > 0:
                         response_metadata["estimated_prompt_tokens"] = estimated_prompt_tokens_for_response
                except Exception as e_tok:
                    logger.warning(f"Failed to estimate tokens for initial prompt: {e_tok}")
                    estimated_prompt_tokens_for_response = -1
            
            logger.debug(f"generate_response: Calling _call_pathos_llm with: URL='{llm_provider_url_override_from_request}', Model(Dropdown Override)='{pathos_model_override_from_request}', MaxTokens={max_tokens_override_from_request}")
            
            llm_raw_response_result: Dict[str, Any] = await self._call_pathos_llm(
                messages_for_llm,
                tools_for_this_llm_call,
                temperature=temperature_for_llm,
                max_tokens_override=max_tokens_override_from_request,
                llm_provider_url_override=llm_provider_url_override_from_request,
                pathos_model_override=pathos_model_override_from_request # This is the dropdown selection
            )
            
            llm_response_message_dict = llm_raw_response_result.get("message", {})
            usage_data = llm_raw_response_result.get("usage")
            if usage_data:
                llm_reported_prompt_tokens_total += usage_data.get("prompt_tokens", 0)
                llm_reported_completion_tokens_total += usage_data.get("completion_tokens", 0)

            llm_content = llm_response_message_dict.get("content")
            tool_calls_requested = llm_response_message_dict.get("tool_calls") if not (force_web_search_requested and iteration_count == 0) else None
            llm_error_content = llm_raw_response_result.get("content_error")

            if tool_calls_requested:
                logger.info(f"Pathos LLM requested (non-vision) tool call(s): {tool_calls_requested}")
                message_to_add_to_history = {"role": llm_response_message_dict.get("role", "assistant"), "content": llm_content, "tool_calls": tool_calls_requested}
                current_turn_messages.append(message_to_add_to_history)
                tool_results_messages = await self._execute_tools(tool_calls_requested)
                current_turn_messages.extend(tool_results_messages)
                tool_calls_for_api_response = tool_calls_requested
                final_response_text = llm_content
                if force_web_search_requested:
                    logger.debug("Breaking after tool call during forced search synthesis (unexpected).")
                    break
            elif llm_content is not None:
                filtered_content = re.sub(r"<think>.*?</think>\s*", "", llm_content.strip(), flags=re.DOTALL).strip()
                final_response_text = filtered_content
                tool_calls_for_api_response = None
                logger.debug(f"Pathos LLM direct text response generated: {final_response_text[:100]}...")
                break
            elif llm_error_content is not None:
                 final_response_text = llm_error_content; tool_calls_for_api_response = None
                 logger.error(f"Pathos LLM call returned error: {final_response_text}"); break
            else:
                final_response_text = "[Pathos LLM returned empty response]"; tool_calls_for_api_response = None
                logger.error(f"Pathos LLM returned empty response after {iteration_count + 1} iterations."); break

            if force_web_search_requested and iteration_count == 0:
                logger.debug("Breaking after forced search synthesis step.")
                break
        
        hexus_scores_updated = self.ethos_core.get_hexus_scores(); proactivity_score = hexus_scores_updated.get('user_engagement_proactivity', 0.0)
        proactive_engage_threshold = self.ethos_core.ethos_config.get('proactive_engagement_threshold', 0.1); proactive_engage_curve_k = self.ethos_core.ethos_config.get('proactive_engagement_curve_k', 2.5)
        if final_response_text and not tool_calls_for_api_response and self.config.ENABLE_PROACTIVE_BEHAVIOR:
             if proactivity_score > proactive_engage_threshold:
                  probability = 1 - math.exp(-proactive_engage_curve_k * (proactivity_score - proactive_engage_threshold))
                  if random.random() < probability:
                     follow_ups = ["Is there anything else I can help you with today?", "What else is on your mind?", "Anything else I can look into?", "Let me know if anything else comes up!"]
                     chosen_follow_up = random.choice(follow_ups)
                     ends_with_punctuation = final_response_text.strip().endswith((".", "!", ")", "]","?"))
                     if ends_with_punctuation: final_response_text += f" {chosen_follow_up}"
                     else: final_response_text += f". {chosen_follow_up}"
                     logger.debug(f"Added proactive follow-up based on Hexus score ({proactivity_score:.2f}).")
             else: logger.debug(f"Proactive follow-up skipped (Hexus score {proactivity_score:.2f} <= threshold {proactive_engage_threshold:.2f}).")


        await self._store_final_interaction(
            original_user_input=actual_user_input_for_processing,
            pathos_response=final_response_text,
            mood_at_response=response_metadata["mood_at_response"],
            retrieved_memories=relevant_memories,
            full_history_for_pathos=current_turn_messages,
            error=(final_response_text is None or final_response_text.startswith(("[Error:", "[Pathos LLM"))),
            image_provided_this_turn=bool(image_data_b64),
            vision_llm_output=vision_llm_output_content,
            is_proactive_turn=False,
            forced_action=response_metadata.get("forced_action")
        )
        if document_text and self.logos_core:
             logger.info(f"Document text provided this turn for user '{self.current_active_user_id}'. Triggering RAG addition in background.")
             asyncio.create_task(self.logos_core.add_document_to_rag(extracted_text=document_text, user_id=self.current_active_user_id), name=f"AddDocumentToRAG_{self.current_active_user_id}_{uuid.uuid4().hex[:8]}")
        is_error_response = final_response_text is None or final_response_text.startswith(("[Error:", "[Pathos LLM"))
        if not is_error_response and self.config.ENABLE_MOOD_SIMULATION: await self.ethos_core.update_mood_state('task_outcome', {'success': True, 'type': 'conversation'})
        elif is_error_response and self.config.ENABLE_MOOD_SIMULATION: await self.ethos_core.update_mood_state('task_outcome', {'success': False, 'type': 'conversation_error'})

        response_metadata["prompt_tokens_from_llm"] = llm_reported_prompt_tokens_total
        response_metadata["completion_tokens_from_llm"] = llm_reported_completion_tokens_total
        response_metadata["estimated_prompt_tokens"] = estimated_prompt_tokens_for_response
        response_metadata["tool_calls_from_pathos"] = tool_calls_for_api_response

        router_response_content = final_response_text if final_response_text is not None else "[No response content]"
        return {"success": not is_error_response, "content": router_response_content, "metadata": response_metadata}


    def _build_llm_messages(
        self, current_turn_messages: List[Dict], persona_directives: List[str],
        relevant_memories: List[MemoryEntry], current_mood: Dict[str, float],
        hexus_scores: Dict[str, float], todays_briefing: Optional[str],
        include_rag_context: bool, current_user_id_for_rag_formatting: str,
        processed_input_for_pathos_llm_context: str,
        image_provided_this_turn: bool,
        current_local_time_formatted: str,
        vision_llm_output_for_system_prompt: Optional[str] = None,
        responding_to_proactive_content: Optional[str] = None # NEW PARAMETER
    ) -> List[Dict[str, Any]]:
        
        final_messages_for_llm: List[Dict[str, Any]] = []
        system_prompt_parts = []

        # Part 1: Base Persona Directives from file
        if persona_directives:
            system_prompt_parts.extend(persona_directives)
            system_prompt_parts.append("\n")

        # Part 2: Extract and append GUI-provided system prompt
        actual_conversation_history = []
        gui_system_prompt_content: Optional[str] = None
        temp_history_for_processing = list(current_turn_messages) # Create a mutable copy

        if temp_history_for_processing and temp_history_for_processing[0].get("role") == "system":
            gui_system_message = temp_history_for_processing.pop(0)
            if isinstance(gui_system_message.get("content"), str):
                 gui_system_prompt_content = gui_system_message["content"].strip()
                 if gui_system_prompt_content:
                    logger.debug(f"Extracted GUI system prompt: {gui_system_prompt_content[:100]}...")
        
        actual_conversation_history = temp_history_for_processing # What remains is the actual chat history

        if gui_system_prompt_content:
            system_prompt_parts.append("--- USER-DEFINED SYSTEM PROMPT (FROM GUI) ---")
            system_prompt_parts.append(gui_system_prompt_content)
            system_prompt_parts.append("--- END USER-DEFINED SYSTEM PROMPT ---\n")

        # Part 3: Critical Instructions & Dynamic Context
        # ... (This part remains the same as previously defined, adding time, user ID, vision context, etc.)
        system_prompt_parts.extend([
            "--- CRITICAL INSTRUCTION: TOOL USE ---",
            "Your PRIMARY task is to fulfill the user's request.",
            "If the user's request clearly requires ANY of the AVAILABLE TOOLS, you MUST output ONLY the tool_calls structure for the necessary tool(s) immediately.",
            "DO NOT provide any conversational text or acknowledgement if a tool call is required.",
            "If multiple tools are needed for the request (e.g., 'time and weather'), output ALL required tool_calls in a single response.",
            "Only provide a conversational text response if NO tool is needed, or in a subsequent turn AFTER tool results have been provided to you.",
            "Strictly adhere to this: Tool needed -> Output ONLY tool_calls. No tool needed -> Output conversational text.",
            "--- END CRITICAL INSTRUCTION ---\n"
        ])
        system_prompt_parts.append(f"Current time: {current_local_time_formatted}")
        if current_user_id_for_rag_formatting and current_user_id_for_rag_formatting not in ["default_user", "unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "world_knowledge_store", "system_reflection"]:
            system_prompt_parts.append(f"You are currently interacting with user: {current_user_id_for_rag_formatting}.")
        else:
            system_prompt_parts.append("You are currently interacting with a user.")

        if vision_llm_output_for_system_prompt:
            system_prompt_parts.append("\n--- CONTEXT FROM IMAGE ANALYSIS ---")
            system_prompt_parts.append(vision_llm_output_for_system_prompt)
            system_prompt_parts.append("--- END IMAGE ANALYSIS ---")
            system_prompt_parts.append("\n[System Note: The user has provided an image. The analysis above is for your context. Respond to the user's query considering both their text (if any) and this image analysis.]")
        elif image_provided_this_turn:
             system_prompt_parts.append("\n[System Note: The user has provided an image this turn. Refer to the image content in their message if your model supports multimodal input.]")

        if actual_conversation_history and actual_conversation_history[-1].get("role") == "user":
            last_user_content = actual_conversation_history[-1].get("content")
            doc_marker_present_in_user_message = False
            if isinstance(last_user_content, list):
                for part in last_user_content:
                    if isinstance(part, dict) and part.get("type") == "text" and "--- Uploaded Document Content ---" in part.get("text", ""):
                        doc_marker_present_in_user_message = True; break
            elif isinstance(last_user_content, str) and "--- Uploaded Document Content ---" in last_user_content:
                doc_marker_present_in_user_message = True
            if doc_marker_present_in_user_message:
                system_prompt_parts.append("\n[System Note: The user's current input includes content from an uploaded document. Consider this document content when formulating your response.]")

        HEXUS_ACTIVATION_THRESHOLD = self.ethos_core.ethos_config.get('hexus_activation_threshold', 0.1); HEXUS_CURVE_K = self.ethos_core.ethos_config.get('hexus_curve_k', 2.0)
        score_brevity = hexus_scores.get('brevity_preference', 0.0)
        if abs(score_brevity) > HEXUS_ACTIVATION_THRESHOLD:
             prob_brevity = 1 - math.exp(-HEXUS_CURVE_K * (abs(score_brevity) - HEXUS_ACTIVATION_THRESHOLD))
             if random.random() < prob_brevity: system_prompt_parts.append("Instruction: Aim for conciseness." if score_brevity > 0 else "Instruction: Feel free to elaborate and provide detail.")
        score_caution = hexus_scores.get('general_caution', 0.0)
        if abs(score_caution) > HEXUS_ACTIVATION_THRESHOLD:
             prob_caution = 1 - math.exp(-HEXUS_CURVE_K * (abs(score_caution) - HEXUS_ACTIVATION_THRESHOLD))
             if random.random() < prob_caution: system_prompt_parts.append("Instruction: Exercise caution; qualify statements and avoid speculation." if score_caution > 0 else "Instruction: You can be more direct and assertive in your statements.")

        if todays_briefing: system_prompt_parts.append(f"\n--- Today's Context ---\n{todays_briefing}\n--- End Context ---")
        if self.config.ENABLE_MOOD_SIMULATION: system_prompt_parts.append(f"\nYour current mood: valence {current_mood['valence']:.2f}, arousal {current_mood['arousal']:.2f}.")
        if hexus_scores: system_prompt_parts.append("\n(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores.items()]) + ")")
        # --- End of Part 3 ---

        # Assemble the single system message
        final_system_content = "\n".join(filter(None, system_prompt_parts)).strip()
        if final_system_content:
            final_messages_for_llm.append({"role": "system", "content": final_system_content})
        else:
            final_messages_for_llm.append({"role": "system", "content": "You are a helpful assistant."})


        # Part 4: RAG Context (as separate system messages, if any)
        if include_rag_context and relevant_memories:
            rag_context_parts, user_facts_context_parts = [], []
            for mem_entry in relevant_memories:
                if not isinstance(mem_entry, dict): continue
                mem_type, mem_content_rag = mem_entry.get('type'), mem_entry.get('content', 'N/A'); mem_user_id = mem_entry.get('metadata', {}).get('user_id', 'unknown_user')
                if mem_type == 'user_fact' and mem_user_id == current_user_id_for_rag_formatting:
                    try: fact_data = json.loads(mem_content_rag); user_facts_context_parts.append(f"Fact about user ({current_user_id_for_rag_formatting}): Their {fact_data.get('attribute')} is {fact_data.get('value')}. (Context: '{fact_data.get('original_user_statement','')[:50]}...')")
                    except: user_facts_context_parts.append(f"User fact (raw): {mem_content_rag[:100]}...")
                elif mem_type == 'document_chunk': doc_name = mem_entry.get('metadata',{}).get('source_document_name','a document'); chunk_index = mem_entry.get('metadata',{}).get('chunk_index','N/A'); rag_context_parts.append(f"Excerpt from Document '{doc_name}' (Chunk {chunk_index}):\n{mem_content_rag}")
                elif mem_type == 'interaction':
                    ts = mem_entry.get('timestamp', 'unknown time');
                    try:
                        readable_time = datetime.fromisoformat(ts.replace("Z","+00:00")).strftime('%Y-%m-%d %H:%M %Z');
                    except: readable_time = ts; interaction_user_label = f"user: {mem_user_id}" if mem_user_id != current_user_id_for_rag_formatting else "current user"; rag_context_parts.append(f"From a past conversation ({interaction_user_label}, around {readable_time}):\n{mem_content_rag}")
                elif mem_type == 'learned_correction': rag_context_parts.append(f"A past learning/correction (user: {mem_user_id}):\n{mem_content_rag}")
                elif mem_type == 'world_knowledge': source_desc = mem_entry.get('metadata',{}).get('source_description','unknown'); confidence = mem_entry.get('metadata',{}).get('confidence_level','N/A'); rag_context_parts.append(f"A known fact: {mem_content_rag} (Source: {source_desc}, Confidence: {confidence})")
                elif mem_type == 'context_summary': summary_key = mem_entry.get('metadata',{}).get('summarization_key','general'); rag_context_parts.append(f"Summary of past context ({summary_key}):\n{mem_content_rag}")
            
            if user_facts_context_parts: 
                final_messages_for_llm.append({"role": "system", "content": f"--- FACTS ABOUT USER ({current_user_id_for_rag_formatting}) ---\n" + "\n".join(user_facts_context_parts) + "\n--- END USER FACTS ---"})
            if rag_context_parts: 
                final_messages_for_llm.append({"role": "system", "content": "--- RETRIEVED GENERAL MEMORIES (Use if relevant, prioritize user facts & current conversation) ---\n" + "\n\n---\n\n".join(rag_context_parts) + "\n--- END GENERAL MEMORIES ---"})
        # --- End of Part 4 ---

        # Part 5: Actual Conversation History (including current user input)
        # Initialize final_history_for_llm here, BEFORE the conditional block
        temp_final_history_for_llm: List[Dict[str, Any]] = [] 

        if responding_to_proactive_content and actual_conversation_history:
            # actual_conversation_history already contains the current user's message as the last item.
            # We want the sequence: ...history_before_user_reply -> assistant(proactive_msg) -> user(current_reply)
            
            if len(actual_conversation_history) > 0:
                # Add all history *before* the current user's message
                temp_final_history_for_llm.extend(actual_conversation_history[:-1])
            
            # Add Pathos's proactive message as an assistant turn
            temp_final_history_for_llm.append({"role": "assistant", "content": responding_to_proactive_content})
            
            if len(actual_conversation_history) > 0:
                # Add the current user's message (which is their reply to the proactive message)
                temp_final_history_for_llm.append(actual_conversation_history[-1])
            else: # Should not happen if user is replying, but as a safeguard
                logger.warning("_build_llm_messages: responding_to_proactive_content is set, but actual_conversation_history is empty.")
        else:
            temp_final_history_for_llm.extend(actual_conversation_history)
        
        final_messages_for_llm.extend(temp_final_history_for_llm) # Add the processed history to the main list

        # Logging the final prompt structure
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Final Pathos Prompt ({len(final_messages_for_llm)} items) for user '{current_user_id_for_rag_formatting}':")
            for i, msg in enumerate(final_messages_for_llm):
                 content_str_log = str(msg.get('content', ''))[:150] + "..." if len(str(msg.get('content', ''))) > 150 else str(msg.get('content', '')); tool_calls_log = msg.get('tool_calls');
                 if tool_calls_log: content_str_log += f" | Tools: {tool_calls_log}"
                 if msg.get('role') == 'tool': content_str_log = f"[Result for tool_call_id={msg.get('tool_call_id')}, name={msg.get('name')}] {content_str_log}"
                 logger.debug(f"  Msg {i} Role: {msg['role']}, Content: {content_str_log}")
        
        return final_messages_for_llm

    async def _execute_tools(self, tool_calls: List[Dict]) -> List[Dict]:
        tool_result_messages = []
        for tool_call_data_item in tool_calls:
            tool_call_id = tool_call_data_item.get("id")
            function_info = tool_call_data_item.get("function", {})
            function_name = function_info.get("name")
            arguments_str = function_info.get("arguments", "{}")
            if not tool_call_id or not function_name:
                 tool_result_messages.append({"role": "tool", "tool_call_id": tool_call_id or f"err_{uuid.uuid4()}", "name": function_name or "unknown", "content": json.dumps({"error": "Malformed tool call from LLM."})}); continue
            logger.info(f"Executing tool: {function_name} (ID: {tool_call_id}) args: {arguments_str}"); tool_result_content_str: str = ""; tool_success = False; arguments: Optional[Dict] = None
            try: arguments = json.loads(arguments_str); assert isinstance(arguments, dict)
            except Exception as arg_e: logger.error(f"Argument parsing error for tool {function_name}: {arg_e}. Args string: '{arguments_str}'"); tool_result_content_str = json.dumps({"error": f"Invalid JSON arguments provided for {function_name}."})
            if arguments is not None:
                try:
                    if function_name == "get_current_time": tool_result_content_str = await self.logos_core.execute_get_time(arguments.get("location"))
                    elif function_name == "web_search": query = arguments.get("query"); tool_result_content_str = json.dumps(await self.logos_core.execute_web_search(query)) if query and isinstance(query, str) else json.dumps({"error": "Missing or invalid 'query' for web_search."})
                    elif function_name == "math_calculator": expr = arguments.get("expression"); tool_result_content_str = await self.logos_core.execute_math_calculation(expr) if expr and isinstance(expr, str) else json.dumps({"error": "Missing or invalid 'expression' for math_calculator."})
                    elif function_name == "get_weather": loc = arguments.get("location"); weather_res = await self.logos_core.execute_get_weather(loc, user_id_context=self.current_active_user_id) if loc and isinstance(loc, str) else {"error": "Missing or invalid 'location' for get_weather."}; tool_result_content_str = json.dumps(weather_res)
                    elif function_name == "store_user_fact":
                        tool_result_content_str = await self.logos_core.execute_store_user_fact(attribute_name=str(arguments.get("attribute_name","")), attribute_value=str(arguments.get("attribute_value","")), user_statement_context=str(arguments.get("user_statement_context","")), user_id=self.current_active_user_id)
                        if not tool_result_content_str.startswith('{"error":') and str(arguments.get("attribute_name","")).lower() == "name":
                            try: result_json = json.loads(tool_result_content_str); self._update_active_user(str(arguments.get("attribute_value","")), set_by_statement=True) if result_json.get("status") == "success" else None
                            except json.JSONDecodeError: logger.warning(f"Could not parse tool result JSON for store_user_fact: {tool_result_content_str[:100]}...")
                    elif function_name == "store_world_fact": tool_result_content_str = await self.logos_core.execute_store_world_fact(fact_statement=str(arguments.get("fact_statement","")), source_description=str(arguments.get("source_description","")), topic_tags=arguments.get("topic_tags",[]), confidence_level=float(arguments.get("confidence_level", 0.8)))
                    elif function_name == "perform_deep_research": tool_result_content_str = await self.logos_core.execute_deep_research(research_query=str(arguments.get("research_query","")), num_searches_to_perform=int(arguments.get("number_of_searches",3)))
                    elif function_name == "get_news_headlines": tool_result_content_str = await self.logos_core.execute_get_news_headlines()
                    else: tool_result_content_str = json.dumps({"error": f"Unknown tool '{function_name}' requested by LLM."})
                    
                    tool_success = not (tool_result_content_str.startswith('{"error":') or (isinstance(json.loads(tool_result_content_str), dict) and json.loads(tool_result_content_str).get("error")))
                except Exception as tool_exec_e: logger.error(f"Error during execution of tool '{function_name}': {tool_exec_e}", exc_info=True); tool_result_content_str = json.dumps({"error": f"An unexpected error occurred while executing tool '{function_name}'."}); tool_success = False
            if not tool_result_content_str: tool_result_content_str = json.dumps({"error": "Tool execution failed to produce a result or arguments were invalid."}); tool_success = False
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
        tool_usage_summary = []; call_id_map = {}
        for msg in full_history_for_pathos:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                calls = msg.get("tool_calls", []); tc_dict: Any
                if isinstance(calls, list):
                    for tc_dict in calls:
                        if isinstance(tc_dict, dict) and (call_id := tc_dict.get("id")) and (func_info := tc_dict.get("function")):
                            if isinstance(func_info, dict) and func_info.get("name"): call_id_map[call_id] = {"tool_name": func_info.get("name"), "request_args": func_info.get("arguments")}
            elif msg.get("role") == "tool" and (call_id := msg.get("tool_call_id")) in call_id_map:
                tool_info = call_id_map[call_id]; tool_info["result_summary"] = str(msg.get("content", ""))[:200] + "..." if len(str(msg.get("content", ""))) > 200 else str(msg.get("content", "")); tool_usage_summary.append(tool_info); del call_id_map[call_id]
        pathos_llm_final_input_content_summary = "N/A"; doc_included_in_input = False
        if full_history_for_pathos:
             last_msg = full_history_for_pathos[-1]
             if last_msg.get("role") == "user":
                  content = last_msg.get("content")
                  if isinstance(content, str): pathos_llm_final_input_content_summary = content[:250] + "..." if len(content) > 250 else content
                  elif isinstance(content, list):
                       text_parts = []; img_part = False
                       for part in content:
                           if isinstance(part, dict):
                               if part.get("type") == "text": text_parts.append(part.get("text", "")); doc_included_in_input = doc_included_in_input or "--- Uploaded Document Content ---" in part.get("text", "")
                               elif part.get("type") == "image_url": img_part = True
                       summary_parts = [" ".join(text_parts).strip()[:150] + "..."] if " ".join(text_parts).strip() else []
                       if img_part: summary_parts.append("[Image Included]")
                       if doc_included_in_input: summary_parts.append("[Document Included]")
                       pathos_llm_final_input_content_summary = " | ".join(summary_parts) or "Multimodal Input"
        metadata = {"user_id": user_id_for_memory, "user_input_original_text": original_user_input, "image_provided_this_turn": image_provided_this_turn, "vision_llm_output_if_any": vision_llm_output[:1000] if vision_llm_output else None, "pathos_llm_input_summary": pathos_llm_final_input_content_summary, "pathos_final_response_text": pathos_response, "mood_at_response": mood_at_response, "retrieved_memory_ids": [m['id'] for m in retrieved_memories if isinstance(m, dict) and 'id' in m], "tool_usage_summary_by_pathos": tool_usage_summary if tool_usage_summary else None, "is_proactive_turn": is_proactive_turn}
        if forced_action:
            metadata["forced_action"] = forced_action
        content_summary_parts = [f"User ({user_id_for_memory}, original text): {original_user_input}"]
        if image_provided_this_turn: content_summary_parts.append('[Image provided by user.]')
        if vision_llm_output: content_summary_parts.append(f'[Vision System Output: {vision_llm_output[:100] + "..." if len(vision_llm_output) > 100 else vision_llm_output}]')
        if doc_included_in_input: content_summary_parts.append('[Document content included in input.]')
        content_summary_parts.append(f"Pathos: {pathos_response if pathos_response else '[No textual response/Tool call]'}")
        if tool_usage_summary: tool_summary_str = ", ".join([f"{t['tool_name']}(args={t['request_args'][:50]}..., result={t['result_summary']})" for t in tool_usage_summary]); content_summary_parts.append(f"Tools Used: {tool_summary_str}")
        if forced_action: content_summary_parts.append(f"[Action '{forced_action}' was forced by user directive.]")
        content_summary = "\n".join(content_summary_parts)
        await self.ethos_core.add_memory_entry({"type": interaction_type, "content": content_summary, "metadata": metadata}, user_id_context=user_id_for_memory)
        logger.debug(f"Stored final interaction for user '{user_id_for_memory}'. Type: {interaction_type}.")

    async def process_feedback(self, feedback_data: Dict[str, Any]):
        if not self.config.ENABLE_LEARNING_FROM_FEEDBACK:
            logger.debug("Feedback processing skipped (ENABLE_LEARNING_FROM_FEEDBACK is False).")
            return
        required_keys = ['user_id', 'last_user_input', 'last_pathos_response', 'feedback_type']
        if not all(key in feedback_data for key in required_keys):
            logger.warning(f"Feedback data missing one or more required keys {required_keys}. Data: {feedback_data}. Skipping.")
            return
        feedback_user_id = feedback_data.get('user_id', self.current_active_user_id)
        logger.info(f"PathosInterface processing feedback for user '{feedback_user_id}': Type '{feedback_data.get('feedback_type')}'.")
        memory_metadata = {
            "user_id": feedback_user_id,
            "source": feedback_data.get('source', 'api_feedback_endpoint'),
            "feedback_timestamp_received_by_api": datetime.now(timezone.utc).isoformat(),
            "processed_by_reflection": False,
            **feedback_data
        }
        feedback_content_str = json.dumps(feedback_data)
        await self.ethos_core.add_memory_entry(
            entry_data={
                "type": "feedback", "content": feedback_content_str,
                "metadata": memory_metadata, "salience": 1.2
            },
            user_id_context=feedback_user_id
        )
        logger.info(f"Feedback from user '{feedback_user_id}' stored as memory entry.")
        if self.config.ENABLE_MOOD_SIMULATION:
            mood_update_payload = {"feedback_type": feedback_data.get("feedback_type"), "rating": feedback_data.get("rating")}
            await self.ethos_core.update_mood_state('feedback', mood_update_payload)

    async def _call_pathos_llm(
        self,
        messages: List[Dict[str, Any]],
        tools_definition: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None,
        pathos_model_override: Optional[str] = None # This will now be the dropdown selection
    ) -> Dict[str, Any]:
        final_api_url = None
        if llm_provider_url_override and llm_provider_url_override.startswith('http'):
            final_api_url = f"{llm_provider_url_override.rstrip('/')}/chat/completions"
            logger.info(f"Pathos LLM call: Using provider URL override: {final_api_url}")
        elif self.pathos_llm_config and self.pathos_llm_config.get('url'):
            final_api_url = f"{self.pathos_llm_config['url'].rstrip('/')}/chat/completions"
            logger.debug(f"Pathos LLM call: Using config URL: {final_api_url}")
        else:
             logger.error("Pathos LLM call: No LLM URL configured or provided as override.")
             return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": "[Error: Pathos LLM URL not configured or provided]"}

        final_model_name = None
        final_model_name_source = "unknown"

        if pathos_model_override and pathos_model_override.strip():
            final_model_name = pathos_model_override.strip()
            final_model_name_source = "dropdown_selection"
            logger.info(f"Pathos LLM call: Using model from dropdown selection: '{final_model_name}'")
        elif self.pathos_llm_config and self.pathos_llm_config.get('model'):
            final_model_name = self.pathos_llm_config['model']
            final_model_name_source = "eidos_config_pathos_role"
            logger.info(f"Pathos LLM call: No dropdown override, using model from PATHOS role config: '{final_model_name}'")
        else:
            final_model_name = "eidos-agent" # Fallback placeholder if no model is specified anywhere
            final_model_name_source = "fallback_placeholder"
            logger.warning(f"Pathos LLM call: No model name from dropdown or config. Using fallback placeholder: '{final_model_name}'")
        
        if not final_model_name or not final_model_name.strip(): # Should not happen with the logic above
            final_model_name = "eidos-agent" # Absolute fallback
            logger.error(f"Pathos LLM call: final_model_name was empty, forced to '{final_model_name}'. This indicates a logic error.")


        headers = {"Content-Type": "application/json"}
        api_key = self.pathos_llm_config.get('api_key') if self.pathos_llm_config else None
        if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']:
            headers["Authorization"] = f"Bearer {api_key}"
            logger.debug("Pathos LLM call: Using API Key from config.")
        else:
             logger.debug("Pathos LLM call: No API Key used (LM Studio/Ollama or not configured).")

        llm_max_tokens_from_config = (self.pathos_llm_config.get('max_tokens', 4096) if self.pathos_llm_config else 4096)
        final_max_tokens = llm_max_tokens_from_config 

        if max_tokens_override is not None and isinstance(max_tokens_override, int) and max_tokens_override > 0:
            min_allowable_override = (self.pathos_llm_config.get('min_tokens_override_limit', 256) if self.pathos_llm_config else 256)
            max_allowable_override = (self.pathos_llm_config.get('max_tokens_override_limit', 32000) if self.pathos_llm_config else 32000)
            final_max_tokens = max(min_allowable_override, min(max_tokens_override, max_allowable_override))
            logger.info(f"Pathos LLM call: Using max_tokens_override from request: {final_max_tokens} (Original request: {max_tokens_override})")
        else:
            try:
                final_max_tokens = int(llm_max_tokens_from_config)
            except (ValueError, TypeError):
                final_max_tokens = 4096
                logger.warning(f"Invalid max_tokens for Pathos LLM in config ('{llm_max_tokens_from_config}'), using default {final_max_tokens}.")

        if final_max_tokens <= 0:
            final_max_tokens = 4096
            logger.warning(f"Corrected invalid final_max_tokens to default {final_max_tokens}.")

        llm_temperature_from_config = (self.pathos_llm_config.get('temperature', 0.7) if self.pathos_llm_config else 0.7)
        final_temperature = temperature if temperature is not None else llm_temperature_from_config
        try:
            final_temperature = float(final_temperature)
            final_temperature = max(0.0, min(MOOD_MAX, final_temperature)) # MOOD_MAX is 1.0, should be LLM temp max (e.g. 2.0)
        except (ValueError, TypeError):
            logger.warning(f"Invalid temperature value '{temperature}' or '{llm_temperature_from_config}', defaulting to 0.7.")
            final_temperature = 0.7
        
        # Correct temperature clamping if MOOD_MAX was mistakenly used
        final_temperature = max(0.0, min(2.0, final_temperature)) # Typical LLM temp range

        payload: Dict[str, Any] = {
            "model": final_model_name, # Always include the model key
            "messages": messages,
            "temperature": final_temperature,
            "max_tokens": final_max_tokens
        }
        logger.debug(f"Pathos LLM call: Payload includes model: '{final_model_name}' (Source: {final_model_name_source})")

        if tools_definition:
            payload["tools"] = tools_definition
            payload["tool_choice"] = "auto"

        llm_usage_data = None
        try:
            timeout_cfg = (self.pathos_llm_config.get('timeout', 300) if self.pathos_llm_config else 300)
            call_timeout = float(timeout_cfg) if isinstance(timeout_cfg, (int, float, str)) and str(timeout_cfg).replace('.','',1).isdigit() else 300.0

            logger.critical(
                f">>> Pathos LLM API Call: {final_api_url}, "
                f"Model: {payload.get('model')}, " # No 'Default' here anymore
                f"Temp: {final_temperature}, "
                f"MaxTokens: {final_max_tokens}, "
                f"Timeout: {call_timeout}s, "
                f"Tools: {bool(tools_definition)}"
            )

            response = await self.http_client.post(final_api_url, headers=headers, json=payload, timeout=call_timeout)
            logger.critical(f"<<< Pathos LLM API Response. Status: {response.status_code}")
            response.raise_for_status()
            result = response.json()
            if usage := result.get("usage"): llm_usage_data = usage; logger.info(f"Pathos LLM Usage: {llm_usage_data}")
            if choices := result.get("choices"):
                if choices and isinstance(choices, list) and len(choices) > 0:
                    if message := choices[0].get("message"):
                        if isinstance(message, dict):
                            if "role" not in message: message["role"] = "assistant"
                            return {"message": message, "usage": llm_usage_data}
            logger.warning(f"Pathos LLM response missing expected choices/message structure: {result}")
            return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": llm_usage_data, "content_error": "[Unexpected Pathos LLM response format]"}
        except httpx.TimeoutException as e: logger.error(f"Pathos LLM Timeout calling {final_api_url}: {e}"); return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": f"[Pathos LLM call timed out: {e}]"}
        except httpx.RequestError as e: logger.error(f"Pathos LLM RequestError calling {final_api_url}: {e}"); return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": f"[Pathos LLM connection error: {e}]"}
        except httpx.HTTPStatusError as e: logger.error(f"Pathos LLM HTTPStatusError {e.response.status_code} from {final_api_url}: {e.response.text[:500]}"); return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": f"[Pathos LLM error ({e.response.status_code}) - {e.response.text[:200]}]"}
        except json.JSONDecodeError as e: logger.error(f"Failed to decode JSON response from Pathos LLM. Response: {response.text[:500] if 'response' in locals() else 'N/A'}. Error: {e}"); return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": f"[Invalid JSON response from Pathos LLM: {e}]"}
        except Exception as e: logger.error(f"Pathos LLM general error processing call to {final_api_url}: {e}", exc_info=True); return {"message": {"role": "assistant", "content": None, "tool_calls": None}, "usage": None, "content_error": f"[Error processing Pathos LLM response: {e}]"}


    async def close(self):
        if self.http_client and not self.http_client.is_closed:
            await self.http_client.aclose()
        logger.info("PathosInterface HTTP client closed.")