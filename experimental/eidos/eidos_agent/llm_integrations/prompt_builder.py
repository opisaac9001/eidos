"""
Handles the construction of prompts for LLM interactions within the Eidos agent,
particularly for the Pathos Subconscious Node.
"""
import logging
import json
from datetime import datetime, timezone, timedelta # Added timedelta
from typing import List, Dict, Any, Optional, Tuple, Union

from eidos_agent.core.config import Config, LLMConfig # Assuming LLMConfig is needed, or just Config

from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.persona_logic.logos_core.handler import LogosCore # For execute_get_time
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.prompt_loader import load_system_prompt
from eidos_agent.utils.logger import get_logger # Use consistent logger

# Import tool definitions (updated to relative)
from .pathos_tools_definitions import (
    AVAILABLE_TOOLS_FOR_PATHOS_LLM,
    # ALL_AVAILABLE_SYSTEM_TOOLS # Not directly used in this version of PromptBuilder
)

# Import the enricher function (this will be replaced)
# from eidos_agent.core.prompting.context_enricher import enrich_prompt_with_subconscious

# Import the new SubconsciousFeedIntegrator
from eidos_agent.features.subconscious_interface_to_node.subconscious_feed_integrator import SubconsciousFeedIntegrator


# Handle tiktoken import and logging
try:
    import tiktoken
except ImportError:
    tiktoken = None
    # Use a local logger for this module, or ensure global logger is configured early
    logging.getLogger(__name__).warning("Tiktoken not found. Token estimation will be unavailable. Install with: pip install tiktoken")

logger = get_logger(__name__)

DAYS_TO_PREFER_SUMMARY_FOR_CONTEXT = 1.0 # Added constant

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
        # Initialize the SubconsciousFeedIntegrator
        # It's okay if this uses default cache settings for now.
        # If SubconsciousFeedIntegrator needs config (e.g. for cache duration),
        # it should ideally pull from Config itself or be passed params here.
        # The current SubconsciousFeedIntegrator takes an optional cache_duration_seconds.
        # We can make it configurable via main Config if needed later.
        try:
            self.feed_integrator: Optional[SubconsciousFeedIntegrator] = SubconsciousFeedIntegrator()
            logger.info("SubconsciousFeedIntegrator initialized in PromptBuilder.")
        except Exception as e:
            self.feed_integrator = None
            logger.error(f"Failed to initialize SubconsciousFeedIntegrator in PromptBuilder: {e}", exc_info=True)

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
        This involves constructing the system prompt with dynamic context (mood, memories, etc.),
        potentially injecting relevant past interactions, and managing token limits.
        """
        # Get Dynamic Context Configuration
        dynamic_context_enabled = self.config.DYNAMIC_CONTEXT_ENABLED
        max_retrieved_chunks = self.config.DYNAMIC_CONTEXT_MAX_RETRIEVED_CHUNKS
        similarity_threshold = self.config.DYNAMIC_CONTEXT_SIMILARITY_THRESHOLD
        # LLM token limits will be used further down.

        # --- Standard System Prompt Construction (as before) ---
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

        # New logic for formatting memories, potentially using summaries:
        formatted_memory_strings = []
        now_utc = datetime.now(timezone.utc)

        for m in retrieved_memories_raw:
            if not (isinstance(m, dict) and m.get('content')):
                continue

            summary_content = m.get('summary_llm')
            use_summary = False
            # Default display timestamp if parsing fails or not applicable
            memory_display_timestamp = "an earlier time"

            if summary_content and isinstance(summary_content, str) and summary_content.strip():
                timestamp_str = m.get('timestamp')
                if timestamp_str:
                    try:
                        # Ensure timestamp is timezone-aware (UTC) for comparison
                        mem_ts_parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if mem_ts_parsed.tzinfo is None:
                            mem_ts = mem_ts_parsed.replace(tzinfo=timezone.utc)
                        else:
                            mem_ts = mem_ts_parsed.astimezone(timezone.utc)

                        memory_display_timestamp = mem_ts.strftime('%Y-%m-%d %H:%M UTC')
                        # Use '>=' so 1.0 means 1 full day (24 hours) or more has passed
                        if (now_utc - mem_ts).days >= DAYS_TO_PREFER_SUMMARY_FOR_CONTEXT:
                            use_summary = True
                    except ValueError as e_ts:
                        logger.debug(f"Could not parse timestamp for memory {m.get('id', 'N/A')} ('{timestamp_str}') to decide on summary: {e_ts}")
                    except Exception as e_gen_ts:
                        logger.warning(f"Unexpected error processing timestamp for memory {m.get('id', 'N/A')}: {e_gen_ts}")

            if use_summary:
                summary_snippet = summary_content[:350] + "..." if len(summary_content) > 350 else summary_content
                formatted_memory_strings.append(f"- [Summary from {memory_display_timestamp}]: {summary_snippet}")
            else:
                content_snippet = m['content'][:300] + "..." if len(m['content']) > 300 else m['content']
                prefix_for_content = ""
                # Add timestamp to content if summary not used, timestamp is available, and not obviously part of content
                if memory_display_timestamp != "an earlier time" and not m['content'].startswith(memory_display_timestamp.split(' ')[0]):
                     prefix_for_content = f"[From {memory_display_timestamp}]: "
                formatted_memory_strings.append(f"- {prefix_for_content}{content_snippet}")

        memories_formatted_for_prompt = "\n".join(formatted_memory_strings) or "No specific memories retrieved for this query."

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
            "{{RELEVANT_MEMORIES_CONTEXT_FOR_PROMPT}}": memories_formatted_for_prompt, # Standard short-term memory retrieval
            "{{TODAYS_BRIEFING_CONTEXT_FOR_PROMPT}}": todays_briefing_context,
            "{{VISION_ANALYSIS_CONTEXT_FOR_PROMPT}}": vision_analysis_context_for_prompt,
            "{{AVAILABLE_TOOLS_JSON_FOR_PROMPT}}": available_tools_json_for_prompt
        }

        base_system_prompt_content = main_system_prompt_template
        for placeholder, value in system_prompt_replacements.items():
            base_system_prompt_content = base_system_prompt_content.replace(placeholder, str(value) if value is not None else "")

        # Enrich with subconscious thoughts
        if self.feed_integrator:
            subconscious_enrichment = self.feed_integrator.get_formatted_thoughts_for_prompt(user_input_text)
            if subconscious_enrichment:
                base_system_prompt_content += subconscious_enrichment
        else:
            logger.warning("SubconsciousFeedIntegrator not available. Skipping subconscious enrichment.")

        if force_web_search:
            base_system_prompt_content += "\n\nIMPORTANT_NOTE: User requested web search. Prioritize web_search tool if appropriate."

        if system_provided_info:
            base_system_prompt_content += "\n\n--- System Provided Information (for your awareness) ---"
            if info := system_provided_info.get("weather"): base_system_prompt_content += f"\nCurrent Weather Context: Location: {info.get('location')}, Conditions: {info.get('temperature')}{info.get('unit')} {info.get('description')}."
            if info := system_provided_info.get("current_time_info"): base_system_prompt_content += f"\nCurrent Time Context: {info}"
            if info := system_provided_info.get("news_headlines"): base_system_prompt_content += f"\nRecent News Headlines Context: {str(info)[:500]}..."
            if info := system_provided_info.get("web_search_summary"): base_system_prompt_content += f"\nQuick Web Search Summary: {info}"
            base_system_prompt_content += "\n--- End System Provided Information ---"

        system_prompt_message = {"role": "system", "content": base_system_prompt_content}

        # --- Dynamic Context Injection & Truncation ---
        model_name_for_tiktoken = "cl100k_base" # Default
        if enhanced_pathos_llm_config:
             model_name_for_tiktoken = enhanced_pathos_llm_config.get('model_name_for_tiktoken', enhanced_pathos_llm_config.get('model', 'cl100k_base'))

        injected_past_messages: List[Dict[str, Any]] = []
        if dynamic_context_enabled and self.ethos_core:
            logger.debug(f"Dynamic context enabled. Retrieving past interactions for user '{user_id}'.")
            # For now, current_history_entry_ids is passed as empty. Content-based filtering will be applied.
            retrieved_past_interactions = await self.ethos_core.retrieve_relevant_past_interactions(
                query_text=user_input_text, # Query based on current user input
                user_id=user_id,
                current_history_entry_ids=[],
                top_k=max_retrieved_chunks,
                similarity_threshold=similarity_threshold
            )

            if retrieved_past_interactions:
                # Content-based filtering against current history_context
                history_content_set = {msg.get("content") for msg in history_context if isinstance(msg.get("content"), str)}

                unique_past_interactions = []
                for mem_entry in retrieved_past_interactions:
                    if mem_entry.get('content') not in history_content_set:
                        unique_past_interactions.append(mem_entry)
                    else:
                        logger.debug(f"Filtered out past interaction (ID: {mem_entry.get('id')}) due to content match with current history.")

                # Format for injection
                max_len_past_interaction = 250 # Max length for each injected snippet
                for mem_entry in unique_past_interactions: # Already sorted by relevance by EthosCore
                    summary_content = mem_entry.get('summary_llm')
                    original_content = mem_entry.get('content', '')
                    use_summary = False
                    interaction_display_timestamp = "an earlier time" # Default
                    parsed_timestamp_for_age_check = None

                    timestamp_str = mem_entry.get('timestamp')
                    if timestamp_str:
                        try:
                            # Robust timestamp parsing
                            parsed_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                            if parsed_dt.tzinfo is None:
                                parsed_timestamp_for_age_check = parsed_dt.replace(tzinfo=timezone.utc)
                            else:
                                parsed_timestamp_for_age_check = parsed_dt.astimezone(timezone.utc)
                            interaction_display_timestamp = parsed_timestamp_for_age_check.strftime('%Y-%m-%d %H:%M UTC')
                        except ValueError as e_ts:
                            logger.debug(f"Could not parse timestamp for past interaction {mem_entry.get('id', 'N/A')} ('{timestamp_str}'): {e_ts}")
                        except Exception as e_gen_ts: # Catch any other unexpected errors
                            logger.warning(f"Unexpected error processing timestamp for past interaction {mem_entry.get('id', 'N/A')}: {e_gen_ts}")

                    if summary_content and isinstance(summary_content, str) and summary_content.strip() and parsed_timestamp_for_age_check:
                        # now_utc should be defined earlier in the method from previous changes
                        if (now_utc - parsed_timestamp_for_age_check).days >= DAYS_TO_PREFER_SUMMARY_FOR_CONTEXT:
                            use_summary = True

                    if use_summary:
                        summary_snippet = summary_content[:max_len_past_interaction] + "..." if len(summary_content) > max_len_past_interaction else summary_content
                        system_recall_content = f"[Recalling a summary of an earlier part of our conversation (around {interaction_display_timestamp}) that seems relevant:]\n{summary_snippet}"
                    else:
                        content_snippet = original_content[:max_len_past_interaction] + "..." if len(original_content) > max_len_past_interaction else original_content
                        # Use a slightly different prefix if it's not a summary but still has a good timestamp
                        prefix_str = "Recalling an earlier part of our conversation"
                        if interaction_display_timestamp != "an earlier time":
                             prefix_str += f" (around {interaction_display_timestamp})"
                        system_recall_content = f"[{prefix_str} that seems relevant:]\n{content_snippet}"

                    # Estimate tokens for this specific injected message
                    # Note: estimate_tokens_for_messages expects a list of messages.
                    tokens_for_this_injection = estimate_tokens_for_messages([{"role": "system", "content": system_recall_content}], model_name_for_tiktoken)

                    injected_past_messages.append({
                        "role": "system",
                        "content": system_recall_content,
                        "_is_injected_context": True, # Mark for truncation logic
                        "_estimated_tokens": tokens_for_this_injection # Store its token count
                    })
                if injected_past_messages:
                    logger.info(f"Injecting {len(injected_past_messages)} relevant past interaction snippets.")

        # Clean history_context (remove old system prompts, etc.)
        cleaned_history: List[Dict[str, Any]] = []
        for msg in history_context:
            is_old_system_prompt = msg.get("role") == "system" and (
                msg.get("content") == base_system_prompt_content or # Exact match (unlikely now with dynamic parts)
                "Error: Main Pathos system prompt not found" in msg.get("content","") or
                msg.get("content") == "You are a helpful assistant" or
                msg.get("_is_injected_context") # Remove previously injected context from history
            )
            if not is_old_system_prompt:
                # Add estimated tokens to history messages if not already present
                if "_estimated_tokens" not in msg:
                    msg["_estimated_tokens"] = estimate_tokens_for_messages([msg], model_name_for_tiktoken)
                cleaned_history.append(msg)

        # Prepare current user message (multimodal if needed)
        user_message_content_parts: List[Dict[str, Any]] = []
        current_user_input_full = user_input_text
        if document_text: current_user_input_full += f"\n\n--- Attached Document Content ---\n{document_text}\n--- End of Document ---"
        user_message_content_parts.append({"type": "text", "text": current_user_input_full})

        if image_data_b64 and is_multimodal_llm:
            image_mime_type = "image/jpeg" # Default
            if image_data_b64.startswith("iVBORw0KGgo"): image_mime_type = "image/png"
            elif image_data_b64.startswith("/9j/"): image_mime_type = "image/jpeg"
            user_message_content_parts.append({"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{image_data_b64}"}})

        final_user_content: Union[str, List[Dict[str,Any]]] = user_message_content_parts[0]["text"] if len(user_message_content_parts) == 1 and user_message_content_parts[0]["type"] == "text" else user_message_content_parts
        current_user_message = {"role": "user", "content": final_user_content}
        current_user_message["_estimated_tokens"] = estimate_tokens_for_messages([current_user_message], model_name_for_tiktoken)


        # Assemble messages: System Prompt, Injected Past, Cleaned History, Current User Input
        # System prompt needs its token count too
        system_prompt_message["_estimated_tokens"] = estimate_tokens_for_messages([system_prompt_message], model_name_for_tiktoken)

        tentative_messages: List[Dict[str, Any]] = [system_prompt_message] + injected_past_messages + cleaned_history + [current_user_message]

        # Token Truncation Logic
        max_prompt_tokens = self.config.LLM_MAX_PROMPT_TOKENS_MAIN - self.config.LLM_RESPONSE_BUFFER_TOKENS

        current_total_tokens = sum(m.get("_estimated_tokens", 0) for m in tentative_messages)
        logger.debug(f"Initial token count before truncation: {current_total_tokens}. Max allowed: {max_prompt_tokens}")

        # Truncation loop
        # Priority: 1. Oldest from cleaned_history, 2. Oldest from injected_past_messages
        while current_total_tokens > max_prompt_tokens:
            removed_something = False
            # Try removing from cleaned_history first (oldest standard history)
            # Ensure system_prompt (index 0) and current_user_message (last index) are not removed initially
            if len(tentative_messages) > 2: # Must have more than sys prompt and user msg
                # Find first removable message from cleaned_history part
                # System prompt is at index 0. Injected messages follow. Then cleaned history.
                start_of_cleaned_history_idx = 1 + len(injected_past_messages)
                if start_of_cleaned_history_idx < len(tentative_messages) -1: # Check if cleaned_history part exists and is not the user message
                    removed_msg = tentative_messages.pop(start_of_cleaned_history_idx)
                    current_total_tokens -= removed_msg.get("_estimated_tokens", 0)
                    logger.debug(f"Truncation: Removed message from cleaned_history (tokens: {removed_msg.get('_estimated_tokens',0)}). New total: {current_total_tokens}")
                    removed_something = True
                elif injected_past_messages: # No more cleaned_history to remove, try injected context
                    # Remove from the start of injected_past_messages (oldest injected)
                    removed_msg = tentative_messages.pop(1) # Index 1 is the oldest injected if any
                    current_total_tokens -= removed_msg.get("_estimated_tokens", 0)
                    injected_past_messages.pop(0) # Also remove from the separate list
                    logger.debug(f"Truncation: Removed message from injected_past_messages (tokens: {removed_msg.get('_estimated_tokens',0)}). New total: {current_total_tokens}")
                    removed_something = True

            if not removed_something:
                # This means only system prompt and current user message are left, or something is wrong.
                logger.warning(f"Cannot truncate further. System prompt and user message alone exceed token limit ({current_total_tokens} > {max_prompt_tokens}). This may lead to LLM errors.")
                # Potentially truncate system prompt or user message if absolutely necessary,
                # but this usually indicates a design issue or extremely large single messages.
                # For now, break to avoid infinite loop.
                break

        final_messages = tentative_messages
        # Clean up internal token count keys before sending to LLM
        for msg in final_messages:
            msg.pop("_estimated_tokens", None)
            msg.pop("_is_injected_context", None)

        final_estimated_tokens = estimate_tokens_for_messages(final_messages, model_name_for_tiktoken)
        logger.info(f"Built main LLM messages for user '{user_id}'. Final token count: {final_estimated_tokens}. System prompt length: {len(system_prompt_message['content'])}. Total messages: {len(final_messages)}")

        return final_messages, retrieved_memories_raw, current_mood_dict, hexus_scores_dict, final_estimated_tokens

# Note: PATHOS_USER_ID is used by _execute_tools in PathosInterface for add_pathos_event.
# If _execute_tools were moved here, PATHOS_USER_ID would need to be imported here too.
# For now, it's fine as _execute_tools remains in PathosInterface.
