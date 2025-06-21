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
from eidos_agent.schemas import ChatMessage
# PATHOS_USER_ID is used by ToolOrchestrator._execute_tools, but ToolOrchestrator imports it directly.
# from eidos_agent.modules.chronos_engine import PATHOS_USER_ID
# simulation_module is used by ToolOrchestrator._execute_tools, ToolOrchestrator imports it directly.
# from eidos_agent.modules import simulation_module

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.services.external_tts_service import ExternalTTSService

logger = get_logger(__name__)

# Updated internal imports to be relative
from .pathos_tools_definitions import (
    AVAILABLE_TOOLS_FOR_PATHOS_LLM,
    ALL_AVAILABLE_SYSTEM_TOOLS
)
from .prompt_builder import PromptBuilder
from .llm_client import LLMClient
from .tool_orchestrator import ToolOrchestrator


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

        self.prompt_builder = PromptBuilder(self.config, self.ethos_core, self.logos_core)

        timeout_seconds_cfg = self.pathos_llm_config.get('timeout', 300.0) if self.pathos_llm_config else 300.0
        try: timeout_value = float(timeout_seconds_cfg)
        except (ValueError, TypeError): timeout_value = 300.0
        self.http_client = httpx.AsyncClient(timeout=timeout_value)
        self.llm_client = LLMClient(self.http_client)
        self.tool_orchestrator = ToolOrchestrator(self.llm_client, self.logos_core, self.ethos_core) # Instantiate ToolOrchestrator

        self.eidos_tts_service_instance: Optional['ExternalTTSService'] = None
        self.audio_cache: Optional[Dict[str, bytes]] = None
        self.audio_cache_lock: Optional[asyncio.Lock] = None
        logger.info("PathosInterface initialized with PromptBuilder, LLMClient, and ToolOrchestrator.")

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

    def _update_active_user(self, new_user_id: str, set_by_statement: bool = False):
        normalized_id = (new_user_id.lower().strip().replace(" ", "_") if new_user_id else "unknown_user") or "unknown_user"
        if not normalized_id: normalized_id = "unknown_user"
        if self.current_active_user_id != normalized_id:
            logger.info(f"PathosInterface: Active user changed from '{self.current_active_user_id}' to '{normalized_id}'.")
            self.current_active_user_id = normalized_id

    # _call_llm_with_tools and _execute_tools are now moved to ToolOrchestrator

    async def generate_response(
        self,
        user_id: str,
        user_input: str,
        image_data_b64: Optional[str] = None,
        document_text: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        response_metadata: Dict[str, Any] = {}
        req_meta = request_metadata if request_metadata is not None else {}
        user_id_for_response = user_id
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

        system_provided_info_for_prompt: Dict[str, Any] = {}

        initial_llm_messages, retrieved_memories, current_mood, hexus_scores, estimated_prompt_tokens = await self.prompt_builder.build_main_llm_messages(
            user_id=user_id_for_response,
            user_input_text=user_input,
            history_context=req_meta.get('conversation_history', []),
            image_data_b64=image_data_b64,
            vision_description_if_non_multimodal=vision_description_for_non_multimodal_pathos,
            document_text=document_text,
            force_web_search=req_meta.get('force_web_search_requested', False),
            engaged_proactive_id=req_meta.get('engaged_proactive_id'),
            system_provided_info=system_provided_info_for_prompt,
            enhanced_pathos_llm_config=enhanced_pathos_config
        )
        full_history_for_interaction_log: List[Dict[str, Any]] = list(initial_llm_messages)
        llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False
        final_pathos_response_text_parts: List[str] = []; tts_sequence_num = 0
        final_assistant_message_payload_for_response: Optional[Dict[str, Any]] = None

        if not enhanced_pathos_config:
            final_pathos_response_text_parts.append("I'm sorry, my internal configuration is incomplete."); llm_error_occurred = True
        else:
            current_conversation_messages = list(initial_llm_messages)
            # Use self.tool_orchestrator.call_llm_with_tools
            async for item in self.tool_orchestrator.call_llm_with_tools(
                llm_config_to_use=enhanced_pathos_config,
                messages=current_conversation_messages,
                tools_definition=getattr(self, 'AVAILABLE_TOOLS_FOR_PATHOS_LLM', ALL_AVAILABLE_SYSTEM_TOOLS),
                user_id=user_id_for_response,
                stream_tool_calls=True,
                temperature_override=req_meta.get('temperature'),
                max_tokens_override=req_meta.get('max_tokens_override'),
                llm_provider_url_override=req_meta.get('llm_provider_url_override'),
                model_override=req_meta.get('pathos_model_override')
            ):
                item_type = item.get("type"); payload = item.get("payload")
                if item_type == "text_chunk" and isinstance(payload, str):
                    final_pathos_response_text_parts.append(payload)
                    await self.connection_manager.send_personal_message({"type": "text_chunk", "payload": {"text": payload, "sequence": tts_sequence_num}}, user_id_for_response)
                elif item_type == "assistant_message_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "tool_result_chunk" and isinstance(payload, dict): full_history_for_interaction_log.append(payload)
                elif item_type == "final_assistant_message" and isinstance(payload, dict):
                    full_history_for_interaction_log.append(payload); final_assistant_message_payload_for_response = payload
                    if final_content := payload.get("content"):
                        if not "".join(final_pathos_response_text_parts).strip() and isinstance(final_content, str):
                             final_pathos_response_text_parts = [final_content]
                elif item_type == "error_chunk":
                    error_content = payload if isinstance(payload, str) else "Unknown LLM error from stream"
                    final_pathos_response_text_parts.append(f"[{error_content}]")
                    llm_error_occurred = True; full_history_for_interaction_log.append({"role": "system", "content": f"LLM Error: {error_content}"})
                    logger.error(f"LLM error_chunk received: {error_content}"); break
                elif item_type == "usage_chunk": llm_usage_data = payload

        final_pathos_response_text = "".join(final_pathos_response_text_parts).strip()
        if final_assistant_message_payload_for_response and isinstance(final_assistant_message_payload_for_response.get("content"), str) and not final_pathos_response_text:
            final_pathos_response_text = final_assistant_message_payload_for_response["content"]

        final_pathos_response_text = re.sub(r"<think>.*?</think>\s*", "", final_pathos_response_text, flags=re.DOTALL).strip()

        # Process Hexus updates based on successful tool calls
        if self.ethos_core and final_assistant_message_payload_for_response and final_assistant_message_payload_for_response.get("tool_calls"):
            tool_calls_data = final_assistant_message_payload_for_response.get("tool_calls")
            # Need to find corresponding tool results in full_history_for_interaction_log
            # This part is a bit complex as results are separate messages.
            # For simplicity, we'll iterate through tool_calls and assume success if a result for that call_id exists later.
            # A more robust way would be to have tool_orchestrator return explicit success/failure per tool.

            # Create a map of tool_call_id to tool_name
            tool_call_name_map = {}
            if isinstance(tool_calls_data, list):
                for tc in tool_calls_data:
                    if isinstance(tc, dict) and tc.get("id") and tc.get("function"):
                        tool_call_name_map[tc["id"]] = tc["function"].get("name")

            for message in full_history_for_interaction_log:
                if message.get("role") == "tool" and (tool_call_id := message.get("tool_call_id")):
                    tool_name = tool_call_name_map.get(tool_call_id)
                    if not tool_name: continue # Should not happen if history is consistent

                    # Assuming tool execution was successful if we have a "tool" role message with its ID.
                    # More precise success checking would require changes in ToolOrchestrator's output.
                    event_name: Optional[str] = None
                    event_payload: Dict[str, Any] = {"tool_name": tool_name} # Basic payload

                    if tool_name == "web_search":
                        event_name = "TOOL_SUCCESS_WEB_SEARCH"
                    elif tool_name == "add_pathos_event_to_calendar":
                        # Ideally, parse arguments to determine if it's work or leisure
                        # For now, default to a generic or work-related event
                        event_name = "TOOL_SUCCESS_ADD_EVENT_WORK"
                        # Example for future:
                        # try:
                        #     args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                        #     if "leisure" in args.get("event_type", "").lower() or "social" in args.get("event_type", "").lower():
                        #         event_name = "TOOL_SUCCESS_ADD_EVENT_LEISURE"
                        # except json.JSONDecodeError:
                        #     pass
                    elif tool_name == "fetch_weather":
                        event_name = "TOOL_SUCCESS_FETCH_WEATHER"
                    # Add other tool mappings here
                    else:
                        event_name = "TOOL_SUCCESS_GENERIC" # Fallback for unmapped successful tools

                    if event_name:
                        asyncio.create_task(self.ethos_core.process_event_for_hexus_update(event_name, payload=event_payload))

                    # TODO: Add handling for TOOL_FAILURE_GENERIC if ToolOrchestrator provides failure info


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

        if self.ethos_core:
            # Changed from update_mood_on_interaction to process_interaction_for_hexus_update
            self.ethos_core.process_interaction_for_hexus_update(user_input, final_pathos_response_text, bool(image_data_b64), bool(document_text))

        tool_calls_for_metadata = final_assistant_message_payload_for_response.get("tool_calls") if final_assistant_message_payload_for_response else None
        conversation_id = kwargs.get("conversation_id", "unknown_conv_id")

        detected_intent_to_search = False
        original_user_query_for_search = user_input
        pathos_formulated_search_query = None

        if final_pathos_response_text and not tool_calls_for_metadata:
            response_lower = final_pathos_response_text.lower()
            for phrase in self.INTENT_TO_SEARCH_PHRASES:
                if phrase.lower() in response_lower:
                    detected_intent_to_search = True
                    logger.info(f"PathosInterface: Detected intent to search in response: '{final_pathos_response_text}' (Trigger: '{phrase}') for user_id: {user_id_for_response}, conversation_id: {conversation_id}")
                    pathos_formulated_search_query = f"Information related to Pathos's statement: '{final_pathos_response_text}' (Original user query: '{user_input}')"
                    response_metadata["detected_intent_to_search"] = True
                    response_metadata["pathos_stated_intent_text"] = final_pathos_response_text
                    response_metadata["original_user_query_for_search"] = user_input
                    response_metadata["pathos_formulated_search_query_mvp"] = pathos_formulated_search_query
                    break

        if detected_intent_to_search:
            logger.info(f"PathosInterface: TODO - Call Computer Interaction Module with query. User='{original_user_query_for_search}', Pathos Response='{final_pathos_response_text}' for user_id: {user_id_for_response}, conversation_id: {conversation_id}")
            pass

        response_metadata["tool_calls_from_pathos"] = tool_calls_for_metadata
        response_metadata["error_flag"] = llm_error_occurred
        response_metadata["mood_at_response"] = self.ethos_core.get_current_mood() if self.ethos_core else {} # Updated to use new get_current_mood()
        response_metadata["hexus_scores"] = self.ethos_core.get_hexus_scores() if self.ethos_core else {} # Ensure this is up-to-date
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

        proactive_text_content_accumulator = []; llm_usage_data: Optional[Dict[str, Any]] = None; llm_error_occurred = False

        async for item in self.llm_client.call_llm_api(
            llm_config=enhanced_config,
            messages=proactive_messages_for_llm,
            tools_definition=None,
            temperature_override=float(enhanced_config.get('temperature', 0.4)),
            max_tokens_override=150,
            stream=True
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

    async def _store_final_interaction(
        self,
        original_user_input: str,
        pathos_response: str,
        mood_at_response: Dict[str, Any], # Changed from Dict[str, float] to Dict[str, Any] to accommodate new mood structure
        retrieved_memories: List[Dict[str, Any]],
        full_history_for_pathos: List[Dict[str, Any]],
        error: bool = False,
        image_provided_this_turn: bool = False,
        vision_llm_output: Optional[str] = None,
        is_proactive_turn: bool = False,
        forced_action: bool = False
    ):
        """Store the final interaction details in Ethos memory system."""
        if not self.ethos_core:
            logger.error("Cannot store final interaction: EthosCore not available.")
            return

        try:
            # Construct interaction content string
            interaction_content_parts = []
            interaction_content_parts.append(f"User: {original_user_input}")
            
            # Add any vision context if provided
            if image_provided_this_turn and vision_llm_output:
                interaction_content_parts.append(f"\nImage Analysis: {vision_llm_output}")
            
            # Add Pathos's response
            interaction_content_parts.append(f"\nPathos: {pathos_response}")

            # Add any tool usage from the conversation history
            tool_calls = []
            for msg in full_history_for_pathos:
                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])
            if tool_calls:
                interaction_content_parts.append("\nTools Used by Pathos:")
                for tool in tool_calls:
                    interaction_content_parts.append(f"- {tool.get('function', {}).get('name', 'unknown_tool')}")

            # Build metadata
            metadata = {
                "user_id": self.current_active_user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mood_at_response": mood_at_response,
                "is_error": error,
                "is_proactive": is_proactive_turn,
                "had_image": image_provided_this_turn,
                "forced_action": forced_action,
                "retrieved_memory_count": len(retrieved_memories),
                "retrieved_memory_ids": [m.get("id") for m in retrieved_memories if isinstance(m, dict) and "id" in m],
            }

            # Calculate salience based on various factors
            base_salience = 1.0
            if error:
                base_salience *= 1.2  # Errors are more notable
            if is_proactive_turn:
                base_salience *= 1.1  # Proactive interactions are slightly more notable
            if len(retrieved_memories) > 0:
                base_salience *= (1.0 + min(len(retrieved_memories) * 0.05, 0.2))  # More memories = more significant
            
            # Store the interaction in Ethos memory
            await self.ethos_core.add_memory_entry(
                entry_data={
                    "type": "chat_interaction",
                    "content": "\n".join(interaction_content_parts),
                    "metadata": metadata,
                    "salience": base_salience
                },
                user_id_context=self.current_active_user_id
            )

        except Exception as e:
            logger.error(f"Error storing final interaction in Ethos: {e}", exc_info=True)

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
