import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Literal, Union, AsyncGenerator, Tuple
import re
import json
from pathlib import Path
import uuid
import httpx # Keep for self.http_client initialization

from eidos_agent.core.config import Config, LLMConfig
# EthosCore imports are already updated to persona_logic in this file
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry
from eidos_agent.utils.logger import get_logger
from eidos_agent.schemas.oai_schemas import ChatMessage
# PATHOS_USER_ID is used by ToolOrchestrator._execute_tools, but ToolOrchestrator imports it directly.
# from eidos_agent.modules.chronos_engine import PATHOS_USER_ID
# simulation_module is used by ToolOrchestrator._execute_tools, ToolOrchestrator imports it directly.
# from eidos_agent.modules import simulation_module

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.services.external_tts_service import ExternalTTSService
    from eidos_agent.features.firmament.module import FirmamentModule
    # Assuming SubconsciousNodeClient will be created in integrations
    from eidos_agent.integrations.subconscious_node_client import SubconsciousNodeClient
    from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine
    from eidos_agent.features.firmament.core.http_client_manager import HTTPClientManager

# New Schema Imports
from eidos_agent.schemas.llm_schemas import LLMOutput, LLMToolCall, LLMResponsePayload
from eidos_agent.schemas.orchestration_schemas import MainLLMPromptContext
from eidos_agent.schemas.firmament_schemas import NPCInteractionOutput # Renamed from FirmamentNPCResponse
from eidos_agent.schemas.tool_schemas import ToolResult


logger = get_logger(__name__)

# Updated internal imports to be relative
from .pathos_tools_definitions import (
    AVAILABLE_TOOLS_FOR_PATHOS_LLM, # This might be used by PromptBuilder or LogosCore directly
    ALL_AVAILABLE_SYSTEM_TOOLS
)
from .prompt_builder import PromptBuilder
from .llm_client import LLMClient
# ToolOrchestrator might be deprecated or its logic moved into PathosInterface's process_user_interaction loop
# from .tool_orchestrator import ToolOrchestrator


class PathosInterface:
    INTENT_TO_SEARCH_PHRASES = [ # This seems like a specific feature, can be refactored into a tool or different logic
        "look that up", "check online", "find out about that",
        "search for that", "see what i can find", "let me check",
        "i'll try to find that", "i should look into that", "wonder what the web says",
        "let me search that", "i'll google that"
    ]

    def __init__(self,
                 config: Config,
                 ethos_core: EthosCore,
                 logos_core: LogosCore,
                 connection_manager: 'ConnectionManager',
                 firmament_module: 'FirmamentModule',
                 chronos_engine: 'ChronosEngine',
                 # subconscious_node_client: 'SubconsciousNodeClient', # To be added when client is implemented
                 http_client_manager: 'HTTPClientManager' # For LLMClient
                ):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.connection_manager = connection_manager
        self.firmament_module = firmament_module
        self.chronos_engine = chronos_engine
        # self.subconscious_node_client = subconscious_node_client # Will be uncommented when SubconsciousNodeClient is implemented
        self.subconscious_node_client: Optional['SubconsciousNodeClient'] = None # Placeholder for now

        self.pathos_llm_config: Optional[LLMConfig] = config.get_llm_config('PATHOS')
        self._enhanced_pathos_llm_config: Optional[LLMConfig] = None # For auto-detection
        self.current_active_user_id: str = "default_user"

        self.prompt_builder = PromptBuilder(self.config, self.ethos_core, self.logos_core) # LogosCore might provide tool defs to PromptBuilder

        # LLMClient now takes HTTPClientManager
        self.llm_client = LLMClient(http_client_manager)

        # ToolOrchestrator is being replaced by logic within process_user_interaction
        # self.tool_orchestrator = ToolOrchestrator(self.llm_client, self.logos_core, self.ethos_core) # REMOVED

        self.eidos_tts_service_instance: Optional['ExternalTTSService'] = None
        self.audio_cache: Optional[Dict[str, bytes]] = None
        self.audio_cache_lock: Optional[asyncio.Lock] = None
        logger.info("PathosInterface initialized with new dependencies.")

    # --- Start of New Orchestration Methods (Stubbed) ---

    async def gather_context_for_main_llm(self, user_input: str, conversation_history: List[Dict[str, str]]) -> MainLLMPromptContext:
        """Gathers all necessary context from various modules for the Main Pathos LLM."""
        logger.debug(f"Gathering context for user_input: '{user_input[:50]}...'")

        current_mood = await self.ethos_core.get_current_mood_state()
        # Using user_input as query for memories, might need refinement
        # Also, self.current_active_user_id should be set before this is called by process_user_interaction
        recent_memories = await self.ethos_core.get_relevant_memories(query=user_input, user_id_context=self.current_active_user_id, limit=5)
        persona_profile = await self.ethos_core.get_persona_profile()
        current_activity = await self.chronos_engine.get_current_activity_for_user(user_id=self.config.ETHOS.get("pathos_user_id", "pathos")) # Assuming Pathos's schedule

        simulation_context = None
        if self.firmament_module:
            simulation_context = await self.firmament_module.get_current_simulation_context(pathos_user_id=self.config.ETHOS.get("pathos_user_id", "pathos"))

        significant_subconscious_thoughts = []
        if self.subconscious_node_client: # Check if client is available
            # significant_subconscious_thoughts = await self.subconscious_node_client.get_significant_thoughts(limit=3)
            pass # Implement when SubconsciousNodeClient is fully available

        # Convert Pydantic models to dicts for MainLLMPromptContext if necessary, or update MainLLMPromptContext to use the models directly
        # For now, assuming MainLLMPromptContext placeholders are Dict[str, Any]
        # This will require careful mapping or direct use of Pydantic models in MainLLMPromptContext schema.
        # Let's assume for now the schemas are designed to be compatible or direct model usage.

        # Ensure we get the correct user_id for Pathos. This should ideally be a constant.
        # Using a placeholder from config for now.
        pathos_user_id = self.config.ETHOS.get("pathos_user_id", "pathos_agent_id") # Fallback needed if not in EthosConfig type

        current_mood_data = await self.ethos_core.get_current_mood_state()
        # Ensure recent_memories is a list of dicts if models are not directly used in MainLLMPromptContext
        recent_memories_data = await self.ethos_core.get_relevant_memories(query=user_input, user_id_context=self.current_active_user_id, limit=self.config.DYNAMIC_CONTEXT_MAX_RETRIEVED_CHUNKS or 5)
        persona_profile_data = await self.ethos_core.get_persona_profile()
        current_activity_data = await self.chronos_engine.get_current_activity_for_user(user_id=pathos_user_id)

        simulation_context_data = None
        if self.firmament_module:
            simulation_context_data = await self.firmament_module.get_current_simulation_context(pathos_user_id=pathos_user_id)

        significant_subconscious_thoughts_data = []
        if self.subconscious_node_client:
            try:
                # significant_subconscious_thoughts_data = await self.subconscious_node_client.get_significant_thoughts(limit=3)
                logger.debug("SubconsciousNodeClient.get_significant_thoughts call placeholder.") # Placeholder
            except Exception as e_sub:
                logger.warning(f"Failed to get thoughts from subconscious_node_client: {e_sub}")

        return MainLLMPromptContext(
            user_input=user_input,
            conversation_history=conversation_history,
            current_mood=current_mood_data.model_dump() if current_mood_data else None,
            recent_memories=[mem.model_dump() for mem in recent_memories_data] if recent_memories_data else [],
            persona_profile=persona_profile_data.model_dump() if persona_profile_data else None,
            current_activity=current_activity_data.model_dump() if current_activity_data else None,
            simulation_context=simulation_context_data.model_dump() if simulation_context_data else None,
            significant_subconscious_thoughts=[thought.model_dump() for thought in significant_subconscious_thoughts_data] if significant_subconscious_thoughts_data else []
        )

    async def invoke_main_llm(self, prompt_context: MainLLMPromptContext) -> LLMOutput:
        """Constructs prompt, calls main LLM, and parses its output into a structured LLMOutput."""
        logger.debug("Invoking Main Pathos LLM.")

        enhanced_pathos_config = await self._get_enhanced_pathos_llm_config()
        if not enhanced_pathos_config:
            logger.error("Pathos LLM configuration not available for invoke_main_llm.")
            return LLMOutput(raw_text="Error: LLM configuration missing.", dialogue_to_user="I'm having trouble thinking right now due to a configuration issue.")

        # PromptBuilder constructs the messages list for the LLM
        # This will likely involve calling a method on self.prompt_builder
        # For now, creating a placeholder messages list.
        # Actual implementation will require PromptBuilder.build_messages_from_prompt_context to be defined.
        try:
            # Assuming PromptBuilder might raise an error if context is problematic
            llm_messages = await self.prompt_builder.build_messages_from_main_llm_prompt_context(prompt_context, enhanced_pathos_config)
        except Exception as e_prompt:
            logger.error(f"Error building LLM messages from prompt context: {e_prompt}", exc_info=True)
            return LLMOutput(raw_text=f"Error building prompt: {e_prompt}", dialogue_to_user="I had trouble understanding the context for our conversation.")

        if not llm_messages:
            logger.error("PromptBuilder returned empty messages for the LLM.")
            return LLMOutput(raw_text="Error: Empty prompt for LLM.", dialogue_to_user="I'm not sure what to say next, the prompt was empty.")

        # Using the standardized LLMClient
        # For structured parsing, non-streaming (stream=False) is generally easier to start with.
        # Tool definitions would be passed to the LLM if applicable for function calling.
        # The current self.logos_core.get_tools_for_llm() seems to be the source for this.
        tools_for_llm = self.logos_core.get_tools_for_llm(user_id_context=self.current_active_user_id)

        llm_response_payload: LLMResponsePayload = await self.llm_client.call_llm_api(
            llm_config=enhanced_pathos_config,
            messages=llm_messages,
            tools_definition=tools_for_llm if tools_for_llm else None, # Pass tool definitions
            stream=False
        )

        if not llm_response_payload.success() or (llm_response_payload.content is None and not self._check_for_tool_calls_in_raw_response(llm_response_payload)): # check if content is None AND no tool calls in raw
            error_msg = llm_response_payload.error_message or "LLM call failed with no content or tool calls."
            logger.error(f"invoke_main_llm: LLM call failed. Error: {error_msg}")
            return LLMOutput(raw_text=llm_response_payload.content or error_msg, dialogue_to_user=f"I encountered an issue: {error_msg}")

        return await self._parse_raw_llm_response(llm_response_payload) # Pass the full payload

    def _check_for_tool_calls_in_raw_response(self, llm_response_payload: LLMResponsePayload) -> bool:
        """
        Helper to check if the raw LLM response (before full parsing) might contain tool calls.
        This is a placeholder. Actual checking depends on how LLMClient structures raw_response_data.
        """
        # This is a placeholder. The actual logic would inspect llm_response_payload.raw_response_data
        # if we decide to include the full JSON object there.
        # For now, if content is None, we rely on _parse_raw_llm_response to find tool calls in the text.
        # A more robust way: if the LLM returns a structured JSON (not just text) for non-streaming,
        # LLMClient.call_llm_api (non-streaming part) should parse that and LLMResponsePayload would carry it.
        # Let's assume _parse_raw_llm_response will handle extracting tool_calls from content for now.
        return False # Placeholder

    async def _parse_raw_llm_response(self, llm_response_payload: LLMResponsePayload) -> LLMOutput:
        """
        Parses the LLM's raw text from LLMResponsePayload.content to identify dialogue, tool calls, etc.
        This version assumes the LLM might output OpenAI-style tool calls if tools were provided in the prompt,
        or specific XML-like tags for NPC dialogue.
        """
        raw_text = llm_response_payload.content if llm_response_payload.content else ""
        logger.debug(f"Parsing LLM raw response: '{raw_text[:250]}...'")

        dialogue_to_user: Optional[str] = None
        dialogue_to_npc: Optional[str] = None
        target_npc_id: Optional[str] = None
        parsed_tool_calls: List[LLMToolCall] = []

        # Attempt to parse for OpenAI-style tool calls if raw_text might be a JSON string
        # representing the assistant's message with tool_calls.
        # This depends on how `LLMClient.call_llm_api` (non-streaming) structures its `content`
        # when the LLM itself returns a structured message (e.g. from OpenAI API).
        # If `llm_response_payload.content` IS the structured assistant message:
        try:
            # A more robust check: does the raw_text look like it's an assistant message object?
            # For example, if the LLM (like OpenAI) returns a JSON object for the message containing tool_calls.
            # This part is tricky if `llm_response_payload.content` is *always* just the text part.
            # If `LLMClient` puts the full assistant message (potentially a dict with 'content' and 'tool_calls')
            # into `raw_response_data` field of `LLMResponsePayload`, we'd use that.
            # For now, let's assume `raw_text` might contain special structures or needs to be the primary source.

            # Placeholder: If the LLM is prompted to output JSON for actions, try to parse it.
            # Example: LLM outputs: {"action": "tool_call", "tool_name": "X", "tool_arguments": {...}}
            # Or: {"action": "dialogue_npc", "target_npc_id": "Y", "text": "Hello NPC"}
            # Or: {"action": "dialogue_user", "text": "Hello User"}

            # This simplified parser will look for XML-like tags first.
            # If not found, it assumes the text is for the user.

            # 1. Check for NPC Dialogue: <npc_dialogue target_npc_id="NPC_ID_HERE">Message to NPC</npc_dialogue>
            npc_match = re.search(r"<npc_dialogue target_npc_id=['\"](.*?)['\"]>(.*?)</npc_dialogue>", raw_text, re.DOTALL)
            if npc_match:
                target_npc_id = npc_match.group(1).strip()
                dialogue_to_npc = npc_match.group(2).strip()
                # Remove this tag from raw_text if we want to process other parts, or assume it's exclusive.
                # For now, assume it's exclusive or the main content.
                logger.info(f"Parsed NPC dialogue for '{target_npc_id}': '{dialogue_to_npc[:50]}...'")

            # 2. Check for Tool Calls (OpenAI Format - assuming LLMClient might pass this structure if applicable)
            # This part is more complex if we only have raw_text.
            # If the LLM is prompted to produce, e.g., <tool_call id="call_abc" name="tool_name">{"arg": "value"}</tool_call>
            tool_call_pattern = r"<tool_call\s+id=['\"]([^'\"]+)['\"]\s+name=['\"]([^'\"]+)['\"]>(.*?)</tool_call>"
            remaining_text = raw_text
            for match in re.finditer(tool_call_pattern, raw_text, re.DOTALL):
                call_id = match.group(1)
                tool_name = match.group(2)
                args_str = match.group(3).strip()
                try:
                    tool_arguments = json.loads(args_str)
                    if not isinstance(tool_arguments, dict):
                        raise json.JSONDecodeError("Arguments not a dict", args_str, 0)
                    parsed_tool_calls.append(LLMToolCall(id=call_id, type="function", function=FunctionCall(name=tool_name, arguments=json.dumps(tool_arguments)))) # Store args as JSON string
                    logger.info(f"Parsed tool call: ID='{call_id}', Name='{tool_name}', Args='{tool_arguments}'")
                except json.JSONDecodeError as e_json:
                    logger.warning(f"Failed to parse JSON arguments for tool '{tool_name}': {args_str}. Error: {e_json}")
                # Remove the matched tool call from remaining_text to isolate user dialogue
                remaining_text = remaining_text.replace(match.group(0), "", 1).strip()

            if parsed_tool_calls:
                # If there were tool calls, any remaining text might be a concluding remark for the user, or empty.
                if remaining_text:
                    dialogue_to_user = remaining_text
            elif not dialogue_to_npc: # No tool calls and no NPC dialogue found
                dialogue_to_user = raw_text # Assume the entire text is for the user

        except Exception as e:
            logger.error(f"Error during _parse_raw_llm_response: {e}", exc_info=True)
            # Fallback: treat the entire raw_text as dialogue to user in case of parsing error
            dialogue_to_user = raw_text

        return LLMOutput(
            raw_text=raw_text,
            dialogue_to_user=dialogue_to_user.strip() if dialogue_to_user else None,
            dialogue_to_npc=dialogue_to_npc.strip() if dialogue_to_npc else None,
            target_npc_id=target_npc_id,
            tool_calls=parsed_tool_calls if parsed_tool_calls else None
        )

    async def process_user_interaction(self, user_input: str, conversation_history: List[Dict[str, str]], request_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Main entry point for a user interaction turn.
        Orchestrates context gathering, LLM invocation, tool use, NPC interaction, and state updates.
        Returns the final textual response to be delivered to the user.
        """
        # Determine user_id for this interaction turn.
        # Priority: request_metadata.user_id > conversation_history user_id > default_user
        req_meta_user_id = request_metadata.get("user_id") if request_metadata else None
        history_user_id = conversation_history[-1].get("user_id_for_turn") if conversation_history and conversation_history[-1].get("user_id_for_turn") else None # Assuming user_id_for_turn is added to history entries

        effective_user_id = req_meta_user_id or history_user_id or self.current_active_user_id # Fallback to existing active user
        if not effective_user_id or effective_user_id == "unknown_user": # Ensure a more specific ID if possible
            effective_user_id = "default_user"

        self._update_active_user(user_id_from_request=effective_user_id)

        logger.info(f"Processing user interaction for user '{self.current_active_user_id}': '{user_input[:70]}...'")

        # Initialize conversation history for this turn with the current user input
        # The full conversation_history passed in is for context gathering,
        # while turn_specific_history tracks this specific multi-step interaction.
        turn_specific_history: List[Dict[str, Any]] = conversation_history + [{"role": "user", "content": user_input}]

        context = await self.gather_context_for_main_llm(user_input, turn_specific_history)

        MAX_ITERATIONS = self.config.LLM.get("PATHOS", {}).get("max_tool_iterations", 5)
        final_response_to_user = "I'm not sure how to respond to that." # Default error/fallback
        llm_output: Optional[LLMOutput] = None # To store the last llm_output outside loop if needed

        for i in range(MAX_ITERATIONS):
            logger.debug(f"Interaction loop iteration {i+1}/{MAX_ITERATIONS} for user '{self.current_active_user_id}'")
            llm_output = await self.invoke_main_llm(context)

            # Construct assistant message for history based on LLMOutput
            assistant_message_for_history: Dict[str, Any] = {"role": "assistant"}
            if llm_output.tool_calls: # LLM wants to use tools
                # Ensure tool_calls are in the format expected by OpenAI schemas if needed
                # My LLMToolCall -> oai_schemas.ToolCall
                oai_tool_calls = []
                for tc in llm_output.tool_calls:
                    # Assuming LLMOutput.tool_calls directly matches oai_schemas.ToolCall after parsing
                    oai_tool_calls.append(tc.model_dump(exclude_none=True))
                assistant_message_for_history["tool_calls"] = oai_tool_calls
                if llm_output.raw_text and not llm_output.dialogue_to_user and not llm_output.dialogue_to_npc:
                     # Sometimes LLM includes text content alongside tool_calls, which should be part of the assistant message
                     assistant_message_for_history["content"] = llm_output.raw_text

            elif llm_output.dialogue_to_npc: # LLM wants to talk to an NPC
                assistant_message_for_history["content"] = f"<thinking_process>Pathos decides to speak to NPC {llm_output.target_npc_id}.</thinking_process>\n<dialogue_to_npc target_id=\"{llm_output.target_npc_id}\">{llm_output.dialogue_to_npc}</dialogue_to_npc>"

            elif llm_output.dialogue_to_user: # LLM has direct dialogue for the user
                assistant_message_for_history["content"] = llm_output.dialogue_to_user

            else: # Fallback if LLM output is unclear but not an error
                assistant_message_for_history["content"] = llm_output.raw_text # Use raw_text as a last resort

            # Add assistant's action/response to the turn-specific history and context for next iteration
            context.conversation_history.append(assistant_message_for_history)
            turn_specific_history.append(assistant_message_for_history)


            if llm_output.tool_calls:
                logger.info(f"LLM requested tool calls: {[tc.function.name for tc in llm_output.tool_calls]}")
                tool_results: List[ToolResult] = await self.logos_core.execute_tools(llm_output.tool_calls, user_id_context=self.current_active_user_id)

                for tool_idx, tr in enumerate(tool_results):
                    # Default tool response message structure
                    tool_response_content_for_llm = tr.result_summary_for_llm or json.dumps(tr.result_payload)

                    # Specific handling for 'interact_with_npc' results
                    if tr.tool_name == "interact_with_npc" and tr.status == "success" and tr.result_payload:
                        npc_payload = tr.result_payload
                        npc_response_text = npc_payload.get("npc_response")
                        npc_name = npc_payload.get("npc_name_responded", npc_payload.get("npc_id_responded", "NPC"))
                        # current_conv_id = npc_payload.get("conversation_id") # NPCController now manages history internally based on this

                        # Find Pathos's original utterance from the tool call that led to this result
                        pathos_original_utterance_to_npc = "Pathos spoke to the NPC." # Default
                        original_tool_call = None
                        if llm_output.tool_calls and tool_idx < len(llm_output.tool_calls): # Ensure index is valid
                            # Assuming tool_results are in the same order as tool_calls
                            # And that tr.call_id matches llm_output.tool_calls[idx].id
                            # A more robust way is to match tr.call_id with the id in llm_output.tool_calls
                            for tc_original in llm_output.tool_calls:
                                if tc_original.id == tr.call_id:
                                    original_tool_call = tc_original
                                    break

                        if original_tool_call:
                            try:
                                original_args = json.loads(original_tool_call.function.arguments) if isinstance(original_tool_call.function.arguments, str) else original_tool_call.function.arguments
                                pathos_original_utterance_to_npc = original_args.get("utterance", pathos_original_utterance_to_npc)
                            except Exception:
                                logger.warning("Could not parse original utterance for interact_with_npc tool call.")

                        # Remove the standard "tool" role message for this specific tool,
                        # as we will add more descriptive assistant/user like messages.
                        # Instead of adding to history here, we'll modify how it's added below.
                        # We need to make sure the LLM knows Pathos spoke, and then the NPC responded.

                        # 1. Pathos's speech to NPC (already added to history as assistant's tool_call request)
                        # The assistant message with the tool_call (interact_with_npc) is already in history.
                        # We now add the NPC's response as if it's a new message in the dialogue.

                        # 2. NPC's response
                        npc_response_message_for_history = {
                            "role": "assistant", # Or "user" if we want Pathos to treat NPC as external input?
                                                # Let's try "assistant" but with a "name" field to clarify it's an NPC.
                                                # Or, more directly, a "user" role message that represents the NPC.
                                                # The key is how the MAIN Pathos LLM best understands this.
                                                # If we treat NPC response like a user message, Pathos then formulates a reply.
                                                # Let's use a system/context message or a specially formatted user message.
                            "content": f"<npc_response speaker_name=\"{npc_name}\" speaker_id=\"{npc_payload.get('npc_id_responded')}\">\n{npc_response_text}\n</npc_response>"
                            # The content for the next LLM prompt should clearly indicate the NPC spoke.
                            # Using a structured message or clear prefix.
                        }
                        context.conversation_history.append(npc_response_message_for_history)
                        turn_specific_history.append(npc_response_message_for_history)
                        logger.info(f"Appended NPC '{npc_name}' response to history for Main LLM.")

                        # No need to set tool_response_content_for_llm here as we added a more descriptive message.
                        # We skip appending the generic tool role message for this specific tool.
                        continue # Go to next tool result if any, or next iteration of main loop

                    # For other tools, or if interact_with_npc failed:
                    tool_response_message = {
                        "role": "tool",
                        "tool_call_id": tr.call_id,
                        "name": tr.tool_name,
                        "content": tool_response_content_for_llm
                    }
                    context.conversation_history.append(tool_response_message)
                    turn_specific_history.append(tool_response_message)
                continue # Loop back to invoke_main_llm with updated context

            # This elif block for llm_output.dialogue_to_npc is now superseded by the interact_with_npc tool.
            # The LLM should use the tool to talk to NPCs.
            # elif llm_output.dialogue_to_npc and llm_output.target_npc_id and self.firmament_module:
            #     logger.info(f"Pathos to NPC '{llm_output.target_npc_id}': '{llm_output.dialogue_to_npc[:50]}...'")
            #     # ... (old direct NPC dialogue logic) ...
            #     continue # Loop back to invoke_main_llm

            elif llm_output.dialogue_to_user:
                logger.info(f"LLM generated dialogue for user: '{llm_output.dialogue_to_user[:70]}...'")
                final_response_to_user = llm_output.dialogue_to_user
                break

            else:
                logger.warning("LLMOutput had no actionable content. Using raw_text.")
                final_response_to_user = llm_output.raw_text or "I'm a bit unsure how to proceed."
                break

        if i == MAX_ITERATIONS - 1 and llm_output and (llm_output.tool_calls or llm_output.dialogue_to_npc) :
             logger.warning(f"Max interaction iterations ({MAX_ITERATIONS}) reached. Ending turn with last status.")
             final_response_to_user = "I was in the middle of processing that. Could you give me a moment or rephrase?"

        # After loop completion or break (meaning final response for user is determined)
        # Record the interaction and perform other post-interaction tasks
        mood_at_start_of_turn = context.current_mood # This was fetched at the beginning of process_user_interaction

        interaction_log_data = InteractionLog(
            interaction_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc), # Consider timestamp at start of user_input
            user_id=self.current_active_user_id,
            pathos_mood_at_start=mood_at_start_of_turn, # type: ignore # Assuming mood_at_start_of_turn is MoodState compatible
            conversation_turns=turn_specific_history # This contains the full exchange for this turn
        )
        await self.ethos_core.record_interaction_event(interaction_log_data)

        # Update Hexus based on the overall interaction (this might be simplified here)
        # A more nuanced Hexus update could happen inside record_interaction_event or based on final_response_to_user
        await self.ethos_core.process_event_for_hexus_update(
            event_type="GENERAL_INTERACTION", # Or a more specific event based on content/outcome
            payload={"user_input_snippet": user_input[:50], "pathos_response_snippet": final_response_to_user[:50]}
        )

        if self.subconscious_node_client:
            try:
                # Send a summary or key parts to subconscious
                # subconscious_context = f"User: {user_input}\nPathos: {final_response_to_user}"
                # await self.subconscious_node_client.inject_context_to_node("conversation", subconscious_context)
                logger.debug("SubconsciousNodeClient.inject_context_to_node call placeholder.")
            except Exception as e_sub_inject:
                logger.warning(f"Failed to inject context to subconscious_node_client: {e_sub_inject}")

        # TTS Streaming for final_response_to_user (if applicable)
        # This logic can be adapted from the old generate_response method's TTS handling.
        if final_response_to_user and request_metadata and request_metadata.get('auto_tts_enabled_for_response', False):
            if self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
                sentences = re.split(r'(?<=[.!?])\s+', final_response_to_user.strip())
                tts_sequence_num = 0
                for sentence_text in sentences:
                    sentence = sentence_text.strip()
                    if not sentence: continue
                    # Use current_active_user_id for TTS task naming
                    forced_chunk_id = f"chat_tts_main_{self.current_active_user_id}_{uuid.uuid4().hex[:8]}_{tts_sequence_num}"
                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(
                        sentence=sentence,
                        user_id=self.current_active_user_id, # Use the active user ID
                        sequence_num=tts_sequence_num,
                        forced_chunk_id=forced_chunk_id
                    ))
                    tts_sequence_num += 1

        return final_response_to_user

    # --- End of New Orchestration Methods ---

    # The _get_enhanced_pathos_llm_config, set_tts_service, set_audio_cache,
    # get_static_prompt_for_cache_warming, _update_active_user methods remain as they are useful utilities.
    # The old generate_response method and its helper _store_final_interaction will be removed or commented out.
    # Proactive message generation methods (_generate_proactive_message, send_proactive_message)
    # also need review to see if they fit the new orchestration or need adjustment.

    async def _get_enhanced_pathos_llm_config(self) -> Optional[LLMConfig]:
        if self._enhanced_pathos_llm_config is not None:
            return self._enhanced_pathos_llm_config
        self._enhanced_pathos_llm_config = await Config.get_llm_config_with_auto_detection('PATHOS')
        if self._enhanced_pathos_llm_config:
            detected_model = self._enhanced_pathos_llm_config.get('model')
            original_model = self.pathos_llm_config.get('model') if self.pathos_llm_config else None
            if detected_model != original_model and original_model and original_model.lower() == "auto":
                logger.info(f"Enhanced PATHOS config: resolved 'auto' model to '{detected_model}'")
        elif self.pathos_llm_config:
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

    def get_static_prompt_for_cache_warming(self) -> Optional[str]:
        return self.prompt_builder.get_static_system_prompt_content()

    def _update_active_user(self, new_user_id: Optional[str] = None, user_id_from_request: Optional[str] = None, set_by_statement: bool = False):
        # Priority: new_user_id > user_id_from_request > fallback
        effective_new_user_id = new_user_id or user_id_from_request or "unknown_user"

        normalized_id = (effective_new_user_id.lower().strip().replace(" ", "_") if effective_new_user_id else "unknown_user")
        if not normalized_id: normalized_id = "unknown_user" # Ensure it's never empty

        if self.current_active_user_id != normalized_id:
            logger.info(f"PathosInterface: Active user changed from '{self.current_active_user_id}' to '{normalized_id}'.")
            self.current_active_user_id = normalized_id


    # Old generate_response method - COMMENTED OUT as its logic will be replaced by process_user_interaction
    # async def generate_response(
    #     self,
    #     user_id: str,
    #     user_input: str,
    #     image_data_b64: Optional[str] = None,
    #     document_text: Optional[str] = None,
    #     request_metadata: Optional[Dict[str, Any]] = None,
    #     **kwargs: Any
    # ) -> Dict[str, Any]:
    #     response_metadata: Dict[str, Any] = {}
    #     req_meta = request_metadata if request_metadata is not None else {}
    #     user_id_for_response = user_id
    #     self._update_active_user(user_id_for_response)
    #     should_stream_tts_for_this_response = req_meta.get('auto_tts_enabled_for_response', False)
    #     response_metadata["tts_stream_attempted"] = should_stream_tts_for_this_response
    #     if engaged_proactive_id := req_meta.get('engaged_proactive_id'): response_metadata["engaged_proactive_id"] = engaged_proactive_id
    #     logger.info(f"PathosInterface: Processing request for user '{user_id_for_response}' with Main PATHOS LLM.")
    #     vision_description_for_non_multimodal_pathos: Optional[str] = None
    #     enhanced_pathos_config = await self._get_enhanced_pathos_llm_config()
    #     if image_data_b64 and enhanced_pathos_config and not enhanced_pathos_config.get('supports_vision', False) and self.logos_core:
    #         logger.info(f"Pathos LLM for '{user_id_for_response}' not multimodal. Requesting image description.")
    #         vision_prompt = user_input if user_input.strip() else "Describe this image in detail."
    #         try:
    #             vision_description_for_non_multimodal_pathos = await self.logos_core.execute_describe_image(image_data_b64, vision_prompt)
    #             if vision_description_for_non_multimodal_pathos and vision_description_for_non_multimodal_pathos.startswith('{\"error\":'):
    #                 logger.warning(f"LogosCore image description failed: {vision_description_for_non_multimodal_pathos}")
    #                 vision_description_for_non_multimodal_pathos = "[System note: Error processing image description.]"
    #         except Exception as e_vision: logger.error(f"Error getting image description: {e_vision}", exc_info=True); vision_description_for_non_multimodal_pathos = "[System note: Error obtaining image description.]"
    #     system_provided_info_for_prompt: Dict[str, Any] = {}
    #     initial_llm_messages, retrieved_memories, current_mood, hexus_scores, estimated_prompt_tokens = await self.prompt_builder.build_main_llm_messages(
    #         user_id=user_id_for_response,
    #         user_input_text=user_input,
    #         history_context=req_meta.get('conversation_history', []),
    #         image_data_b64=image_data_b64,
    #         vision_description_if_non_multimodal=vision_description_for_non_multimodal_pathos,
    #         document_text=document_text,
    #         force_web_search=req_meta.get('force_web_search_requested', False),
    #         engaged_proactive_id=req_meta.get('engaged_proactive_id'),
    #         system_provided_info=system_provided_info_for_prompt,
    #         enhanced_pathos_llm_config=enhanced_pathos_config
    #     )
    #     full_history_for_interaction_log: List[Dict[str, Any]] = list(initial_llm_messages)
    #     llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
    #     final_pathos_response_text_parts: List[str] = []; tts_sequence_num = 0
    #     final_assistant_message_payload_for_response: Optional[Dict[str, Any]] = None
    #     if not enhanced_pathos_config:
    #         final_pathos_response_text_parts.append("I'm sorry, my internal configuration is incomplete."); llm_error_occurred = True
    #     else:
    #         current_conversation_messages = list(initial_llm_messages)
    #         # This part used self.tool_orchestrator - will be replaced by new loop in process_user_interaction
    #         # async for item in self.tool_orchestrator.call_llm_with_tools(...):
    #         #    ...
    #         logger.warning("generate_response: ToolOrchestrator logic needs to be moved/refactored into process_user_interaction.")
    #         final_pathos_response_text_parts.append("[Old generate_response logic - needs refactor]") # Placeholder
    #
    #     final_pathos_response_text = "".join(final_pathos_response_text_parts).strip()
    #     # ... rest of the old generate_response logic ...
    #     return {"success": not llm_error_occurred, "content": final_pathos_response_text, "metadata": response_metadata}


    async def _generate_proactive_message(self, user_id: str, proactive_type: str, context: Optional[Any] = None) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        enhanced_config = await self._get_enhanced_pathos_llm_config()
        if not enhanced_config: logger.error("Cannot generate proactive message: Pathos LLM not configured."); return None, []

        logger.info(f"Attempting to generate proactive message of type '{proactive_type}' for user '{user_id}'. Context: {str(context)[:100]}")
        prompt_for_llm = ""
        user_name_for_prompt = user_id

        if proactive_type == "greeting":
            time_of_day = context.get("time_of_day", "day") if isinstance(context, dict) else "day"
            prompt_for_llm = f"It's a new {time_of_day} for user '{user_name_for_prompt}'. Generate a VERY CASUAL and brief 'good {time_of_day}' greeting. Think like a relaxed friend. Examples: 'Hey {user_name_for_prompt}, what\\'s up?', 'Mornin {user_name_for_prompt}!', 'Afternoon! How\\'s it hanging?'"
        elif proactive_type == "queued_discussion" and context and isinstance(context, dict):
            topic_content = context.get("topic_content", "something I was thinking about")
            reason = context.get("reason", "earlier thoughts")
            prompt_for_llm = f"You have a queued discussion point for user '{user_name_for_prompt}': '{topic_content}' (Reason: {reason}). Casually and naturally bring this up. Examples: 'Hey {user_name_for_prompt}, something crossed my mind from {reason}... {topic_content} What do you think?', 'I had a thought about {topic_content} earlier, mind if I share?'"
        else:
            logger.warning(f"Proactive message generation: No specific prompt logic for type '{proactive_type}'."); return None, []

        if not prompt_for_llm: logger.warning(f"Proactive message generation: No prompt_for_llm constructed for type '{proactive_type}'."); return None, []

        current_mood_pm = self.ethos_core.get_current_mood() if self.ethos_core else {'valence': 0.0, 'arousal': 0.0}
        hexus_scores_pm = self.ethos_core.get_hexus_scores() if self.ethos_core else {}

        if self.ethos_core:
            persona_directives_for_proactive = "\n".join(self.ethos_core.get_persona_directives())
        else:
            persona_directives_for_proactive = "You are Pathos, a friendly AI."

        system_prompt_content_parts_pm = [
            persona_directives_for_proactive,
            f"\nYou are generating a specific, brief, VERY CASUAL, and proactive message for user '{user_id}'.",
            f"Your current mood is valence {current_mood_pm['valence']:.2f}, arousal {current_mood_pm['arousal']:.2f}.",
            "(Current Hexus Scores: " + ", ".join([f"{k}={v:.2f}" for k, v in hexus_scores_pm.items()]) + ")",
            "Be concise and natural, consistent with your friendly and relaxed persona. Use contractions.",
            "Your response should ONLY be the proactive message text. Do not include any other text or formatting."
        ]
        system_prompt_content_pm = "\n".join(system_prompt_content_parts_pm)
        proactive_messages_for_llm = [{"role": "system", "content": system_prompt_content_pm}, {"role": "user", "content": prompt_for_llm}]

        proactive_text_content: Optional[str] = None
        llm_error_occurred = False

        # Call LLM (non-streaming for a single proactive message)
        llm_response: LLMResponsePayload = await self.llm_client.call_llm_api(
            llm_config=enhanced_config,
            messages=proactive_messages_for_llm,
            # tools_definition=None, # No tools for proactive messages typically
            temperature_override=float(enhanced_config.get('temperature', 0.7)), # Temp might be different for proactive
            max_tokens_override=150, # Proactive messages should be concise
            stream=False
        )

        if llm_response.success() and llm_response.content:
            proactive_text_content = llm_response.content.strip()
            # Further processing like stripping <think> tags
            proactive_text_content = re.sub(r"<think>.*?</think>\s*", "", proactive_text_content, flags=re.DOTALL).strip()
            if not proactive_text_content:
                logger.warning(f"Proactive message for '{proactive_type}' empty after stripping think tags or initial processing.")
                proactive_text_content = None # Ensure it's None if truly empty
        else:
            logger.warning(f"Proactive message generation LLM call failed or returned no content. Error: {llm_response.error_message}")
            llm_error_occurred = True
            proactive_text_content = None

        if proactive_text_content: # Check if content is not None and not empty
            logger.info(f"Generated proactive message text for '{proactive_type}': {proactive_text_content[:100]}...")
            audio_chunk_info_list: List[Dict[str, Any]] = []; tts_sequence_num_proactive = 0
            if self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
                sentences = re.split(r'(?<=[.!?])\s+', proactive_text_content.strip())
                for sentence_text in sentences:
                    sentence = sentence_text.strip();
                    if not sentence: continue
                    forced_chunk_id = f"proactive_tts_{user_id}_{uuid.uuid4().hex[:10]}_{tts_sequence_num_proactive}"
                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id, sequence_num=tts_sequence_num_proactive, forced_chunk_id=forced_chunk_id, chunk_id_prefix="proactive_tts_"))
                    tts_sequence_num_proactive += 1
            return proactive_text_content, audio_chunk_info_list
        else:
            logger.warning(f"Proactive message generation for '{proactive_type}' failed or resulted in empty content.")
            return None, []

    async def send_sentence_to_tts_and_notify_client(self, sentence: str, user_id: str, sequence_num: int, forced_chunk_id: Optional[str] = None, chunk_id_prefix: str = "chat_tts_main_"):

            logger.info(f"Generated proactive message text for '{proactive_type}': {proactive_text_content[:100]}...")
            audio_chunk_info_list: List[Dict[str, Any]] = []; tts_sequence_num_proactive = 0
            if self.eidos_tts_service_instance and self.eidos_tts_service_instance.is_available() and self.audio_cache is not None:
                sentences = re.split(r'(?<=[.!?])\s+', proactive_text_content.strip())
                for sentence_text in sentences:
                    sentence = sentence_text.strip();
                    if not sentence: continue
                    forced_chunk_id = f"proactive_tts_{user_id}_{uuid.uuid4().hex[:10]}_{tts_sequence_num_proactive}"
                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(sentence=sentence, user_id=user_id, sequence_num=tts_sequence_num_proactive, forced_chunk_id=forced_chunk_id, chunk_id_prefix="proactive_tts_"))
                    tts_sequence_num_proactive += 1
            return proactive_text_content, audio_chunk_info_list
        else:
            logger.warning(f"Proactive message generation for '{proactive_type}' failed or resulted in empty content. LLM response/error: {proactive_text_content}")
            return None, []

    async def send_sentence_to_tts_and_notify_client(self, sentence: str, user_id: str, sequence_num: int, forced_chunk_id: Optional[str] = None, chunk_id_prefix: str = "chat_tts_main_"):
        if not self.eidos_tts_service_instance or not self.connection_manager or self.audio_cache is None or not self.eidos_tts_service_instance.is_available():
            logger.error(f"TTS prerequisites missing for user {user_id}. TTS Service: {self.eidos_tts_service_instance}, ConnMgr: {self.connection_manager}, AudioCache: {self.audio_cache}, TTS Available: {self.eidos_tts_service_instance.is_available() if self.eidos_tts_service_instance else False}"); return

        final_chunk_id = forced_chunk_id if forced_chunk_id else f"{chunk_id_prefix}{user_id}_{uuid.uuid4().hex[:10]}_{sequence_num}"
        log_prefix = f"FORCED_ID({final_chunk_id})" if forced_chunk_id else f"PREFIX({chunk_id_prefix})"
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
            "processed_by_reflection": False,
            **feedback_data
        }
        feedback_content_str = json.dumps(feedback_data)

        if self.ethos_core:
            await self.ethos_core.add_memory_entry(
                {"type": "feedback", "content": feedback_content_str, "metadata": memory_metadata, "salience": 1.2},
                user_id_context=feedback_user_id
            )
            if self.config.ENABLE_MOOD_SIMULATION: # This flag now gates Hexus updates too
                # Determine feedback event name
                feedback_type_str = str(feedback_data.get("feedback_type", "unknown")).upper()
                event_name = f"USER_FEEDBACK_{feedback_type_str}"
                if event_name not in self.ethos_core.HEXUS_EVENT_DEFINITIONS: # Accessing class variable for check
                    logger.warning(f"Undefined Hexus feedback event '{event_name}'. Defaulting or skipping.")
                    # Potentially default to a generic feedback event or skip
                    event_name = "USER_FEEDBACK_POSITIVE" if feedback_data.get("rating", 0) > 0 else "USER_FEEDBACK_NEGATIVE" # Simplified default

                await self.ethos_core.process_event_for_hexus_update(event_name, payload=feedback_data)
        else:
            logger.error("EthosCore not available in PathosInterface, cannot process feedback.")

    async def close(self):
        try:
            if hasattr(self, 'http_client') and self.http_client and not self.http_client.is_closed:
                await self.http_client.aclose()
                logger.info("PathosInterface: HTTP client closed.")
        except Exception as e: logger.error(f"Error closing PathosInterface resources: {e}", exc_info=True)
        logger.info("PathosInterface closed.")

    # Removed _store_final_interaction method. Its logic is now integrated into
    # process_user_interaction through ethos_core.record_interaction_event.

    async def send_proactive_message(
        self,
        user_id: str,
        message_type: str, # e.g., "proactive_greeting", "proactive_queued_topic"
        message_content: str,
        context_data: Optional[Dict[str, Any]] = None # e.g., the queued point memory for context
    ):
        """
        Sends a fully formulated proactive message to a user and handles TTS.
        This method does NOT call an LLM to generate the message_content.
        """
        if not user_id or not message_content:
            logger.warning(f"PathosInterface: Attempted to send proactive message with missing user_id or content. User: {user_id}, Type: {message_type}")
            return

        logger.info(f"PathosInterface: Sending proactive message. User: '{user_id}', Type: '{message_type}', Content: '{message_content[:70]}...'")

        # 1. Send the text message via WebSocket
        if self.connection_manager:
            ws_payload = {
                "type": "proactive_message", # A distinct WebSocket message type
                "payload": {
                    "message_type": message_type,
                    "text": message_content,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "context": context_data if context_data else {} # Include any relevant context
                }
            }
            try:
                await self.connection_manager.send_personal_message(ws_payload, user_id)
                logger.debug(f"PathosInterface: Proactive text message sent to user '{user_id}'.")
            except Exception as e:
                logger.error(f"PathosInterface: Error sending proactive text message to user '{user_id}': {e}", exc_info=True)
        else:
            logger.error("PathosInterface: ConnectionManager not available. Cannot send proactive text message.")

        # 2. Handle TTS for the proactive message
        should_stream_tts = (
            self.eidos_tts_service_instance and
            self.eidos_tts_service_instance.is_available() and
            self.audio_cache is not None
        )

        if should_stream_tts:
            logger.debug(f"PathosInterface: Attempting TTS for proactive message to user '{user_id}'.")
            proactive_tts_chunk_id_prefix = f"proactive_tts_{message_type}_{user_id}_"
            tts_sequence_num = 0
            try:
                sentences = re.split(r'(?<=[.!?])\s+', message_content.strip())
                for sentence_text in sentences:
                    sentence = sentence_text.strip()
                    if not sentence:
                        continue

                    forced_chunk_id = f"{proactive_tts_chunk_id_prefix}{uuid.uuid4().hex[:8]}_{tts_sequence_num}"

                    asyncio.create_task(self.send_sentence_to_tts_and_notify_client(
                        sentence=sentence,
                        user_id=user_id,
                        sequence_num=tts_sequence_num,
                        forced_chunk_id=forced_chunk_id,
                        chunk_id_prefix="proactive_tts_"
                    ))
                    tts_sequence_num += 1
                logger.info(f"PathosInterface: Queued {tts_sequence_num} sentence(s) for proactive TTS for user '{user_id}'.")
            except Exception as e_tts:
                logger.error(f"PathosInterface: Error during proactive message TTS processing for user '{user_id}': {e_tts}", exc_info=True)
        else:
            logger.debug(f"PathosInterface: Proactive TTS not attempted for user '{user_id}' (service unavailable or cache missing).")

if __name__ == '__main__':
    import unittest.mock

    # Basic Config for PathosInterface testing
    class MockConfigForPathosInterface:
        def __init__(self):
            self.LLM: Dict[str, LLMConfig] = { # type: ignore
                "PATHOS": {"url": "dummy_pathos_url", "model": "dummy_pathos_model", "timeout": 30.0},
                "LOGOS_VISION": {"url": "dummy_vision_url", "model": "dummy_vision_model"}, # For vision description
            }
            self.ENABLE_PROACTIVE_BEHAVIOR = True # Assuming needed for EthosCore mock
            self.ENABLE_LEARNING_FROM_FEEDBACK = True # Assuming needed for EthosCore mock
            self.ENABLE_MOOD_SIMULATION = True
            self.DYNAMIC_CONTEXT_ENABLED = True
            self.DYNAMIC_CONTEXT_MAX_RETRIEVED_CHUNKS = 1
            self.DYNAMIC_CONTEXT_SIMILARITY_THRESHOLD = 0.75
            self.ETHOS = { # Mock EthosConfig part
                "persona_traits_file_path": "dummy_traits.json", # EthosCore might try to load this
                 "retrieval_min_salience_for_pathos_context": 0.1,
                 "retrieval_limit_for_pathos_context": 3,
            }


        def get_llm_config(self, role: str) -> Optional[LLMConfig]: # type: ignore
            return self.LLM.get(role)

        def get_ethos_config(self): # Mimic real Config
            return self.ETHOS

        @staticmethod
        async def get_llm_config_with_auto_detection(role: str) -> Optional[LLMConfig]:
            # Simplified for mock: return the base config directly
            return MockConfigForPathosInterface().LLM.get(role)


    # Mock External Services
    MockEthosCore = unittest.mock.AsyncMock(spec=EthosCore)
    MockLogosCore = unittest.mock.AsyncMock(spec=LogosCore)
    MockConnectionManager = unittest.mock.AsyncMock(spec='eidos_agent.core.connection_manager.ConnectionManager') # Use string path if class not directly available
    MockExternalTTSService = unittest.mock.AsyncMock(spec='eidos_agent.services.external_tts_service.ExternalTTSService') # Use string path

    async def main_test_runner():
        # Setup basic logging for the test
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger_main_test = logging.getLogger("pathos_interface_main_test")

        mock_config = MockConfigForPathosInterface()

        # Instantiate mocks for EthosCore and LogosCore
        mock_ethos = MockEthosCore()
        mock_ethos.get_persona_directives.return_value = ["Be a test AI."]
        mock_ethos.get_current_mood.return_value = {"name": "neutral", "valence": 0.0, "arousal": 0.0}
        mock_ethos.get_current_activity_description.return_value = "testing"
        mock_ethos.get_hexus_scores.return_value = {}
        mock_ethos.get_user_profile_summary.return_value = "Test user profile."
        mock_ethos.get_pathos_schedule_context_for_prompt.return_value = "Test schedule."
        mock_ethos.get_pathos_aspirations_context_for_prompt.return_value = "Test aspirations."
        mock_ethos.retrieve_relevant_memories.return_value = []
        mock_ethos.get_todays_briefing_context_for_prompt.return_value = "Test briefing."
        # Mock for traits integration in PromptBuilder
        mock_ethos.traits_engine = unittest.mock.Mock()
        mock_ethos.traits_engine.get_descriptive_trait_summary.return_value = "Test personality traits."


        mock_logos = MockLogosCore()
        mock_logos.execute_get_time.return_value = datetime.now(timezone.utc).isoformat()


        mock_conn_mgr_instance = MockConnectionManager()

        pathos_iface = PathosInterface(mock_config, mock_ethos, mock_logos, mock_conn_mgr_instance) # type: ignore

        # Setup TTS Service and Cache for proactive message test
        mock_tts_service_instance = MockExternalTTSService()
        mock_tts_service_instance.is_available.return_value = True
        pathos_iface.set_tts_service(mock_tts_service_instance) # Use the setter

        pathos_iface.audio_cache = {}
        pathos_iface.audio_cache_lock = asyncio.Lock()

        # Patch the method that actually does the TTS sending for this unit test
        with unittest.mock.patch.object(pathos_iface, 'send_sentence_to_tts_and_notify_client', new_callable=unittest.mock.AsyncMock) as mock_send_tts_chunk:
            logger_main_test.info("\n--- Testing send_proactive_message ---")
            test_user_id = "user_proactive_test_01"
            test_message_type = "test_proactive_greeting"
            test_message_content = "Hello there, friend! How are you doing today?" # Two sentences
            test_context_data = {"source": "test_trigger"}

            await pathos_iface.send_proactive_message(test_user_id, test_message_type, test_message_content, test_context_data)

            # Check ConnectionManager call
            mock_conn_mgr_instance.send_personal_message.assert_called_once()
            args_cm, _ = mock_conn_mgr_instance.send_personal_message.call_args
            sent_payload_cm = args_cm[0]
            sent_to_user_cm = args_cm[1]

            assert sent_to_user_cm == test_user_id
            assert sent_payload_cm["type"] == "proactive_message"
            assert sent_payload_cm["payload"]["message_type"] == test_message_type
            assert sent_payload_cm["payload"]["text"] == test_message_content
            assert sent_payload_cm["payload"]["context"] == test_context_data
            logger_main_test.info("send_personal_message call verified for proactive message.")

            # Check if TTS was attempted (split into 2 sentences)
            assert mock_send_tts_chunk.call_count == 2, f"Expected 2 TTS calls, got {mock_send_tts_chunk.call_count}"

            first_tts_call_args = mock_send_tts_chunk.call_args_list[0].kwargs
            assert first_tts_call_args.get("sentence") == "Hello there, friend!"
            assert first_tts_call_args.get("user_id") == test_user_id
            assert first_tts_call_args.get("chunk_id_prefix") == "proactive_tts_"

            second_tts_call_args = mock_send_tts_chunk.call_args_list[1].kwargs
            assert second_tts_call_args.get("sentence") == "How are you doing today?"
            assert second_tts_call_args.get("user_id") == test_user_id
            logger_main_test.info("send_sentence_to_tts_and_notify_client calls verified for proactive message.")

            logger_main_test.info("--- send_proactive_message test passed basic checks. ---")

        # Test with TTS disabled
        mock_tts_service_instance.is_available.return_value = False # Disable TTS
        mock_send_tts_chunk.reset_mock()
        mock_conn_mgr_instance.send_personal_message.reset_mock()

        with unittest.mock.patch.object(pathos_iface, 'send_sentence_to_tts_and_notify_client', new_callable=unittest.mock.AsyncMock) as mock_send_tts_chunk_disabled:
            logger_main_test.info("\n--- Testing send_proactive_message (TTS Disabled) ---")
            await pathos_iface.send_proactive_message(test_user_id, "tts_disabled_test", "Single sentence.")
            mock_conn_mgr_instance.send_personal_message.assert_called_once() # Still sends text
            mock_send_tts_chunk_disabled.assert_not_called() # TTS method should not be called
            logger_main_test.info("send_proactive_message with TTS disabled verified.")


        logger_main_test.info("\n--- PathosInterface __main__ tests finished ---")

    asyncio.run(main_test_runner())
