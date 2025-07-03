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

    async def build_messages_from_main_llm_prompt_context(
        self,
        context: 'MainLLMPromptContext', # Forward reference with quotes
        llm_config: Optional[LLMConfig] = None
    ) -> List[Dict[str, Any]]: # Returns only the messages
        """
        Builds the list of messages for the Main Pathos LLM using a MainLLMPromptContext object.
        """
        # Unpack data from the context object
        user_id = self.ethos_core.current_active_user_id if self.ethos_core else "unknown_user" # Assuming PathosInterface sets this
        # Or, if MainLLMPromptContext should carry user_id:
        # user_id = context.user_id_for_context if hasattr(context, 'user_id_for_context') else "unknown_user"

        user_input_text = context.user_input
        history_context = context.conversation_history

        # Assuming context fields for mood, memories etc. are already Pydantic models or dicts
        # that can be used directly or easily formatted.
        # The original build_main_llm_messages fetched these; now they are provided.

        main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "You are Pathos...")

        persona_directives_content = "\n".join(context.persona_profile.get("core_directives", [])) if context.persona_profile else "Default persona." # Simplified
        current_mood_str = f"Valence: {context.current_mood.get('valence', 0):.2f}, Arousal: {context.current_mood.get('arousal', 0):.2f}" if context.current_mood else "Mood: Neutral"
        current_activity_description = context.current_activity.get("title", "Currently idle.") if context.current_activity else "Currently idle."
        hexus_scores_str = ", ".join([f"{s.get('name')}={s.get('value'):.2f}" for s in context.current_mood.get("detailed_hexus_scores", [])]) if context.current_mood else "N/A"

        user_profile_summary = "User profile not detailed in context." # Placeholder
        if context.persona_profile and context.persona_profile.get("self_description_summary"): # Assuming profile might contain this
            user_profile_summary = context.persona_profile.get("self_description_summary")
        elif self.ethos_core: # Fallback to fetching if not directly in context.persona_profile
             user_profile_summary = await self.ethos_core.get_user_profile_summary(user_id)


        try:
            current_time_str = await self.logos_core.execute_get_time(location=None) if self.logos_core else datetime.now(timezone.utc).strftime("%A, %B %d, %Y, %I:%M %p %Z")
            if not isinstance(current_time_str, str) or "Error" in current_time_str or "error" in current_time_str.lower():
                 current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")
        except Exception: current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z (UTC fallback)")

        formatted_memory_strings = []
        if context.recent_memories:
            for mem_dict in context.recent_memories: # mem_dict is already a dict from model_dump()
                content_snippet = mem_dict.get('content', '')[:150] + "..." if len(mem_dict.get('content', '')) > 150 else mem_dict.get('content', '')
                formatted_memory_strings.append(f"- {content_snippet}")
        memories_formatted_for_prompt = "\n".join(formatted_memory_strings) or "No specific recent memories noted."

        pathos_schedule_context = context.current_activity.get("title", "No specific schedule context.") if context.current_activity else "No schedule info."
        pathos_aspirations_context = "Aspirations context not detailed." # Placeholder, needs specific field in MainLLMPromptContext or persona_profile
        todays_briefing_context = "Briefing context not detailed." # Placeholder

        pathos_traits_description = "Pathos has an adaptive personality." # Placeholder
        if context.persona_profile and context.persona_profile.get("traits"):
            traits_list = [f"{t.get('name')}: {t.get('value')}" for t in context.persona_profile.get("traits", [])]
            if traits_list: pathos_traits_description = "Key traits: " + "; ".join(traits_list)

        available_tools_json_for_prompt = json.dumps(self.logos_core.get_tools_for_llm(user_id_context=user_id), indent=2) if self.logos_core else "[]"

        vision_analysis_context_for_prompt = "No image analysis this turn."
        if context.simulation_context and context.simulation_context.get("image_analysis_result"): # Example if sim_context carried this
            vision_analysis_context_for_prompt = context.simulation_context.get("image_analysis_result")


        system_prompt_replacements = {
            "{{PATHOS_PERSONA_DIRECTIVES_FROM_FILE}}": persona_directives_content,
            "{{CURRENT_DATETIME_FOR_PROMPT}}": current_time_str,
            "{{USER_PROFILE_SUMMARY_FOR_PROMPT}}": user_profile_summary,
            "{{CURRENT_ACTIVITY_DESCRIPTION}}": current_activity_description,
            "{{CURRENT_MOOD_FOR_PROMPT}}": current_mood_str,
            "{{CURRENT_HEXUS_SCORES_FOR_PROMPT}}": hexus_scores_str,
            "{{PATHOS_SCHEDULE_CONTEXT}}": pathos_schedule_context,
            "{{PATHOS_ASPIRATIONS_CONTEXT}}": pathos_aspirations_context,
            "{{PATHOS_TRAITS_DESCRIPTION}}": pathos_traits_description,
            "{{RELEVANT_MEMORIES_CONTEXT_FOR_PROMPT}}": memories_formatted_for_prompt,
            "{{TODAYS_BRIEFING_CONTEXT_FOR_PROMPT}}": todays_briefing_context,
            "{{VISION_ANALYSIS_CONTEXT_FOR_PROMPT}}": vision_analysis_context_for_prompt,
            "{{AVAILABLE_TOOLS_JSON_FOR_PROMPT}}": available_tools_json_for_prompt
        }
        base_system_prompt_content = main_system_prompt_template
        for placeholder, value in system_prompt_replacements.items():
            base_system_prompt_content = base_system_prompt_content.replace(placeholder, str(value) if value is not None else "")

        if self.feed_integrator and context.significant_subconscious_thoughts:
            # This needs SubconsciousFeedIntegrator to be adapted or a new method to format thoughts from context
            # For now, simple join:
            thoughts_str = "\n".join([f"- {th.get('content')}" for th in context.significant_subconscious_thoughts])
            subconscious_enrichment = f"\n\n--- Recent Subconscious Musings ---\n{thoughts_str}\n--- End Subconscious Musings ---"
            if subconscious_enrichment:
                base_system_prompt_content += subconscious_enrichment

        system_prompt_message = {"role": "system", "content": base_system_prompt_content}

        # Token management: Use cleaned history from context.conversation_history
        # The context.conversation_history should already be prepared by PathosInterface
        # (e.g., user input added, but not yet Pathos's current response attempt).

        # For now, assume history_context in MainLLMPromptContext is ready to use
        final_messages: List[Dict[str, Any]] = [system_prompt_message] + history_context

        # Simplified token estimation and truncation for this refactor step.
        # Actual token counting and truncation logic from original build_main_llm_messages should be adapted here.
        model_name_for_tiktoken = "cl100k_base"
        if llm_config:
             model_name_for_tiktoken = llm_config.get('model_name_for_tiktoken', llm_config.get('model', 'cl100k_base'))

        estimated_tokens = estimate_tokens_for_messages(final_messages, model_name_for_tiktoken)
        logger.info(f"PromptBuilder (new method): Initial message assembly. Estimated tokens: {estimated_tokens}. System prompt length: {len(system_prompt_message['content'])}. Total messages: {len(final_messages)}")

        # Token Truncation Logic (adapted from original build_main_llm_messages)
        # Max prompt tokens calculation (should come from config, passed via llm_config or self.config)
        # Assuming llm_config is the enhanced_pathos_llm_config which might have overrides.
        # Fallback to main config if specific limits aren't in llm_config.

        # PathosInterface._get_enhanced_pathos_llm_config() will provide this.
        # For PromptBuilder, it should ideally get these limits via config objects.
        # Let's assume self.config has these directly for simplicity here.
        llm_max_prompt_tokens_main = self.config.LLM_MAX_PROMPT_TOKENS_MAIN
        llm_response_buffer_tokens = self.config.LLM_RESPONSE_BUFFER_TOKENS
        max_prompt_tokens = llm_max_prompt_tokens_main - llm_response_buffer_tokens

        # Add _estimated_tokens to each message for truncation logic
        messages_for_truncation: List[Dict[str, Any]] = []
        for msg in final_messages:
            msg_copy = msg.copy()
            msg_copy["_estimated_tokens"] = estimate_tokens_for_messages([msg_copy], model_name_for_tiktoken)
            messages_for_truncation.append(msg_copy)

        current_total_tokens = sum(m.get("_estimated_tokens", 0) for m in messages_for_truncation)
        logger.debug(f"Token count before truncation: {current_total_tokens}. Max allowed for prompt: {max_prompt_tokens}")

        # Truncation loop
        # Priority: Remove oldest from history_context first.
        # System prompt (index 0) and current user input (last message) should be preserved if possible.
        # The 'history_context' part is now context.conversation_history.
        # 'injected_past_messages' equivalent would be context.recent_memories or context.significant_subconscious_thoughts if formatted as messages.
        # For this refactor, let's assume context.conversation_history is the primary part to truncate.

        # The structure of messages_for_truncation is [system_prompt, ...history_messages..., user_input_message]
        # We want to remove from the `...history_messages...` part.

        while current_total_tokens > max_prompt_tokens and len(messages_for_truncation) > 2: # Keep at least system and user message
            # Remove from the oldest part of the history, which is after the system prompt (index 0)
            idx_to_remove = 1
            if idx_to_remove < len(messages_for_truncation) - 1: # Ensure we don't remove the last (user) message
                removed_msg = messages_for_truncation.pop(idx_to_remove)
                removed_tokens = removed_msg.get("_estimated_tokens", 0)
                current_total_tokens -= removed_tokens
                logger.debug(f"Truncation: Removed message (tokens: {removed_tokens}, content: '{str(removed_msg.get('content'))[:30]}...'). New total: {current_total_tokens}")
            else:
                # Only system prompt and user message left, or only one history message that can't be removed without leaving only one.
                logger.warning(f"Cannot truncate further history. Current token count {current_total_tokens} still exceeds max {max_prompt_tokens}.")
                break

        # Clean up internal token count keys before returning
        final_truncated_messages = []
        for msg in messages_for_truncation:
            msg_copy = msg.copy()
            msg_copy.pop("_estimated_tokens", None)
            final_truncated_messages.append(msg_copy)

        final_estimated_tokens_after_trunc = estimate_tokens_for_messages(final_truncated_messages, model_name_for_tiktoken)
        logger.info(f"PromptBuilder (new method): Built messages. Final token count after truncation: {final_estimated_tokens_after_trunc}. Total messages: {len(final_truncated_messages)}")

        return final_truncated_messages


    def get_static_system_prompt_content(self) -> Optional[str]:
        """
        Generates a static version of the Pathos system prompt, primarily for
        cache warming or initial system checks.
        """
        try:
            main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "You are Pathos, a helpful AI assistant. Please ensure your persona directives and context are fully loaded.")

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
        DEPRECATED: This method is being replaced by build_messages_from_main_llm_prompt_context.
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
        main_system_prompt_template = load_system_prompt("main_pathos_llm_system_prompt", "You are Pathos, a helpful AI assistant. Please ensure your persona directives and context are fully loaded.")
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
            min_salience_for_retrieval = float(self.config.ETHOS.get('retrieval_min_salience_for_pathos_context', 0.1))
            # Ensure ETHOS config key exists or add it to Config.ETHOS if this is a new key.
            # For now, assuming it might exist or 0.1 is a safe default.

            retrieved_memories_raw = await self.ethos_core.retrieve_relevant_memories(
                query=" ".join(memory_query_parts),
                top_k=Config.get_nested_value(self.config.ETHOS, ['retrieval_limit_for_pathos_context'], 3),
                min_salience=min_salience_for_retrieval,
                user_id_context=user_id
                # allowed_types can be added here if needed, e.g., allowed_types=['interaction', 'document_chunk']
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

        pathos_traits_description = "Pathos has a generally adaptive personality profile." # Default
        if self.ethos_core and hasattr(self.ethos_core, 'traits_engine') and self.ethos_core.traits_engine:
            try:
                # The get_descriptive_trait_summary is synchronous
                desc = self.ethos_core.traits_engine.get_descriptive_trait_summary()
                if desc: # Use it only if it's not empty
                    pathos_traits_description = desc
                logger.debug(f"PromptBuilder: Fetched trait description: {pathos_traits_description}")
            except Exception as e_trait_desc:
                logger.error(f"PromptBuilder: Error fetching trait description from TraitsEngine: {e_trait_desc}", exc_info=True)
                # Fallback to default is already set
        else:
            logger.warning("PromptBuilder: EthosCore or TraitsEngine not available for fetching trait description. Using default.")

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
            "{{PATHOS_TRAITS_DESCRIPTION}}": pathos_traits_description, # New entry
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

if __name__ == '__main__':
    import asyncio
    import logging # Already imported at top level, but good for clarity in __main__
    from pathlib import Path
    import unittest.mock # For mocking LogosCore

    # Ensure types for mocks are available. Adjust import paths if necessary based on file structure.
    # These are typically for type hinting the mock classes to resemble the real ones.
    try:
        from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
    except ImportError:
        # Define a dummy MemoryEntry if the real one cannot be imported (e.g. running file standalone)
        MemoryEntry = Dict[str, Any] # type: ignore
        print("Warning: Could not import MemoryEntry for prompt_builder test, using dummy Dict.")

    try:
        # Attempt to import real config types for more accurate mock definitions
        from eidos_agent.core.config import Config as RealConfig
        from eidos_agent.core.config import EthosConfig as RealEthosConfigType
        from eidos_agent.core.config import LLMConfig as RealLLMConfigType
    except ImportError:
        # Define dummy types if real ones are not available
        RealConfig = Dict[str, Any] # type: ignore
        RealEthosConfigType = Dict[str, Any] # type: ignore
        RealLLMConfigType = Dict[str, Any] # type: ignore
        print("Warning: Could not import real Config types for prompt_builder test, using dummy Dicts.")


    # Setup basic logging for the __main__ block if not already configured
    # This logger is specific to the test execution in __main__
    logger_main = logging.getLogger("prompt_builder_test")
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    class MockTraitsEngine:
        def get_descriptive_trait_summary(self) -> str:
            logger_main.info("MockTraitsEngine.get_descriptive_trait_summary called")
            return "Pathos's key personality characteristics include: Test Trait: Value; Test Verbosity: High."

        def get_all_traits(self) -> Dict[str, Any]:
            logger_main.info("MockTraitsEngine.get_all_traits called")
            return {"test_trait": "value", "verbosity": "high", "openness": 0.7, "conscientiousness": 0.6, "extraversion": 0.5, "agreeableness": 0.8, "neuroticism": 0.3}


    class MockEthosCore:
        PATHOS_USER_ID = "test_pathos_id_pb" # Static class attribute for user ID

        def __init__(self, config_obj: Any): # config_obj will be an instance of MockConfigForPromptBuilder
            self.config = config_obj # Store the mock config
            # EthosConfig is expected to be a dict-like attribute on the main config.
            # PromptBuilder accesses it via self.config.ETHOS.
            # So, MockConfigForPromptBuilder needs an ETHOS attribute.
            self.ethos_config: RealEthosConfigType = getattr(config_obj, 'ETHOS', {})
            self.traits_engine = MockTraitsEngine()
            logger_main.info(f"MockEthosCore for PromptBuilder initialized with config: {self.ethos_config}")

        def get_persona_directives(self) -> List[str]:
            logger_main.debug("MockEthosCore.get_persona_directives called")
            return ["PB Test Directive 1: Be helpful.", "PB Test Directive 2: Be insightful."]

        def get_current_mood(self) -> Dict[str, Any]:
            logger_main.debug("MockEthosCore.get_current_mood called")
            return {"name": "pb_test_mood_calm", "valence": 0.2, "arousal": -0.1}

        async def get_current_activity_description(self) -> str:
            logger_main.debug("MockEthosCore.get_current_activity_description called")
            return "PB testing activity: Contemplating test assertions."

        def get_hexus_scores(self) -> Dict[str, float]:
            logger_main.debug("MockEthosCore.get_hexus_scores called")
            return {"joy": 0.65, "anticipation": 0.4, "sadness": 0.1} # Example scores

        async def get_user_profile_summary(self, user_id: str) -> str:
            logger_main.debug(f"MockEthosCore.get_user_profile_summary called for user {user_id}")
            return f"PB User Profile for {user_id}: Enjoys thorough testing."

        async def get_pathos_schedule_context_for_prompt(self) -> str:
            logger_main.debug("MockEthosCore.get_pathos_schedule_context_for_prompt called")
            return "PB Schedule Context: Next up - verify prompt contents. Then, celebrate."

        async def get_pathos_aspirations_context_for_prompt(self) -> str:
            logger_main.debug("MockEthosCore.get_pathos_aspirations_context_for_prompt called")
            return "PB Aspirations Context: To build the most illustrative and correct prompts."

        async def retrieve_relevant_memories(
            self, query: str, top_k: int, min_salience: float,
            user_id_context: Optional[str] = None,
            allowed_types: Optional[List[str]] = None
        ) -> List[MemoryEntry]:
            logger_main.debug(f"MockEthosCore.retrieve_relevant_memories called with query='{query}', top_k={top_k}, min_salience={min_salience}")
            # Return a list of MemoryEntry compatible dicts
            return [
                {
                    "id": "mem_pb_test_1", "type": "interaction",
                    "content": "User previously asked about mock data quality.",
                    "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                    "salience": 0.85, "summary_llm": "User inquired about mock data."
                } # type: ignore
            ]

        async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str:
            logger_main.debug(f"MockEthosCore.get_todays_briefing_context_for_prompt called for user {user_id}")
            return "PB Daily Briefing: Focus on trait integration. Ensure tests cover new prompt elements."

        def get_all_traits(self) -> Dict[str, Any]: # Delegates to its traits_engine
            logger_main.debug("MockEthosCore.get_all_traits called, delegating to traits_engine.")
            return self.traits_engine.get_all_traits()

        # Mock for retrieve_relevant_past_interactions
        async def retrieve_relevant_past_interactions(
            self, query_text: str, user_id: str, current_history_entry_ids: List[str],
            top_k: int, similarity_threshold: float
        ) -> List[MemoryEntry]:
            logger_main.debug(f"MockEthosCore.retrieve_relevant_past_interactions called for user {user_id}, query: '{query_text}'")
            return [
                 {
                    "id": "past_inter_pb_1", "type": "interaction",
                    "content": "User: What was the weather like yesterday? Pathos: It was sunny.",
                    "timestamp": (datetime.now(timezone.utc) - timedelta(days=1, hours=2)).isoformat(),
                    "salience": 0.7, "summary_llm": "Discussed yesterday's weather (sunny)."
                } # type: ignore
            ]


    class MockConfigForPromptBuilder(RealConfig): # type: ignore
        PROJECT_ROOT: Path = Path(".") # Mocked project root

        # Mocked ETHOS configuration dictionary
        ETHOS: RealEthosConfigType = { # type: ignore
            "retrieval_min_salience_for_pathos_context": 0.05,
            "retrieval_limit_for_pathos_context": 3, # Added based on PromptBuilder usage
            "schedule_context_max_items_for_prompt": 2,
            "schedule_context_desc_snippet_len": 25,
            "briefing_context_max_length_for_prompt": 200,
            "aspiration_context_max_items_for_prompt": 2,
            # Add any other keys PromptBuilder.build_main_llm_messages might access from self.config.ETHOS
        }

        LLM_MAX_PROMPT_TOKENS_MAIN: int = 7000
        LLM_RESPONSE_BUFFER_TOKENS: int = 1500
        DYNAMIC_CONTEXT_ENABLED: bool = True
        DYNAMIC_CONTEXT_MAX_RETRIEVED_CHUNKS: int = 1
        DYNAMIC_CONTEXT_SIMILARITY_THRESHOLD: float = 0.65

        # Mocked LLM configurations dictionary
        LLM: Dict[str, RealLLMConfigType] = { # type: ignore
            "PATHOS": {
                "model_name_for_tiktoken": "cl100k_base", # For token estimation
                "supports_vision": False, # For testing non-multimodal path
                "model": "gpt-test-model-for-pathos", # Example model name
                "api_type": "openai", # Example API type
                "api_key_env_var": "DUMMY_API_KEY", # Example env var for API key
                "base_url": "http://localhost:1234/v1", # Example base URL
                # Add other fields as per the actual LLMConfig TypedDict if PromptBuilder uses them
            }
        }

        def get_llm_config(self, role: str) -> Optional[RealLLMConfigType]: # type: ignore
            logger_main.debug(f"MockConfigForPromptBuilder.get_llm_config called for role '{role}'")
            return self.LLM.get(role) # type: ignore

        def get_ethos_config(self) -> RealEthosConfigType: # type: ignore
            logger_main.debug("MockConfigForPromptBuilder.get_ethos_config called")
            return self.ETHOS # type: ignore

        @staticmethod
        def get_nested_value(config_dict: Dict, path: List[str], default: Any = None) -> Any:
            """Helper to get nested values from a dictionary, as used in PromptBuilder."""
            current = config_dict
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current


    async def main_test_runner():
        logger_main.info("Starting PromptBuilder test runner...")

        mock_config_pb = MockConfigForPromptBuilder()
        mock_ethos_pb = MockEthosCore(config_obj=mock_config_pb) # Pass mock config to mock ethos

        # Mock LogosCore
        mock_logos_pb = unittest.mock.AsyncMock(spec=LogosCore) # type: ignore
        async def mock_logos_get_time(location=None):
            logger_main.debug(f"MockLogosCore.execute_get_time called with location: {location}")
            return f"Mock Time from PB Test: {datetime.now(timezone.utc).strftime('%A, %B %d, %Y, %I:%M %p %Z')}"
        mock_logos_pb.execute_get_time = mock_logos_get_time # type: ignore

        # Instantiate PromptBuilder with mocks
        builder = PromptBuilder(config=mock_config_pb, ethos_core=mock_ethos_pb, logos_core=mock_logos_pb) # type: ignore

        logger_main.info("PromptBuilder instantiated with mocks. Building main LLM messages...")

        # Example call to build_main_llm_messages
        # Ensure all required arguments are provided as per the method's signature.
        messages, retrieved_memories, mood, hexus, estimated_tokens = await builder.build_main_llm_messages(
            user_id="test_user_pb_001",
            user_input_text="Hello Pathos, tell me about your personality.",
            history_context=[ # Example history
                {"role": "user", "content": "What was the topic yesterday?"},
                {"role": "assistant", "content": "We were discussing mock objects."}
            ],
            image_data_b64=None, # No image for this test
            vision_description_if_non_multimodal=None,
            document_text=None, # No document for this test
            force_web_search=False,
            engaged_proactive_id=None,
            system_provided_info=None,
            enhanced_pathos_llm_config=mock_config_pb.get_llm_config("PATHOS") # Pass LLM config
        )

        logger_main.info(f"build_main_llm_messages returned. Estimated tokens: {estimated_tokens}. Number of messages: {len(messages)}")

        assert messages, "No messages returned from build_main_llm_messages"
        system_prompt_message = messages[0]
        assert system_prompt_message["role"] == "system", "First message should be a system prompt."

        system_prompt_content = system_prompt_message['content']
        logger_main.debug(f"Generated system prompt content for test:\n{'-'*20}\n{system_prompt_content}\n{'-'*20}")

        # The core assertion: Check for the trait description
        expected_trait_description = "Pathos's key personality characteristics include: Test Trait: Value; Test Verbosity: High."
        assert expected_trait_description in system_prompt_content, \
            f"Trait description '{expected_trait_description}' missing from system prompt."
        logger_main.info(f"Assertion successful: Trait description found in system prompt!")

        # Additional check for other dynamic content (optional, but good for sanity)
        assert "PB Test Directive 1: Be helpful." in system_prompt_content, "Persona directive missing."
        assert "Mock Time from PB Test:" in system_prompt_content, "Mock time missing."
        assert "PB User Profile for test_user_pb_001" in system_prompt_content, "User profile summary missing."
        assert "PB testing activity: Contemplating test assertions." in system_prompt_content, "Activity description missing."
        assert "Valence: 0.20, Arousal: -0.10" in system_prompt_content, "Mood string missing or incorrect." # Note formatting
        assert "joy=0.65" in system_prompt_content, "Hexus scores missing." # Example part of hexus
        assert "PB Schedule Context:" in system_prompt_content, "Schedule context missing."
        assert "PB Aspirations Context:" in system_prompt_content, "Aspirations context missing."
        assert "User previously asked about mock data quality." in system_prompt_content, "Retrieved memory missing."
        assert "PB Daily Briefing:" in system_prompt_content, "Briefing context missing."

        logger_main.info("All basic assertions passed for PromptBuilder test.")

    # Run the async test runner
    try:
        asyncio.run(main_test_runner())
        logger_main.info("PromptBuilder __main__ test run completed successfully.")
    except Exception as e:
        logger_main.error(f"Error during PromptBuilder __main__ test run: {e}", exc_info=True)
