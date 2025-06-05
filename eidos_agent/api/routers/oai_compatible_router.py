"""
API Router for OpenAI Compatible Endpoints in the Eidos Agent.

This module defines routes that mimic the OpenAI API structure, such as
/v1/models and /v1/chat/completions, allowing Eidos to be used as a
drop-in replacement for some OpenAI API calls.
"""
import logging
import uuid
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Literal, Union

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field, ValidationError # Added ValidationError

# Imports from eidos_agent.schemas
from eidos_agent.schemas import (
    ModelList, ModelCard,
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
    ChatCompletionChoice, ChatCompletionUsage
)

# Imports for Eidos core components (will be injected)
from eidos_agent.core.config import Config
from eidos_agent.core.input_router import InputRouter, RoutingResult
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import

from eidos_agent.llm_integrations.pathos_interface import PathosInterface # Updated import path
test
from eidos_agent.core.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["OpenAI Compatible"]
)

# --- Module-level globals for dependency injection ---
_config: Optional[Config] = None
_input_router: Optional[InputRouter] = None
_ethos_core: Optional[EthosCore] = None
_logos_core: Optional[LogosCore] = None
_pathos_interface: Optional[PathosInterface] = None
_manager: Optional[ConnectionManager] = None # Although not directly used by these specific endpoints, it's part of the core components.

def init_oai_router(
    config_instance: Config,
    input_router_instance: InputRouter,
    ethos_core_instance: EthosCore, # Added to match main.py globals
    logos_core_instance: LogosCore, # Added
    pathos_interface_instance: PathosInterface, # Added
    conn_manager_instance: ConnectionManager # Added
):
    """
    Initializes the OpenAI Compatible Router with necessary Eidos core component instances.
    This function is called during application startup.
    """
    global _config, _input_router, _ethos_core, _logos_core, _pathos_interface, _manager
    _config = config_instance
    _input_router = input_router_instance
    _ethos_core = ethos_core_instance
    _logos_core = logos_core_instance
    _pathos_interface = pathos_interface_instance
    _manager = conn_manager_instance

    logger.info("OpenAI Compatible Router initialized with Eidos core components.")

# --- Helper Functions (Moved from main.py) ---
def _extract_input_to_eidos_format(body: dict, request_id: str, user_id_from_header: Optional[str]) -> dict:
    raw_user_id_from_payload = body.get('user')
    effective_raw_user_id: Optional[str] = user_id_from_header or raw_user_id_from_payload or 'api_guest_user'
    final_user_id = 'api_guest_user'
    if effective_raw_user_id and isinstance(effective_raw_user_id, str):
        normalized = effective_raw_user_id.lower().strip().replace(" ", "_")
        if normalized: final_user_id = normalized
    logger.debug(f"Request {request_id}: User ID. Header: '{user_id_from_header}', Payload: '{raw_user_id_from_payload}'. Final: '{final_user_id}'.")
    temperature_from_body = body.get('temperature')
    model_from_body = body.get('model')
    max_tokens_override, llm_provider_url_override, auto_tts_enabled, engaged_proactive_id_from_meta = None, None, False, None
    body_metadata_dict = body.get('metadata')
    if body_metadata_dict and isinstance(body_metadata_dict, dict):
        logger.debug(f"Request {request_id}: Eidos 'metadata' block: {body_metadata_dict}")
        if (mto_raw := body_metadata_dict.get('max_tokens_override')) is not None:
            try: max_tokens_override = int(mto_raw)
            except ValueError: logger.warning(f"Invalid max_tokens_override: '{mto_raw}'.")
        llm_provider_url_override = body_metadata_dict.get('llm_provider_url_override')
        if isinstance(body_metadata_dict.get('auto_tts_enabled_for_response'), bool):
            auto_tts_enabled = body_metadata_dict['auto_tts_enabled_for_response']
        engaged_proactive_id_from_meta = body_metadata_dict.get('engaged_proactive_id')
    input_data: Dict[str, Any] = {
        "type": "text", "text_content": "", "image_content_b64": None, "document_text": None,
        "metadata": {
            "conversation_history": [], "source": "api_openai_compat_new_parser",
            "timestamp": datetime.now(timezone.utc).isoformat(), "user_id": final_user_id,
            "temperature": temperature_from_body, "max_tokens_override": max_tokens_override,
            "llm_provider_url_override": llm_provider_url_override, "pathos_model_override": model_from_body,
            "engaged_proactive_id": engaged_proactive_id_from_meta, "force_web_search_requested": False,
            "auto_tts_enabled_for_response": auto_tts_enabled
        }
    }
    messages = body.get("messages", [])
    if not messages: _log_final_parsed_input(request_id, final_user_id, input_data); return input_data
    if len(messages) > 1:
        for msg_dict in messages[:-1]:
            role, content, tool_calls, tool_call_id = msg_dict.get("role"), msg_dict.get("content"), msg_dict.get("tool_calls"), msg_dict.get("tool_call_id")
            if role not in ["system", "user", "assistant", "tool"]: continue
            entry: Dict[str, Any] = {"role": role}
            if isinstance(content, str): entry["content"] = content
            elif isinstance(content, list):
                text_parts_hist, img_present_hist = [], False
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text": text_parts_hist.append(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url": img_present_hist = True
                final_hist_text = " ".join(text_parts_hist).strip()
                if img_present_hist: final_hist_text += " [Image was present in history]" if final_hist_text else "[Image was present in history]"
                entry["content"] = final_hist_text.strip() or None
            elif content is not None: entry["content"] = str(content)
            if tool_calls: entry["tool_calls"] = tool_calls
            if role == "tool" and tool_call_id: entry["tool_call_id"] = tool_call_id
            if entry.get("content") or entry.get("tool_calls"): input_data["metadata"]["conversation_history"].append(entry)
    last_msg = messages[-1]; last_content_req = last_msg.get("content", ""); current_input_text_parts = []
    if isinstance(last_content_req, str): current_input_text_parts.append(last_content_req)
    elif isinstance(last_content_req, list):
        input_data["type"] = "multimodal_input"
        for part_item in last_content_req:
            if isinstance(part_item, dict):
                part_type = part_item.get("type")
                if part_type == "text":
                    text_part_content = part_item.get("text", "")
                    doc_match = re.search(r"--- Uploaded Document Content ---\n([\s\S]*?)\n--- End Uploaded Document Content ---", text_part_content)
                    if doc_match:
                        input_data["document_text"] = doc_match.group(1).strip()
                        current_input_text_parts.append(text_part_content.split("--- Uploaded Document Content ---")[0].strip())
                        current_input_text_parts.append(text_part_content.split("--- End Uploaded Document Content ---")[-1].strip())
                    else: current_input_text_parts.append(text_part_content)
                elif part_type == "image_url":
                    img_url_data = part_item.get("image_url", {})
                    if isinstance(img_url_data, dict) and (url_str := img_url_data.get("url")) and url_str.startswith("data:image"):
                        try: input_data["image_content_b64"] = url_str.split(",", 1)[1]
                        except IndexError: logger.error(f"Malformed base64 image URI: {url_str[:60]}...")
            else: current_input_text_parts.append(str(part_item))
    raw_text_proc = " ".join(filter(None, current_input_text_parts)).strip()
    FORCE_SEARCH_PREFIX = "[FORCE_WEB_SEARCH] "
    if raw_text_proc.startswith(FORCE_SEARCH_PREFIX):
        input_data["metadata"]["force_web_search_requested"] = True
        input_data["text_content"] = raw_text_proc[len(FORCE_SEARCH_PREFIX):].strip()
    else: input_data["text_content"] = raw_text_proc
    if isinstance(input_data["text_content"], str) and "#### Tools Available" in input_data["text_content"]:
        input_data["text_content"] = input_data["text_content"].split("#### Tools Available")[0].strip()
    _log_final_parsed_input(request_id, final_user_id, input_data); return input_data

def _log_final_parsed_input(request_id: str, final_user_id: str, input_data: Dict[str, Any]):
    metadata = input_data.get("metadata", {})
    logger.info(
        f"Request {request_id}: Parsed. User:'{final_user_id}'. Type:{input_data['type']}. "
        f"TTS:{metadata.get('auto_tts_enabled_for_response')}. FS:{metadata.get('force_web_search_requested')}. "
        f"Img:{bool(input_data['image_content_b64'])}. Doc:{bool(input_data['document_text'])}. "
        f"Temp:{metadata.get('temperature')}. MaxTokOverride:{metadata.get('max_tokens_override')}. "
        f"LLMOverride:{metadata.get('llm_provider_url_override')}. PathosModel:{metadata.get('pathos_model_override')}. "
        f"EngagedProID:{metadata.get('engaged_proactive_id')}. Hist:{len(metadata.get('conversation_history', []))}. "
        f"Text:'{str(input_data.get('text_content', ''))[:70]}...'"
    )

# --- API Endpoints ---
@router.get("/v1/models", response_model=ModelList)
async def list_models_endpoint():
    logger.info("Request received for /v1/models")
    if not _config: # Check if config is injected
        logger.error("LLM configuration (via _config) not available in oai_router.")
        raise HTTPException(status_code=503, detail="System configuration not ready.")

    model_id = _config.LLM['PATHOS']['model'] if _config.LLM and _config.LLM.get('PATHOS') and _config.LLM['PATHOS'].get('model') else 'eidos-agent'
    model_id = model_id.split('#')[0].strip() if model_id else 'eidos-agent'
    eidos_model_card = ModelCard(id=model_id, owned_by="eidos-project")
    logger.info(f"Reporting model ID: {model_id}")
    return ModelList(data=[eidos_model_card])

@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(fastapi_request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    # Use injected components: _input_router, _ethos_core, _logos_core, _pathos_interface, _manager
    if not all([_input_router, _ethos_core, _logos_core, _pathos_interface, _manager]):
        logger.error("Core Eidos components not fully ready in oai_router.")
        raise HTTPException(status_code=503, detail="Eidos system core components not fully ready.")

    request_id = str(uuid.uuid4()); logger.critical(f">>> Request {request_id}: chat_completions ENTERED <<<"); logger.info(f"Request {request_id}: X-User-Id Header: '{x_user_id}'")
    try: body = await fastapi_request.json()
    except json.JSONDecodeError: logger.error(f"Request {request_id}: Invalid JSON body."); raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        parsed_request = ChatCompletionRequest(**body)
        if parsed_request.stream:
            logger.warning(f"Request {request_id}: Client requested streaming (stream=true), but this endpoint returns full text. TTS audio is streamed via WebSocket if enabled.")
        logger.info(f"Request {request_id}: Validated request. Model='{parsed_request.model}', Messages={len(parsed_request.messages)}")
    except ValidationError as pydantic_exc: logger.error(f"Request {request_id}: Pydantic validation error: {pydantic_exc}", exc_info=True); raise HTTPException(status_code=400, detail=f"Invalid request body: {pydantic_exc}")

    input_data = _extract_input_to_eidos_format(body, request_id, user_id_from_header=x_user_id)
    try:
        logger.info(f"Request {request_id}: Calling _input_router.route_input (User ID: {input_data['metadata']['user_id']}). ForceSearchFlag: {input_data['metadata'].get('force_web_search_requested')}, TTS Enabled for Resp: {input_data['metadata'].get('auto_tts_enabled_for_response')}")
        result: RoutingResult = await _input_router.route_input(input_data) # Use injected _input_router
        logger.info(f"Request {request_id}: _input_router.route_input success: {result.success}"); router_metadata = result.metadata or {}; final_response_content = result.content
        message_metadata_keys = ["mood_at_response", "active_user_id_for_turn", "hexus_scores", "vision_llm_output", "retrieved_memory_ids", "tool_calls_from_pathos", "engaged_proactive_id", "forced_action", "tts_stream_attempted"]
        message_metadata = {k: router_metadata.get(k) for k in message_metadata_keys if router_metadata.get(k) is not None}
        usage_data_keys = ["prompt_tokens_from_llm", "completion_tokens_from_llm", "estimated_prompt_tokens"]
        usage_data_from_router = {k.replace("_from_llm",""): router_metadata.get(k) for k in usage_data_keys if router_metadata.get(k) is not None}
        if 'prompt_tokens' in usage_data_from_router and 'completion_tokens' in usage_data_from_router: usage_data_from_router['total_tokens'] = usage_data_from_router['prompt_tokens'] + usage_data_from_router['completion_tokens']
        usage_data = ChatCompletionUsage(**usage_data_from_router) if any(v is not None for v in usage_data_from_router.values()) else None
        final_tool_calls = message_metadata.get("tool_calls_from_pathos")
        response_message = ChatMessage(role="assistant", content=final_response_content, tool_calls=final_tool_calls, metadata=message_metadata if message_metadata else None)
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "null"] = "tool_calls" if final_tool_calls else "stop"
        choice = ChatCompletionChoice(index=0, message=response_message, finish_reason=finish_reason)
        final_model_name_for_response = (body.get("model", 'eidos-agent').split('#')[0].strip() if body.get("model") else 'eidos-agent')
        api_response = ChatCompletionResponse(id=f"chatcmpl-{request_id}", object="chat.completion", created=int(datetime.now(timezone.utc).timestamp()), model=final_model_name_for_response, choices=[choice], usage=usage_data)
        logger.critical(f"<<< Request {request_id}: chat_completions EXITING (sending full text response) <<<"); return api_response
    except HTTPException as http_exc: logger.error(f"!!! Request {request_id}: HTTPException during routing/response generation: {http_exc.detail}", exc_info=False); raise http_exc
    except Exception as e: logger.error(f"!!! Request {request_id}: Unhandled API exception in chat_completions: {e}", exc_info=True); return HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}") # Return HTTPException
