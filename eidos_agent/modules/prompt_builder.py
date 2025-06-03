"""
Handles the construction of prompts for LLM interactions within the Eidos agent,
particularly for the Pathos Subconscious Node.
"""
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Union

from eidos_agent.core.config import Config, LLMConfig # Assuming LLMConfig is needed, or just Config
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore # For execute_get_time
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.prompt_loader import load_system_prompt
from eidos_agent.utils.logger import get_logger # Use consistent logger

# Import tool definitions
from eidos_agent.modules.pathos_tools_definitions import (
    AVAILABLE_TOOLS_FOR_PATHOS_LLM,
    # ALL_AVAILABLE_SYSTEM_TOOLS # Not directly used in this version of PromptBuilder
)

# Import the enricher function
from eidos_agent.core.prompting.context_enricher import enrich_prompt_with_subconscious

# Handle tiktoken import and logging
try:
    import tiktoken
except ImportError:
    tiktoken = None
    # Use a local logger for this module, or ensure global logger is configured early
    logging.getLogger(__name__).warning("Tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken")

logger = get_logger(__name__)

def estimate_tokens_for_messages(messages: List[Dict[str, Any]], model_name_for_tiktoken: str = "cl100k_base") -> int:
    """
    Estimates the number of tokens a list of messages would occupy.

    Args:
        messages: A list of message dictionaries, similar to OpenAI's API.
        model_name_for_tiktoken: The name of the model or encoding to use for tiktoken.

    Returns:
        The estimated number of tokens, or -1 if tiktoken is unavailable or fails.
    """
    if tiktoken is None:
        logger.debug("Tiktoken is not available, cannot estimate tokens.")
        return -1
    try:
        encoding = tiktoken.get_encoding(model_name_for_tiktoken)
    except Exception:
        try:
            encoding = tiktoken.get_encoding("cl100k_base") # Fallback
        except Exception as e_enc:
            logger.error(f"Tiktoken: Failed to get encoding '{model_name_for_tiktoken}' or fallback 'cl100k_base': {e_enc}")
            return -1

    num_tokens = 0
    tokens_per_message_overhead = 3  # OpenAI specific, adjust if needed for other models
    tokens_for_name_if_present = 1   # OpenAI specific

    for message in messages:
        num_tokens += tokens_per_message_overhead
        if message.get("name"):
            num_tokens += tokens_for_name_if_present

        content = message.get("content")
        if content:
            if isinstance(content, str):
                try: num_tokens += len(encoding.encode(content))
                except Exception as e: logger.debug(f"Tiktoken content encode error (str): {e}")
            elif isinstance(content, list): # For multimodal messages (OpenAI format)
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                        try: num_tokens += len(encoding.encode(part["text"]))
                        except Exception as e: logger.debug(f"Tiktoken content encode error (text part): {e}")
                    elif isinstance(part, dict) and part.get("type") == "image_url":
                        # Image token estimation is complex and model-specific.
                        # OpenAI has its own rules (e.g., fixed cost + detail-based).
                        # Using a rough placeholder or a configurable value.
                        num_tokens += 70 # Very rough placeholder for image part overhead/low-detail
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
                    function_data = tool_call.get("function", {})
                    name = function_data.get("name")
                    arguments = function_data.get("arguments")
                    try:
                        if name: num_tokens += len(encoding.encode(name))
                        if arguments and isinstance(arguments, str): num_tokens += len(encoding.encode(arguments))
                    except Exception as e: logger.debug(f"Tiktoken tool data encode error: {e}")
                    num_tokens += 5 # Rough overhead for tool call structure

        if message.get("role") == "tool": # If the message itself is a tool response
            if tool_call_id_val := message.get("tool_call_id"):
                try: num_tokens += len(encoding.encode(tool_call_id_val))
                except Exception as e: logger.debug(f"Tiktoken tool_call_id encode error (tool role): {e}")

    num_tokens += 3  # Every reply is primed with <|start|>assistant<|message|> (OpenAI specific)
    return num_tokens


class PromptBuilder:
    """
    Constructs prompts for LLM interactions, particularly for the Pathos component.
    """
    def __init__(self, config: Config, ethos_core: EthosCore, logos_core: LogosCore):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        logger.info("PromptBuilder initialized.")

    def get_static_system_prompt_content(self) -> Optional[str]:
        """
        Generates a static version of the Pathos system prompt, primarily for
        cache warming or initial system checks.
        """
        try:
            main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "Error: Main Pathos system prompt template could not be loaded.")

            if self.ethos_core:
                persona_directives_content = "\n".join(self.ethos_core.get_persona_directives())
            else:
                logger.warning("PromptBuilder.get_static_system_prompt_content: EthosCore not available, using default persona directives.")
                persona_directives_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos.")

            static_prompt = main_system_prompt_template.replace("{{PATHOS_PERSONA_DIRECTIVES_FROM_FILE}}", persona_directives_content)

            placeholders_to_remove_or_static_fill = [
                "{{CURRENT_DATETIME_FOR_PROMPT}}", "{{USER_PROFILE_SUMMARY_FOR_PROMPT}}",
                "{{CURRENT_ACTIVITY_DESCRIPTION}}", "{{CURRENT_MOOD_FOR_PROMPT}}",
                "{{CURRENT_HEXUS_SCORES_FOR_PROMPT}}", "{{PATHOS_SCHEDULE_CONTEXT}}",
                "{{PATHOS_ASPIRATIONS_CONTEXT}}", "{{RELEVANT_MEMORIES_CONTEXT_FOR_PROMPT}}",
                "{{TODAYS_BRIEFING_CONTEXT_FOR_PROMPT}}", "{{VISION_ANALYSIS_CONTEXT_FOR_PROMPT}}"
            ]
            for ph in placeholders_to_remove_or_static_fill:
                static_prompt = static_prompt.replace(ph, f"[{ph.strip('{}').replace('_FOR_PROMPT','').replace('_CONTEXT','')} context placeholder]")

            # Use AVAILABLE_TOOLS_FOR_PATHOS_LLM as the default set Pathos itself reasons about
            tools_to_include = AVAILABLE_TOOLS_FOR_PATHOS_LLM
            static_prompt = static_prompt.replace("{{AVAILABLE_TOOLS_JSON_FOR_PROMPT}}", json.dumps(tools_to_include, indent=2))
            return static_prompt
        except Exception as e:
            logger.error(f"Error loading static system prompt content: {e}", exc_info=True)
            return "You are a helpful AI named Pathos." # Basic fallback

    async def build_main_llm_messages(
        self,
        user_id: str,
        user_input_text: str,
        history_context: List[Dict[str, Any]],
        image_data_b64: Optional[str] = None,
        vision_description_if_non_multimodal: Optional[str] = None,
        document_text: Optional[str] = None,
        force_web_search: bool = False,
        engaged_proactive_id: Optional[str] = None,
        system_provided_info: Optional[Dict[str, Any]] = None,
        enhanced_pathos_llm_config: Optional[LLMConfig] = None # Passed from PathosInterface
    ) -> Tuple[List[Dict[str, Any]], List[MemoryEntry], Dict[str, float], Dict[str, float], int]:
        """
        Builds the list of messages to be sent to the main Pathos LLM.

        This involves constructing the system prompt with dynamic context (mood, memories, etc.)
        and appending user input and history.
        """
        main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "ERROR: Main Pathos system prompt template not found.")

        persona_directives_content = "\n".join(self.ethos_core.get_persona_directives()) if self.ethos_core else load_system_prompt("pathos_directives", "Default persona: You are Pathos.")

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
                top_k=Config.get_nested_value(self.config.ETHOS, ['retrieval_limit_for_pathos_context'], 3), # self.config
                user_id_context=user_id
            )
        memories_formatted_for_prompt = "\n".join([f"- {m['content'][:300]}..." for m in retrieved_memories_raw if isinstance(m, dict) and 'content' in m]) or "No specific memories retrieved."

        # Use passed enhanced_pathos_llm_config
        is_multimodal_llm = enhanced_pathos_llm_config and enhanced_pathos_llm_config.get('supports_vision', False)
        vision_analysis_context_for_prompt = "No image provided this turn."
        if image_data_b64:
            if is_multimodal_llm: vision_analysis_context_for_prompt = "Image data provided directly in user message."
            elif vision_description_if_non_multimodal: vision_analysis_context_for_prompt = vision_description_if_non_multimodal
            else: vision_analysis_context_for_prompt = "Image provided, but no description generated (non-multimodal LLM)."

        pathos_schedule_context = (await self.ethos_core.get_pathos_schedule_context_for_prompt()) if self.ethos_core else "No schedule info."
        pathos_aspirations_context = (await self.ethos_core.get_pathos_aspirations_context_for_prompt()) if self.ethos_core else "No aspirations info."
        todays_briefing_context = (await self.ethos_core.get_todays_briefing_context_for_prompt(user_id)) if self.ethos_core else "No briefing info."

        # Use AVAILABLE_TOOLS_FOR_PATHOS_LLM by default for Pathos's own reasoning.
        # PathosInterface._call_llm_with_tools can decide to pass ALL_AVAILABLE_SYSTEM_TOOLS if it's a system call.
        available_tools_json_for_prompt = json.dumps(AVAILABLE_TOOLS_FOR_PATHOS_LLM, indent=2)

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

        # Enrich with subconscious thoughts if user_input_text is a thought query
        # user_input_text is the equivalent of user_msg for the enricher
        final_system_prompt_content = enrich_prompt_with_subconscious(final_system_prompt_content, user_input_text)

        if force_web_search:
            final_system_prompt_content += "\n\nIMPORTANT_NOTE: User requested web search. Prioritize web_search tool if appropriate."

        if system_provided_info:
            final_system_prompt_content += "\n\n--- System Provided Information (for your awareness) ---"
            if info := system_provided_info.get("weather"): final_system_prompt_content += f"\nCurrent Weather Context: Location: {info.get('location')}, Conditions: {info.get('temperature')}{info.get('unit')} {info.get('description')}."
            if info := system_provided_info.get("current_time_info"): final_system_prompt_content += f"\nCurrent Time Context: {info}"
            if info := system_provided_info.get("news_headlines"): final_system_prompt_content += f"\nRecent News Headlines Context: {str(info)[:500]}..."
            if info := system_provided_info.get("web_search_summary"): final_system_prompt_content += f"\nQuick Web Search Summary: {info}"
            final_system_prompt_content += "\n--- End System Provided Information ---"

        messages: List[Dict[str, Any]] = [{"role": "system", "content": final_system_prompt_content}]

        cleaned_history = []
        for msg in history_context:
            if msg.get("role") == "system":
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
            image_mime_type = "image/jpeg" # Default, can be refined
            if image_data_b64.startswith("iVBORw0KGgo"): image_mime_type = "image/png"
            elif image_data_b64.startswith("/9j/"): image_mime_type = "image/jpeg"
            user_message_content_parts.append({"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{image_data_b64}"}})

        final_user_content: Union[str, List[Dict[str,Any]]] = user_message_content_parts[0]["text"] if len(user_message_content_parts) == 1 and user_message_content_parts[0]["type"] == "text" else user_message_content_parts
        messages.append({"role": "user", "content": final_user_content})

        estimated_tokens = -1
        if enhanced_pathos_llm_config: # Use the passed config for token estimation
            model_name_for_tiktoken = enhanced_pathos_llm_config.get('model_name_for_tiktoken', enhanced_pathos_llm_config.get('model', 'cl100k_base'))
            estimated_tokens = estimate_tokens_for_messages(messages, model_name_for_tiktoken) # Call local/static version
            logger.info(f"Estimated tokens for messages (user: {user_id}, model for tiktoken: {model_name_for_tiktoken}): {estimated_tokens}")

        logger.info(f"Built main LLM messages for user '{user_id}'. System prompt length: {len(final_system_prompt_content)}. Total messages: {len(messages)}")

        return messages, retrieved_memories_raw, current_mood_dict, hexus_scores_dict, estimated_tokens

# Note: PATHOS_USER_ID is used by _execute_tools in PathosInterface for add_pathos_event.
# If _execute_tools were moved here, PATHOS_USER_ID would need to be imported here too.
# For now, it's fine as _execute_tools remains in PathosInterface.
