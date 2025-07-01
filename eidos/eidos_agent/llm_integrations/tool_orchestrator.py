"""
Handles LLM tool orchestration, including managing the tool-calling loop
and executing tools for the Eidos agent, particularly in the context of Pathos.
"""
import logging
import json
from typing import Dict, List, Any, Optional, AsyncGenerator

from eidos_agent.core.config import LLMConfig # For type hinting
from .llm_client import LLMClient # Updated to relative
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Already updated
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Already updated
from eidos_agent.persona_logic.chronos_engine import PATHOS_USER_ID # Already updated
# Updated import for simulation module functions
from ..features.simulation import (
    initiate_simulated_interaction,
    send_message_to_simulated_npc,
    end_simulated_interaction
)

# Tool definitions are not directly needed here if passed into call_llm_with_tools
# However, _execute_tools will need to know about them if it's not generic enough.
# For now, _execute_tools is specific, so it doesn't need them directly.

logger = logging.getLogger(__name__)

class ToolOrchestrator:
    """
    Orchestrates LLM interactions that may involve tool usage, including managing
    the tool-calling loop and dispatching to specific tool execution logic.
    """
    def __init__(self, llm_client: LLMClient, logos_core: LogosCore, ethos_core: EthosCore):
        """
        Initializes the ToolOrchestrator.

        Args:
            llm_client: An instance of LLMClient for making calls to the LLM.
            logos_core: An instance of LogosCore for executing knowledge/action tools.
            ethos_core: An instance of EthosCore for accessing agent's self/state.
        """
        self.llm_client = llm_client
        self.logos_core = logos_core
        self.ethos_core = ethos_core
        logger.info("ToolOrchestrator initialized.")

    async def _execute_tools(self, tool_calls: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """
        Executes the requested tool calls and returns their results.
        (Moved from PathosInterface)
        """
        tool_results_messages = []
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name")
            function_args_str = tool_call.get("function", {}).get("arguments", "{}")
            tool_call_id = tool_call.get("id")

            if not function_name or not tool_call_id:
                logger.warning(f"Tool call missing function name or ID: {tool_call}")
                tool_results_messages.append({
                    "tool_call_id": tool_call_id or "unknown_tool_id",
                    "role": "tool",
                    "name": function_name or "unknown_function",
                    "content": json.dumps({"error": "Tool call missing function name or ID."})
                })
                continue

            logger.info(f"Executing tool: {function_name} (ID: {tool_call_id}) for user '{user_id}'. Args: {function_args_str[:100]}")

            try:
                function_args = json.loads(function_args_str)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON arguments for tool {function_name} (ID: {tool_call_id}): {e}. Args: {function_args_str}")
                tool_results_messages.append({
                    "tool_call_id": tool_call_id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"error": f"Invalid JSON arguments: {e}"})
                })
                continue

            tool_response_content_str = ""
            try:
                # Dispatch to the appropriate execution logic based on function_name
                if function_name == "get_current_time":
                    tool_response_content_str = await self.logos_core.execute_get_time(function_args.get("location"))
                elif function_name == "web_search":
                    tool_response_content_str = json.dumps(await self.logos_core.execute_web_search(function_args.get("query")))
                elif function_name == "math_calculator":
                    tool_response_content_str = await self.logos_core.execute_math_calculation(function_args.get("expression"))
                elif function_name == "get_weather":
                    tool_response_content_str = json.dumps(await self.logos_core.execute_get_weather(function_args.get("location"), user_id_context=user_id))
                elif function_name == "store_user_fact":
                    tool_response_content_str = await self.logos_core.execute_store_user_fact(function_args.get("attribute_name"), function_args.get("attribute_value"), function_args.get("user_statement_context"), user_id)
                elif function_name == "store_world_fact":
                    tool_response_content_str = await self.logos_core.execute_store_world_fact(function_args.get("fact_statement"), function_args.get("source_description"), function_args.get("topic_tags"), function_args.get("confidence_level", 0.8))
                elif function_name == "perform_deep_research":
                    tool_response_content_str = await self.logos_core.execute_deep_research(function_args.get("research_query"), function_args.get("number_of_searches", 3))
                elif function_name == "get_news_headlines":
                    # Call the updated execute_get_news. For now, without query/category from LLM
                    # as tool definition doesn't support it yet.
                    news_items_list = await self.logos_core.execute_get_news(
                        query=function_args.get("query"), # Pass if LLM provides, else None
                        category=function_args.get("category") # Pass if LLM provides, else None
                    )

                    processed_news_for_llm_response = []
                    if news_items_list:
                        for news_item in news_items_list: # news_items_list is already limited by execute_get_news processing logic
                            # a. Store News Summary as Memory
                            news_metadata = {
                                "source_name": news_item.get("source_name", "Unknown Source"),
                                "url": news_item.get("url"),
                                "published_at": news_item.get("published_at"),
                                "title": news_item.get("title"),
                                "classified_sentiment": news_item.get("classified_sentiment"),
                                "user_id": PATHOS_USER_ID # News is general knowledge for Pathos
                            }
                            await self.ethos_core.add_memory_entry(
                                entry_data={
                                    "type": "news_summary",
                                    "content": news_item.get("summary", "Summary not available."),
                                    "metadata": news_metadata,
                                    "salience": 0.55 # Moderately salient
                                },
                                user_id_context=PATHOS_USER_ID
                            )

                            # b. NEW: Subjective Hexus Update
                            news_summary = news_item.get("summary", "Summary not available.")
                            objective_sentiment = news_item.get("classified_sentiment", "neutral_interesting")
                            current_hexus_scores = self.ethos_core.get_hexus_scores() # Sync call
                            all_persona_directives = self.ethos_core.get_persona_directives() # Sync call
                            persona_directives_subset = all_persona_directives[:3] # Take first 3 for brevity

                            valid_subjective_reaction_event_names = [
                                "NEWS_REACTION_PERSONALLY_POSITIVE", "NEWS_REACTION_PERSONALLY_NEGATIVE",
                                "NEWS_REACTION_VALIDATING", "NEWS_REACTION_CONCERNING_PERSONAL",
                                "NEWS_REACTION_CONTRADICTORY", "NEWS_REACTION_MOTIVATING",
                                "NEWS_REACTION_IRRELEVANT", "NEWS_REACTION_INTERESTING_DEEPER",
                                "NEWS_REACTION_ANGER_FRUSTRATION", "NEWS_REACTION_SADDNESS_EMPATHY",
                                "NEWS_REACTION_HOPEFUL_OPTIMISTIC"
                            ]

                            system_prompt_subjective = (
                                "You are an AI assistant helping Pathos determine its personal, subjective reaction to a piece of news. "
                                "Pathos has a defined persona and current internal state (Hexus scores)."
                            )
                            user_prompt_subjective_parts = [
                                "Pathos has encountered the following news:",
                                f"Title: {news_item.get('title', 'N/A')}",
                                f"Summary: {news_summary}",
                                f"This news is generally considered to have an objective sentiment of: {objective_sentiment}.\n",
                                "Pathos's current internal state (Hexus scores):",
                                f"{json.dumps(current_hexus_scores, indent=2)}\n",
                                "Pathos's core persona directives include:"
                            ]
                            for directive in persona_directives_subset:
                                user_prompt_subjective_parts.append(f"- {directive}")
                            if not persona_directives_subset:
                                user_prompt_subjective_parts.append("- N/A")

                            user_prompt_subjective_parts.append(
                                f"\nConsidering all this, what is Pathos's single most fitting *subjective and personal* reaction to this news? "
                                f"Choose ONE from the following list and respond with ONLY the chosen reaction string (e.g., NEWS_REACTION_VALIDATING):\n"
                                f"{', '.join(valid_subjective_reaction_event_names)}"
                            )
                            user_prompt_subjective = "\n".join(user_prompt_subjective_parts)

                            messages_subjective = [
                                {"role": "system", "content": system_prompt_subjective},
                                {"role": "user", "content": user_prompt_subjective}
                            ]

                            subjective_reaction_llm_config = self.logos_core.logos_techne_config # Use LOGOS_TECHNE for now
                            parsed_subjective_reaction = "NEWS_REACTION_INTERESTING_DEEPER" # Default

                            if subjective_reaction_llm_config:
                                logger.debug(f"ToolOrchestrator: Calling LLM for subjective news reaction. News title: '{news_item.get('title')}'")
                                subjective_llm_response_parts = []
                                # Accumulate response from the LLMClient stream
                                async for llm_item in self.llm_client.call_llm_api(
                                    llm_config=subjective_reaction_llm_config,
                                    messages=messages_subjective,
                                    tools_definition=None, # No tools for this call
                                    stream=True,
                                    temperature_override=0.4, # Slightly lower temp for classification
                                    max_tokens_override=50 # Expecting a short string response
                                ):
                                    if isinstance(llm_item, str):
                                        subjective_llm_response_parts.append(llm_item)
                                    elif isinstance(llm_item, dict) and llm_item.get("type") == "error_chunk":
                                        logger.error(f"LLM error during subjective news reaction: {llm_item.get('payload')}")
                                        subjective_llm_response_parts = ["[ERROR]"] # Mark error
                                        break

                                raw_subjective_response = "".join(subjective_llm_response_parts).strip()
                                logger.debug(f"ToolOrchestrator: Raw subjective reaction LLM response: '{raw_subjective_response}'")

                                if raw_subjective_response and not raw_subjective_response.startswith("[ERROR]"):
                                    # Basic parsing: take the first line, remove quotes, strip whitespace
                                    potential_reaction = raw_subjective_response.splitlines()[0].replace('"', '').replace("'", "").strip()
                                    if potential_reaction in valid_subjective_reaction_event_names:
                                        parsed_subjective_reaction = potential_reaction
                                        logger.info(f"ToolOrchestrator: Parsed subjective news reaction: '{parsed_subjective_reaction}' for news '{news_item.get('title')}'")
                                    else:
                                        logger.warning(f"ToolOrchestrator: LLM returned invalid subjective reaction '{potential_reaction}'. Defaulting to {parsed_subjective_reaction}. Raw: '{raw_subjective_response}'")
                                else:
                                     logger.warning(f"ToolOrchestrator: No valid subjective reaction response from LLM for news '{news_item.get('title')}'. Defaulting to {parsed_subjective_reaction}.")
                            else:
                                logger.warning("ToolOrchestrator: LOGOS_TECHNE config not found for subjective news reaction. Defaulting.")

                            await self.ethos_core.process_event_for_hexus_update(
                                event_type=parsed_subjective_reaction,
                                payload={"news_title": news_item.get("title"), "objective_sentiment": objective_sentiment, "source": news_item.get("source_name")}
                            )

                            # c. Format for Pathos LLM (only fully processed items)
                            # The execute_get_news method already limits fully processed items.
                            # We can just use all items returned by it for the LLM response string.
                            processed_news_for_llm_response.append(
                                f"- {news_item.get('source_name', 'N/A')}: {news_item.get('title', 'N/A')} - {news_item.get('summary', 'N/A')}"
                            )

                        if processed_news_for_llm_response:
                            tool_response_content_str = "Recent news headlines:\n" + "\n".join(processed_news_for_llm_response)
                        else:
                            tool_response_content_str = "No news headlines were processed or available."
                    else:
                        tool_response_content_str = "No news headlines found."
                elif function_name == "add_pathos_event": # Uses ethos_core.chronos_bridge_add_event
                    event_id = await self.ethos_core.chronos_bridge_add_event(
                        title=function_args.get("title"),
                        start_date_str=function_args.get("start_date"),
                        end_date_str=function_args.get("end_date"),
                        event_type_str=function_args.get("event_type"),
                        description=function_args.get("description"),
                        location=function_args.get("location"),
                        activity_theme=function_args.get("activity_theme"),
                        planned_sites_or_tasks=function_args.get("planned_sites_or_tasks"),
                        user_id_for_event=PATHOS_USER_ID # Using imported PATHOS_USER_ID
                    )
                    tool_response_content_str = json.dumps({"status": "success", "event_id": event_id, "message": f"Event '{function_args.get('title')}' scheduled."}) if event_id else json.dumps({"status": "error", "message": f"Failed to schedule event '{function_args.get('title')}'."})
                elif function_name == "initiate_simulated_interaction":
                    tool_response_content_str = json.dumps(await initiate_simulated_interaction(function_args.get("npc_name"), function_args.get("npc_role"), function_args.get("npc_description"), function_args.get("initial_context"), function_args.get("pathos_opening_statement")))
                elif function_name == "send_message_to_simulated_npc":
                    tool_response_content_str = json.dumps(await send_message_to_simulated_npc(function_args.get("message_to_npc")))
                elif function_name == "end_simulated_interaction":
                    tool_response_content_str = json.dumps(await end_simulated_interaction())
                else:
                    tool_response_content_str = json.dumps({"error": f"Tool '{function_name}' not implemented."})
            except Exception as e:
                logger.error(f"Error executing tool {function_name} (ID: {tool_call_id}) for user '{user_id}': {e}", exc_info=True)
                tool_response_content_str = json.dumps({"error": f"Error in tool {function_name}: {str(e)}"})

            tool_results_messages.append({
                "tool_call_id": tool_call_id,
                "role": "tool",
                "name": function_name,
                "content": tool_response_content_str
            })
        return tool_results_messages

    async def call_llm_with_tools(
        self,
        llm_config_to_use: LLMConfig,
        messages: List[Dict[str, Any]],
        tools_definition: List[Dict[str, Any]],
        user_id: str,
        stream_tool_calls: bool = False,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
        llm_provider_url_override: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Manages the LLM interaction loop involving tool calls.
        (Moved from PathosInterface)
        """
        current_messages = list(messages)
        max_iterations = llm_config_to_use.get('max_tool_iterations', 3) # Default to 3 if not in config
        llm_error_occurred_in_loop = False

        for i in range(max_iterations):
            logger.info(f"ToolOrchestrator: LLM tool iteration {i + 1}/{max_iterations} for user '{user_id}'. Message count: {len(current_messages)}")
            accumulated_content_chunks: List[str] = []
            llm_had_tool_calls_this_iter = False
            llm_usage_this_iter: Optional[Dict[str, Any]] = None
            assistant_msg_obj_this_iter: Optional[Dict[str, Any]] = None

            async for llm_item in self.llm_client.call_llm_api(
                llm_config=llm_config_to_use,
                messages=current_messages,
                tools_definition=tools_definition,
                stream=True, # Always stream from LLMClient to process chunks
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                llm_provider_url_override=llm_provider_url_override,
                model_override=model_override
            ):
                item_type = llm_item.get("type") if isinstance(llm_item, dict) else "text_chunk_direct_str"
                payload = llm_item.get("payload") if isinstance(llm_item, dict) else llm_item

                if item_type == "text_chunk_direct_str" and isinstance(payload, str):
                    if not llm_had_tool_calls_this_iter: accumulated_content_chunks.append(payload)
                    if stream_tool_calls: yield {"type": "text_chunk", "payload": payload}
                elif item_type == "tool_calls_chunk" and isinstance(payload, dict):
                    llm_had_tool_calls_this_iter = True
                    assistant_msg_obj_this_iter = payload
                    accumulated_content_chunks = []
                elif item_type == "error_chunk":
                    logger.error(f"ToolOrchestrator: Error chunk received from LLMClient: {payload}")
                    yield llm_item; llm_error_occurred_in_loop = True; return
                elif item_type == "usage_chunk":
                    llm_usage_this_iter = payload

            if llm_error_occurred_in_loop: return

            if llm_had_tool_calls_this_iter and assistant_msg_obj_this_iter:
                current_messages.append(assistant_msg_obj_this_iter)
                yield {"type": "assistant_message_chunk", "payload": assistant_msg_obj_this_iter} # Yield the full assistant message with tool_calls

                actual_tool_calls = assistant_msg_obj_this_iter.get("tool_calls", [])
                if not actual_tool_calls: # Should not happen if llm_had_tool_calls_this_iter is True
                    final_text_on_bad_tool = "".join(accumulated_content_chunks).strip() or "Tool call error: LLM indicated tool use but provided no tool calls."
                    logger.warning(f"ToolOrchestrator: LLM indicated tool calls but none were found in message: {assistant_msg_obj_this_iter}")
                    final_msg_obj = {"role": "assistant", "content": final_text_on_bad_tool}
                    current_messages.append(final_msg_obj); yield {"type": "final_assistant_message", "payload": final_msg_obj}
                    if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                    return

                tool_results = await self._execute_tools(actual_tool_calls, user_id)
                for res_msg in tool_results:
                    current_messages.append(res_msg)
                    yield {"type": "tool_result_chunk", "payload": res_msg}

                if i == max_iterations - 1: # Max iterations reached
                    logger.warning(f"ToolOrchestrator: Max tool iterations ({max_iterations}) reached for user '{user_id}'. Forcing final response from LLM.")
                    # Force a final response from the LLM without tools
                    final_prompt_msgs_max = list(current_messages) + [{"role": "user", "content": "Max tool uses reached. Provide your final answer to the original query now based on all available information and tool results."}]
                    final_text_acc_max = []
                    final_usage_max_iter: Optional[Dict[str, Any]] = None
                    async for item_max in self.llm_client.call_llm_api(
                        llm_config=llm_config_to_use, messages=final_prompt_msgs_max, tools_definition=None, stream=True,
                        temperature_override=temperature_override, max_tokens_override=max_tokens_override,
                        llm_provider_url_override=llm_provider_url_override, model_override=model_override
                    ):
                        if isinstance(item_max, str):
                            final_text_acc_max.append(item_max)
                            if stream_tool_calls: yield {"type": "text_chunk", "payload": item_max}
                        elif isinstance(item_max, dict) and item_max.get("type") == "error_chunk":
                            yield item_max; return # Propagate error
                        elif isinstance(item_max, dict) and item_max.get("type") == "usage_chunk":
                            final_usage_max_iter = item_max.get("payload")

                    final_text_max = "".join(final_text_acc_max).strip() or "After multiple tool uses, processing is complete. How else can I help?"
                    final_msg_obj_max = {"role": "assistant", "content": final_text_max}
                    # current_messages.append(final_msg_obj_max) # Avoid adding to history if it's just a fallback
                    yield {"type": "final_assistant_message", "payload": final_msg_obj_max}
                    if final_usage_max_iter: yield {"type": "usage_chunk", "payload": final_usage_max_iter}
                    elif llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter} # Fallback to previous usage
                    return
            else: # No tool calls in this iteration, this is the final text response
                final_text_response = "".join(accumulated_content_chunks).strip()
                if not final_text_response and not llm_error_occurred_in_loop:
                    logger.warning(f"ToolOrchestrator: No text content accumulated and no tool calls in iteration {i+1} for user '{user_id}'.")
                    final_text_response = "I'm not sure how to respond to that. Can you try rephrasing?" if i == 0 else "Okay, I've processed that."

                final_msg_obj = {"role": "assistant", "content": final_text_response}
                # current_messages.append(final_msg_obj) # PathosInterface will add this to its history
                yield {"type": "final_assistant_message", "payload": final_msg_obj}
                if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
                return

        # Fallback if loop completes max_iterations without a natural stop (should be caught by i == max_iterations - 1 logic)
        logger.warning(f"ToolOrchestrator: Tool call loop completed all iterations ({max_iterations}) without a definitive response for user '{user_id}'. This state should ideally be handled within the loop.")
        fallback_text = "I've completed a series of actions. If you need more help, please let me know!"
        if stream_tool_calls and not accumulated_content_chunks : yield {"type": "text_chunk", "payload": fallback_text}
        final_fallback_msg_obj = {"role": "assistant", "content": fallback_text}
        yield {"type": "final_assistant_message", "payload": final_fallback_msg_obj}
        if llm_usage_this_iter: yield {"type": "usage_chunk", "payload": llm_usage_this_iter}
