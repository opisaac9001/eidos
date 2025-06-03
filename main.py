import asyncio
import logging
import sys
import time
import uuid
import httpx
import io
import re
from datetime import datetime, timezone
import json
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional, Literal, Union
import secrets
import uvicorn
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Header, WebSocket, WebSocketDisconnect, Path as FastApiPath
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError, Field # Ensure ValidationError is imported

from eidos_agent.core.config import Config, LLMConfig
from eidos_agent.utils.logger import get_logger, configure_logging

configure_logging()
logger = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

from eidos_agent.services.openweathermap import OpenWeatherMapService
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry # Used in response_model
from eidos_agent.services.home_assistant import HomeAssistantService
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.pathos_interface import PathosInterface
from eidos_agent.modules.oneiros_module import OneirosModule
from eidos_agent.core.input_router import InputRouter, RoutingResult
from eidos_agent.core.api_models import (
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
    ChatCompletionChoice, ChatCompletionUsage, ModelList, ModelCard,
    UserSettingItem, UserSettingsRequest, ClearUserMemoryRequest,
    FeedbackRequest, DreamEntryResponse, MemoryEntry as ApiMemoryEntry # Use ApiMemoryEntry for response_model
)
from eidos_agent.core.connection_manager import ConnectionManager
from eidos_agent.services.external_tts_service import ExternalTTSService
from eidos_agent.modules.chronos_engine import ChronosEngine, PATHOS_USER_ID
from eidos_agent.modules.chronos_models import ActivitySlot, PathosEvent, EventType, PathosEventDetails
from eidos_agent.routers import chat_storage
from eidos_agent.api.main import router as pathos_hooks_router # Import the new router

# --- Global Variables ---
ethos_core: Optional[EthosCore] = None
logos_core: Optional[LogosCore] = None
pathos_interface: Optional[PathosInterface] = None
oneiros_module: Optional[OneirosModule] = None
router: Optional[InputRouter] = None
background_tasks: List[asyncio.Task] = []
manager = ConnectionManager()
eidos_tts_service_instance: Optional[ExternalTTSService] = None

TEMP_AUDIO_CACHE: Dict[str, bytes] = {}
logger.info(f"MAIN.PY GLOBAL: TEMP_AUDIO_CACHE initialized. ID: {id(TEMP_AUDIO_CACHE)}")
TEMP_AUDIO_CACHE_LOCK = asyncio.Lock()
logger.info(f"MAIN.PY GLOBAL: TEMP_AUDIO_CACHE_LOCK initialized. ID: {id(TEMP_AUDIO_CACHE_LOCK)}")

async def warm_vllm_cache(pathos_if: PathosInterface, static_system_prompt: str):
    main_llm_config_for_warmup: Optional[LLMConfig] = pathos_if.pathos_llm_config
    if not main_llm_config_for_warmup or \
       not (main_llm_config_for_warmup.get('url') or main_llm_config_for_warmup.get('base_url')) or \
       not static_system_prompt:
        logger.warning("VLLM Cache Warming: Main Pathos LLM config (URL/BaseURL) or static prompt content missing. Skipping.")
        return
    llm_provider_url = main_llm_config_for_warmup.get('base_url') or main_llm_config_for_warmup.get('url')
    llm_model_name = main_llm_config_for_warmup.get('model') or main_llm_config_for_warmup.get('model_name')
    logger.info(f"Attempting to warm VLLM cache with static prompt for Pathos LLM. Target URL base: {llm_provider_url}, Target Model: {llm_model_name}")
    if not llm_provider_url or not llm_model_name:
        logger.error(f"VLLM Cache Warming: Could not determine API URL ('{llm_provider_url}') or model name ('{llm_model_name}') from Pathos LLM config. Skipping.")
        return
    final_api_url = f"{llm_provider_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = main_llm_config_for_warmup.get('api_key')
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
        headers["Authorization"] = f"Bearer {api_key}"
    warmup_messages = [{"role": "system", "content": static_system_prompt}, {"role": "user", "content": "Hello."}]
    payload = {"model": llm_model_name, "messages": warmup_messages, "max_tokens": 5, "temperature": 0.1, "stream": False}
    logger.debug(f"Warming VLLM cache: POST to {final_api_url} with model {llm_model_name}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(final_api_url, headers=headers, json=payload)
            response.raise_for_status()
        logger.info(f"VLLM cache warming request sent successfully for Pathos model '{llm_model_name}' at {final_api_url}.")
    except Exception as e:
        logger.error(f"Failed to warm VLLM cache for Pathos LLM (URL: {final_api_url}, Model: {llm_model_name}): {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global ethos_core, logos_core, pathos_interface, oneiros_module, router, background_tasks, manager, eidos_tts_service_instance
    ha_service: Optional[HomeAssistantService] = None
    owm_service: Optional[OpenWeatherMapService] = None
    logger.info("--- Initializing Eidos System for API (Lifespan Startup) ---")
    try:
        logger.info("Lifespan: Starting core component initialization...")
        ethos_core = EthosCore(Config)
        chat_storage.init_router(ethos_core)
        ethos_core.set_connection_manager(manager)
        if Config.get_ha_config():
            ha_service = HomeAssistantService(Config, ethos_core.memory_storage)
            try: await ha_service.connect()
            except Exception as ha_e: logger.error(f"Lifespan: Failed to connect HomeAssistantService: {ha_e}", exc_info=True); ha_service = None
        if Config.get_openweathermap_config() and Config.get_openweathermap_config().get('api_key'):
            owm_service = OpenWeatherMapService(Config)
            if not owm_service.is_available: logger.warning("Lifespan: OWMService not available.")
        if Config.ENABLE_ONEIROS and ethos_core:
            oneiros_module = OneirosModule(Config, ethos_core)
            if ethos_core: ethos_core.oneiros_module = oneiros_module
        logos_core = LogosCore(Config, ethos_core, ha_service, owm_service)
        await logos_core.initialize_services()
        if ethos_core: ethos_core.set_logos_core(logos_core)
        chronos_engine_instance: Optional[ChronosEngine] = None
        if ethos_core and logos_core and ethos_core.memory_storage:
            chronos_engine_instance = ChronosEngine(Config, ethos_core.memory_storage, ethos_core, logos_core)
            if ethos_core: ethos_core.set_chronos_engine(chronos_engine_instance)
            logger.info("Lifespan: ChronosEngine initialized and set in EthosCore.")
        else:
            logger.warning("Lifespan: ChronosEngine NOT initialized due to missing EthosCore, LogosCore, or MemoryStorage.")
        pathos_interface = PathosInterface(Config, ethos_core, logos_core, manager)
        pathos_interface.set_audio_cache(TEMP_AUDIO_CACHE, TEMP_AUDIO_CACHE_LOCK)
        if ethos_core: ethos_core.set_pathos_interface(pathos_interface)
        if ethos_core and logos_core and pathos_interface:
            router = InputRouter(config=Config, ethos_core=ethos_core, logos_core=logos_core, pathos_interface=pathos_interface)
        else:
            raise RuntimeError("Failed to initialize InputRouter due to missing core components.")
        if Config.EIDOS_TTS and isinstance(Config.EIDOS_TTS, dict) and Config.EIDOS_TTS.get('api_url'):
            try:
                eidos_tts_service_instance = ExternalTTSService(config=Config)
                if eidos_tts_service_instance.is_available():
                    if pathos_interface: pathos_interface.set_tts_service(eidos_tts_service_instance)
                else: eidos_tts_service_instance = None
            except Exception as e_tts_init: logger.error(f"Lifespan: Failed to initialize ExternalTTSService: {e_tts_init}", exc_info=True); eidos_tts_service_instance = None
        else: eidos_tts_service_instance = None
        await check_critical_llm_availability()
        if pathos_interface and pathos_interface.pathos_llm_config and (pathos_interface.pathos_llm_config.get("url") or pathos_interface.pathos_llm_config.get("base_url")):
            static_prompt_for_vllm = pathos_interface.get_static_system_prompt_content()
            if static_prompt_for_vllm: await warm_vllm_cache(pathos_interface, static_prompt_for_vllm)
        if ethos_core: background_tasks = await ethos_core.get_background_tasks()
        logger.info("--- Eidos System Initialized Successfully ---")
        yield
        logger.info("--- Shutting Down Eidos System ---")
        active_bg_tasks = [task for task in background_tasks if not task.done()]
        if active_bg_tasks:
            for task in active_bg_tasks: task.cancel()
            try: await asyncio.wait(active_bg_tasks, timeout=5.0)
            except asyncio.TimeoutError: logger.warning("Timeout waiting for background tasks to cancel.")
        if manager: await manager.disconnect_all()
        if pathos_interface: await pathos_interface.close()
        if logos_core: await logos_core.close()
        if ha_service: await ha_service.disconnect()
        if owm_service and hasattr(owm_service, 'close'): await owm_service.close() # type: ignore
        if oneiros_module: await oneiros_module.close()
        if ethos_core: await ethos_core.close()
        if eidos_tts_service_instance: await eidos_tts_service_instance.close()
        TEMP_AUDIO_CACHE.clear()
        logger.info("--- Eidos System Shutdown Complete ---")
    except Exception as e_lifespan_main:
        logger.critical(f"--- System Initialization Failed Critically in Lifespan ---: {str(e_lifespan_main)}", exc_info=True)
        if 'pathos_interface' in locals() and pathos_interface and hasattr(pathos_interface, 'close'): await pathos_interface.close()
        if 'logos_core' in locals() and logos_core and hasattr(logos_core, 'close'): await logos_core.close()
        raise RuntimeError("Eidos system failed to initialize during lifespan startup.") from e_lifespan_main

app = FastAPI(title="Eidos Agent API", version="1.0", lifespan=lifespan)
app.include_router(chat_storage.router, prefix="/v1")
app.include_router(pathos_hooks_router) # Include the Pathos hooks router

if WEBAPP_DIR.is_dir():
    js_dir = WEBAPP_DIR / "js"; css_dir = WEBAPP_DIR / "css"
    if js_dir.is_dir(): app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if css_dir.is_dir(): app.mount("/css", StaticFiles(directory=css_dir), name="css")
if Config.ENABLE_ONEIROS and Config.ONEIROS and Config.ONEIROS.get('enable_image_dreams') and Config.IMAGE_OUTPUT_DIR:
    try:
        image_output_path_static = Path(Config.IMAGE_OUTPUT_DIR)
        if not image_output_path_static.is_absolute(): image_output_path_static = BASE_DIR / Config.IMAGE_OUTPUT_DIR
        image_output_path_static.mkdir(parents=True, exist_ok=True)
        if image_output_path_static.is_dir():
            app.mount("/dream_images", StaticFiles(directory=str(image_output_path_static.resolve())), name="dream_images")
    except Exception as e_mount_static: logger.error(f"Error mounting dream image directory: {e_mount_static}", exc_info=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*", "X-User-Id", "X-Admin-Password"])

async def check_llm_role_availability(role_name: str, llm_config: Optional[Dict[str, Any]]):
    if not llm_config or not llm_config.get('url') or not llm_config.get('model'): return True
    api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"; model_name = llm_config['model']
    headers = {"Content-Type": "application/json"}; api_key = llm_config.get('api_key')
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model_name, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 5, "temperature": 0.1}
    try:
        timeout_val = float(llm_config.get('timeout', 15))
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            response = await client.post(api_url, headers=headers, json=payload)
            if response.status_code == 200: logger.info(f"LLM Check: SUCCESS - Role '{role_name}' (Model: {model_name}) is responding."); return True
            logger.error(f"LLM Check: FAILED - Role '{role_name}' (Model: {model_name}) returned {response.status_code}. Resp: {response.text[:200]}"); return False
    except httpx.ConnectError: logger.error(f"LLM Check: FAILED - Connection refused for role '{role_name}' (Model: {model_name})."); return False
    except Exception as e: logger.error(f"LLM Check: FAILED - Error checking role '{role_name}' (Model: {model_name}): {e}", exc_info=True); return False

async def check_critical_llm_availability():
    all_critical_llms_ok = True
    critical_roles_map = {
        "PATHOS": Config.LLM.get('PATHOS'),
        "LOGOS_TECHNE (Summarization/Reflection/Upkeep)": Config.get_llm_config(Config.ETHOS.get('summarization_llm_role', 'LOGOS_TECHNE')),
        "ONEIROS_DREAM_LLM": Config.get_llm_config(Config.ONEIROS.get('dream_llm_role', 'PATHOS')) if Config.ONEIROS else None
    }
    if Config.ENABLE_KNOWLEDGE_UPKEEP:
        critical_roles_map["KNOWLEDGE_UPKEEP_LLM"] = Config.get_llm_config(Config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE'))
    for role_description, llm_config_to_check in critical_roles_map.items():
        if llm_config_to_check:
            if not await check_llm_role_availability(role_description, llm_config_to_check):
                all_critical_llms_ok = False
    if not all_critical_llms_ok:
        logger.critical("!!! WARNING: One or more critical LLMs are not available or not configured. !!!")

def extract_input_to_eidos_format(body: dict, request_id: str, user_id_from_header: Optional[str]) -> dict:
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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Pydantic Validation Error: {exc.errors()}")
    return PlainTextResponse(str(exc.errors()), status_code=422)

# --- API Endpoints ---

@app.get("/", include_in_schema=False)
async def get_gui_root():
    gui_html_path = WEBAPP_DIR / "gui.html"
    if gui_html_path.is_file(): return FileResponse(str(gui_html_path))
    else: logger.error(f"GUI HTML file not found at {gui_html_path}"); return JSONResponse(content={"error": "Eidos GUI not found."}, status_code=404)

@app.get("/v1/models", response_model=ModelList)
async def list_models_endpoint():
    logger.info("Request received for /v1/models")
    model_id = Config.LLM['PATHOS']['model'] if Config.LLM and Config.LLM.get('PATHOS') and Config.LLM['PATHOS'].get('model') else 'eidos-agent'
    model_id = model_id.split('#')[0].strip() if model_id else 'eidos-agent'
    eidos_model_card = ModelCard(id=model_id, owned_by="eidos-project")
    logger.info(f"Reporting model ID: {model_id}")
    return ModelList(data=[eidos_model_card])

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(fastapi_request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global router, ethos_core, logos_core, pathos_interface, manager
    if not all([router, ethos_core, logos_core, pathos_interface, manager]): raise HTTPException(status_code=503, detail="Eidos system core components not fully ready.")
    request_id = str(uuid.uuid4()); logger.critical(f">>> Request {request_id}: chat_completions ENTERED <<<"); logger.info(f"Request {request_id}: X-User-Id Header: '{x_user_id}'")
    try: body = await fastapi_request.json()
    except json.JSONDecodeError: logger.error(f"Request {request_id}: Invalid JSON body."); raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        parsed_request = ChatCompletionRequest(**body)
        if parsed_request.stream:
            logger.warning(f"Request {request_id}: Client requested streaming (stream=true), but this endpoint returns full text. TTS audio is streamed via WebSocket if enabled.")
        logger.info(f"Request {request_id}: Validated request. Model='{parsed_request.model}', Messages={len(parsed_request.messages)}")
    except ValidationError as pydantic_exc: logger.error(f"Request {request_id}: Pydantic validation error: {pydantic_exc}", exc_info=True); raise HTTPException(status_code=400, detail=f"Invalid request body: {pydantic_exc}")

    input_data = extract_input_to_eidos_format(body, request_id, user_id_from_header=x_user_id)
    try:
        logger.info(f"Request {request_id}: Calling router.route_input (User ID: {input_data['metadata']['user_id']}). ForceSearchFlag: {input_data['metadata'].get('force_web_search_requested')}, TTS Enabled for Resp: {input_data['metadata'].get('auto_tts_enabled_for_response')}")
        result: RoutingResult = await router.route_input(input_data)
        logger.info(f"Request {request_id}: router.route_input success: {result.success}"); router_metadata = result.metadata or {}; final_response_content = result.content
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
    except Exception as e: logger.error(f"!!! Request {request_id}: Unhandled API exception in chat_completions: {e}", exc_info=True); return JSONResponse(status_code=500, content={"error": {"message": f"Internal Server Error: {str(e)}", "type": "internal_error", "code": "internal_server_error"}})

@app.get("/v1/tts/audio_chunk/{chunk_id}")
async def get_tts_audio_chunk(chunk_id: str):
    global TEMP_AUDIO_CACHE
    logger.debug(f"GET_CHUNK_DEBUG: Request for chunk ID: {chunk_id}. ID of global TEMP_AUDIO_CACHE: {id(TEMP_AUDIO_CACHE)}. Cache size: {len(TEMP_AUDIO_CACHE)}")
    if chunk_id in TEMP_AUDIO_CACHE: logger.debug(f"GET_CHUNK_DEBUG: Chunk {chunk_id} FOUND in cache before pop.")
    else: logger.warning(f"GET_CHUNK_DEBUG: Chunk {chunk_id} NOT FOUND in cache before pop. Current keys: {list(TEMP_AUDIO_CACHE.keys())}")
    audio_bytes = TEMP_AUDIO_CACHE.pop(chunk_id, None)
    if audio_bytes:
        logger.info(f"Serving TTS audio chunk ID: {chunk_id}, Length: {len(audio_bytes)} bytes.")
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
    else:
        logger.warning(f"TTS audio chunk ID: {chunk_id} not found in cache or already served.")
        raise HTTPException(status_code=404, detail="Audio chunk not found or already served.")

@app.get("/v1/weather", status_code=200)
async def get_weather_endpoint(location: str, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global logos_core
    if not logos_core: logger.error(f"Weather request but LogosCore not init. User: {x_user_id or 'unknown'}"); raise HTTPException(status_code=503, detail="Eidos system not ready.")
    if not location or not location.strip(): logger.warning(f"Weather request no location. User: {x_user_id or 'unknown'}"); raise HTTPException(status_code=400, detail="'location' required.")
    logger.info(f"Weather request for '{location}'. User: {x_user_id or 'unknown'}")
    try:
        weather_result = await logos_core.execute_get_weather(location, user_id_context=x_user_id)
        if isinstance(weather_result, dict) and weather_result.get("success"):
             if weather_data := weather_result.get('weather_data'): return JSONResponse(content={"success": True, "location": location, "weather_data": weather_data})
             else: logger.error(f"LogosCore success but no weather_data for '{location}': {weather_result}"); raise HTTPException(status_code=500, detail="Weather data missing.")
        elif isinstance(weather_result, dict) and weather_result.get("error"):
            logger.error(f"LogosCore weather error for '{location}': {weather_result}"); error_detail = weather_result.get("error", "Internal weather service error"); service_msg = weather_result.get("message", "")
            raise HTTPException(status_code=500, detail=error_detail, headers={"X-Weather-Service-Message": service_msg})
        else: logger.error(f"LogosCore weather unexpected format for '{location}': {weather_result}"); raise HTTPException(status_code=500, detail="Weather service unexpected format.")
    except HTTPException as http_exc: raise http_exc
    except Exception as e: logger.error(f"Unexpected error in /v1/weather for '{location}': {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error.")

@app.post("/v1/user/settings", status_code=200)
async def update_user_settings(settings_request: UserSettingsRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")):
    global logos_core, ethos_core
    request_id = str(uuid.uuid4())
    raw_user_id_from_payload = settings_request.user_id; raw_user_id_from_header = x_user_id_header
    effective_raw_user_id: Optional[str] = raw_user_id_from_payload
    if not effective_raw_user_id and raw_user_id_from_header: effective_raw_user_id = raw_user_id_from_header
    if not effective_raw_user_id: effective_raw_user_id = "api_guest_user"
    user_id_for_storage: str = "api_guest_user"
    if effective_raw_user_id and isinstance(effective_raw_user_id, str):
        normalized = effective_raw_user_id.lower().strip().replace(" ", "_")
        if normalized: user_id_for_storage = normalized
    logger.info(f"Request {request_id}: /v1/user/settings for user (normalized for storage) '{user_id_for_storage}'. Raw payload ID: '{raw_user_id_from_payload}', Header ID: '{raw_user_id_from_header}'.")
    if not ethos_core or not logos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    results = []; all_ok = True
    for item in settings_request.settings:
        try:
            fact_result_str = await logos_core.execute_store_user_fact(attribute_name=item.attribute_name, attribute_value=str(item.attribute_value), user_statement_context=item.user_statement_context or f"User set {item.attribute_name} via GUI settings.", user_id=user_id_for_storage)
            fact_res = json.loads(fact_result_str)
            if fact_res.get("status") == "success": results.append({"attribute_name": item.attribute_name, "status": "success", "message": fact_res.get("message")})
            else: all_ok = False; results.append({"attribute_name": item.attribute_name, "status": "failed", "message": fact_res.get("error")}); logger.warning(f"Failed to store setting '{item.attribute_name}' for user '{user_id_for_storage}': {fact_res.get('error')}")
        except Exception as e: all_ok = False; error_msg = f"Error processing setting '{item.attribute_name}': {str(e)}"; logger.error(f"Request {request_id}: {error_msg}", exc_info=True); results.append({"attribute_name": item.attribute_name, "status": "error", "message": error_msg})
    if all_ok: return {"status": "success", "message": "All settings processed.", "details": results}
    else: return {"status": "partial_success", "message": "Some settings failed.", "details": results}

@app.get("/v1/briefing", status_code=200)
async def get_daily_briefing_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global logos_core, ethos_core
    if not ethos_core or not logos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    user_id = x_user_id or "unknown_user"; logger.info(f"Request for /v1/briefing for user '{user_id}'.")
    try:
        briefing_result = await logos_core.get_or_generate_daily_briefing(user_id_context=user_id)
        if briefing_result.get("success"): return JSONResponse(content=briefing_result)
        else: logger.warning(f"Briefing for '{user_id}' not fully successful: {briefing_result.get('message')}"); return JSONResponse(content=briefing_result)
    except HTTPException as http_exc: raise http_exc
    except Exception as e: logger.error(f"Unexpected error in /v1/briefing for '{user_id}': {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error processing briefing.")

class TTSRequestAPI(BaseModel): # Renamed to avoid conflict with other TTSRequest
    text: str
    gender: Optional[str] = None
    pitch: Optional[str] = None
    speed: Optional[str] = None

@app.post("/v1/tts/synthesize", tags=["TTS"])
async def synthesize_speech_api(request_data: TTSRequestAPI):
    global eidos_tts_service_instance
    if not eidos_tts_service_instance or not eidos_tts_service_instance.is_available():
        raise HTTPException(status_code=503, detail="TTS service is not available or not configured.")
    # Validation for gender, pitch, speed can be added here if needed, similar to the old endpoint
    logger.info(f"Eidos TTS API: Synthesis request for text: '{request_data.text[:50]}...' G:{request_data.gender} P:{request_data.pitch} S:{request_data.speed}")
    try:
        speed_val = None
        if request_data.speed:
            try: speed_val = float(request_data.speed) # Assuming ExternalTTSService expects float
            except ValueError: raise HTTPException(status_code=422, detail="Invalid speed value, must be a number.")
        
        audio_bytes = await eidos_tts_service_instance.synthesize(
            text=request_data.text,
            speed_override=speed_val
            # gender_override and pitch_override would be passed if ExternalTTSService supports them
        )
        if audio_bytes:
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav") # Assuming WAV for now
        else:
            raise HTTPException(status_code=500, detail="TTS synthesis failed to produce audio (external service).")
    except Exception as e:
        logger.error(f"Error during Eidos TTS API call to external service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {str(e)}")

@app.post("/v1/feedback", status_code=202)
async def receive_feedback(feedback_data: FeedbackRequest, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global pathos_interface, ethos_core; request_id = str(uuid.uuid4())
    logger.info(f"Request {request_id}: /v1/feedback. User from header: '{x_user_id}'")
    if not pathos_interface or not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready for feedback.")
    feedback_dict = feedback_data.model_dump(exclude_unset=True)
    if x_user_id: feedback_dict['user_id'] = x_user_id
    elif 'user_id' not in feedback_dict or not feedback_dict['user_id']: feedback_dict['user_id'] = 'api_guest_user'
    logger.info(f"Request {request_id}: Feedback for user '{feedback_dict.get('user_id')}': {str(feedback_dict)[:500]}...")
    try:
        await pathos_interface.process_feedback(feedback_dict)
        logger.info(f"Request {request_id}: Feedback for '{feedback_dict.get('user_id')}' passed to PathosInterface.")
        return {"message": "Feedback received and queued.", "feedback_log_id": request_id}
    except Exception as e: logger.error(f"Request {request_id}: Error processing feedback: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Internal server error processing feedback: {str(e)}")

@app.get("/health")
async def health_check():
    global ethos_core, logos_core, pathos_interface, router, manager
    core_ok = all([ethos_core, logos_core, pathos_interface, router, manager])
    mem_ok = ethos_core.memory_storage._conn is not None if ethos_core and hasattr(ethos_core, 'memory_storage') and hasattr(ethos_core.memory_storage, '_conn') else False
    logos_http_ok = logos_core.http_client is not None and not logos_core.http_client.is_closed if logos_core and hasattr(logos_core, 'http_client') else False
    pathos_http_ok = pathos_interface.http_client is not None and not pathos_interface.http_client.is_closed if pathos_interface and hasattr(pathos_interface, 'http_client') else False
    status = "ok" if core_ok and mem_ok and logos_http_ok and pathos_http_ok else "error"
    msg = "Eidos healthy." if status == "ok" else "Eidos core components or dependencies unhealthy."
    if status == "error": logger.error(f"Health check failed. Core: {core_ok}, Mem: {mem_ok}, LogosHTTP: {logos_http_ok}, PathosHTTP: {pathos_http_ok}, Mgr: {manager is not None}")
    return JSONResponse(content={"status": status, "message": msg})

@app.post("/v1/documents/upload", status_code=200)
async def upload_document(file: UploadFile = File(..., description="Document (PDF, DOCX, TXT)"), x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global logos_core
    if not logos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    logger.info(f"Doc upload: '{file.filename}' ({file.content_type}, {getattr(file, 'size', 'unknown')} bytes) for user '{x_user_id or 'unknown_user'}'.")
    try: file_content = await file.read()
    except Exception as e: logger.error(f"Error reading uploaded file '{file.filename}': {e}", exc_info=True); raise HTTPException(status_code=422, detail=f"Error reading file: {e}")
    finally:
        if hasattr(file, 'file') and hasattr(file.file, 'close') and callable(file.file.close): file.file.close()
    if not file_content: raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        result = await logos_core.process_uploaded_document(file_content, file.filename, user_id=x_user_id)
        if result.get("success"): return JSONResponse(content={"success": True, "message": "Document processed.", "extracted_text": result.get("extracted_text")})
        raise HTTPException(status_code=500, detail=result.get("message", "Doc processing failed."))
    except HTTPException as http_exc: raise http_exc
    except Exception as e: logger.error(f"Unexpected error processing doc '{file.filename}': {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error during document processing.")

@app.post("/v1/memory/clear", status_code=200)
async def clear_eidos_memory(x_user_id: Optional[str] = Header(None, alias="X-User-Id"), x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    admin_pw_cfg = Config.get_admin_password()
    if admin_pw_cfg:
        if not x_admin_password: logger.warning(f"Clear all memory attempt by '{x_user_id or 'unknown'}' no admin pw."); raise HTTPException(status_code=401, detail="Unauthorized: Admin password required.")
        if not secrets.compare_digest(x_admin_password, admin_pw_cfg): logger.warning(f"Clear all memory attempt by '{x_user_id or 'unknown'}' incorrect admin pw."); raise HTTPException(status_code=403, detail="Forbidden: Incorrect admin password.")
    else: logger.warning("Executing clear all Eidos memory without password protection (EIDOS_ADMIN_PASSWORD not set).")
    logger.warning(f"API request to clear all Eidos memory from '{x_user_id or 'unknown'}' (Authenticated).")
    try:
        if ethos_core.memory_storage.clear_all_memory():
             if ethos_core and x_user_id: await ethos_core.add_memory_entry({"type": "system", "content": f"User '{x_user_id}' initiated full memory clear.", "metadata": {"user_id": x_user_id, "action": "memory_clear", "timestamp": datetime.now(timezone.utc).isoformat()}}, user_id_context="system_admin")
             return JSONResponse(content={"message": "Eidos memory cleared."})
        raise HTTPException(status_code=500, detail="Failed to clear memory.")
    except Exception as e: logger.error(f"Error during clear_all_memory(): {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error during memory clearing.")

@app.post("/v1/memory/clear_user", status_code=200)
async def clear_user_memory(request_data: ClearUserMemoryRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    user_to_clear = request_data.user_id; requesting_user = x_user_id_header or "unknown_api_caller"
    logger.warning(f"API request to clear memory for user '{user_to_clear}' from '{requesting_user}'.")
    if not user_to_clear: raise HTTPException(status_code=400, detail="user_id must be provided.")
    try:
        success = await ethos_core.clear_memory_for_user(user_to_clear)
        if success:
            await ethos_core.add_memory_entry({"type": "system", "content": f"Memory for user '{user_to_clear}' cleared by '{requesting_user}'.", "metadata": {"user_id": "system_admin", "action": "user_memory_clear", "target_user_id": user_to_clear, "requesting_user": requesting_user, "timestamp": datetime.now(timezone.utc).isoformat()}}, user_id_context="system_admin")
            return JSONResponse(content={"message": f"Memory for user '{user_to_clear}' cleared."})
        else: raise HTTPException(status_code=500, detail=f"Failed to clear memory for user '{user_to_clear}'.")
    except Exception as e: logger.error(f"Error during clear_memory_for_user (user: '{user_to_clear}'): {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.delete("/v1/memory/entry/{memory_id}", status_code=200, tags=["Memory Management"])
async def delete_memory_entry_endpoint(
    memory_id: str = FastApiPath(..., title="The ID of the memory entry to delete", min_length=36, max_length=36),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")
):
    global ethos_core
    if not ethos_core:
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")
    requesting_user_raw: Optional[str] = x_user_id
    requesting_user_normalized: str = "unknown_api_caller"
    if requesting_user_raw and isinstance(requesting_user_raw, str):
        normalized = requesting_user_raw.lower().strip().replace(" ", "_")
        if normalized: requesting_user_normalized = normalized
    logger.info(f"API: Request to delete memory entry ID '{memory_id}'. Requesting user (normalized): '{requesting_user_normalized}' (Raw X-User-Id: '{requesting_user_raw}').")
    entry_to_delete = ethos_core.memory_storage.get_entry(memory_id)
    if not entry_to_delete:
        raise HTTPException(status_code=404, detail=f"Memory entry with ID '{memory_id}' not found.")
    entry_owner_id = entry_to_delete.get('metadata', {}).get('user_id')
    is_admin_attempt = False; admin_pw_cfg = Config.get_admin_password()
    if admin_pw_cfg and x_admin_password:
        if secrets.compare_digest(x_admin_password, admin_pw_cfg):
            is_admin_attempt = True; logger.info(f"Admin authenticated for deleting memory entry '{memory_id}'.")
        else: logger.warning(f"Admin password provided but incorrect for deleting memory entry '{memory_id}'.")
    can_delete = False
    if is_admin_attempt: can_delete = True
    elif entry_owner_id == requesting_user_normalized and entry_to_delete.get('type') == 'user_fact': can_delete = True
    elif entry_to_delete.get('type') != 'user_fact': logger.warning(f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) attempted to delete non-user_fact entry '{memory_id}' without admin rights.")
    else: logger.warning(f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) does not own user_fact '{memory_id}' (owner: '{entry_owner_id}').")
    if not can_delete: raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to delete this memory entry.")
    try:
        if ethos_core.memory_storage.delete_entry(memory_id):
            logger.info(f"Successfully deleted memory entry '{memory_id}'.")
            await ethos_core.add_memory_entry({
                "type": "system",
                "content": f"Memory entry '{memory_id}' (type: {entry_to_delete.get('type')}, owner: {entry_owner_id or 'N/A'}) deleted by '{requesting_user_normalized}' (Admin: {is_admin_attempt}). Raw request user: '{requesting_user_raw}'.",
                "metadata": {"user_id": "system_admin", "action": "memory_entry_delete", "deleted_entry_id": memory_id, "deleted_entry_type": entry_to_delete.get('type'), "deleted_entry_owner": entry_owner_id, "requesting_user_normalized": requesting_user_normalized, "requesting_user_raw": requesting_user_raw, "is_admin_action": is_admin_attempt, "timestamp": datetime.now(timezone.utc).isoformat()}
            }, user_id_context="system_admin")
            return JSONResponse(content={"message": f"Memory entry '{memory_id}' deleted successfully."})
        else: raise HTTPException(status_code=500, detail=f"Failed to delete memory entry '{memory_id}', or it was already deleted.")
    except Exception as e: logger.error(f"Error during deletion of memory entry '{memory_id}': {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Internal server error during memory deletion: {str(e)}")

@app.get("/v1/user/facts", response_model=List[ApiMemoryEntry], tags=["User Profile"]) # Use ApiMemoryEntry
async def get_user_facts_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: logger.error("/v1/user/facts: EthosCore not available."); raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")
    raw_actual_user_id = x_user_id or "unknown_user"
    actual_user_id = raw_actual_user_id.lower().strip().replace(" ", "_") if raw_actual_user_id else "unknown_user"
    if not actual_user_id: actual_user_id = "unknown_user"
    if actual_user_id in ["unknown_user", "api_guest_user", "default_user"]:
        logger.info(f"Request for user facts from a generic user context ('{actual_user_id}'). Returning empty list.")
        return []
    logger.info(f"API: Request for user facts for user_id (normalized): '{actual_user_id}' (Raw was: '{raw_actual_user_id}').")
    try:
        user_facts_raw: List[MemoryEntry] = await ethos_core.get_all_user_facts(user_id=actual_user_id)
        validated_facts: List[ApiMemoryEntry] = []
        for fact_data in user_facts_raw:
            try:
                if isinstance(fact_data, dict): validated_facts.append(ApiMemoryEntry(**fact_data))
                elif hasattr(fact_data, 'model_dump'): validated_facts.append(ApiMemoryEntry(**fact_data.model_dump()))
                else: logger.warning(f"Skipping non-dict fact data for user '{actual_user_id}': {type(fact_data)}")
            except ValidationError as ve: logger.error(f"Validation error for a user fact (user: {actual_user_id}): {ve.errors()}. Data: {fact_data}")
        logger.info(f"Returning {len(validated_facts)} facts for user '{actual_user_id}'.")
        return JSONResponse(content=jsonable_encoder(validated_facts))
    except HTTPException as http_exc: raise http_exc
    except Exception as e: logger.error(f"API: Error fetching user facts for '{actual_user_id}': {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error fetching user facts.")

@app.get("/v1/agent/dreams", response_model=List[DreamEntryResponse], tags=["Agent State"])
async def get_agent_dreams(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")
    logger.info(f"API: Request for /v1/agent/dreams. User: {x_user_id}, Limit: {limit}")
    try:
        raw_dreams = await ethos_core.get_recent_dreams(user_id_context=x_user_id, limit=limit)
        response_dreams: List[DreamEntryResponse] = []
        for entry in raw_dreams:
            img_url = None; metadata = entry.get('metadata', {})
            if local_img_path_str := metadata.get('dream_image_path'):
                try: img_filename = Path(local_img_path_str).name; img_url = f"/dream_images/{img_filename}"
                except Exception as e_path: logger.error(f"Error constructing image URL from dream_image_path '{local_img_path_str}': {e_path}")
            response_dreams.append(DreamEntryResponse(id=entry.get('id', str(uuid.uuid4())), timestamp=entry.get('timestamp', datetime.now(timezone.utc).isoformat()), content=entry.get('content', '[No dream content]'), dream_image_url=img_url, dream_seed_summary=metadata.get('dream_seed_summary')))
        return response_dreams
    except Exception as e: logger.error(f"API: Error fetching agent dreams: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error fetching agent dreams.")

@app.get("/v1/agent/learnings", response_model=List[ApiMemoryEntry], tags=["Agent State"]) # Use ApiMemoryEntry
async def get_agent_learnings(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    user_id_filter = x_user_id; logger.info(f"Request for /v1/agent/learnings. User: {user_id_filter}, Limit: {limit}")
    try:
        learning_types = ["learned_correction", "learned_feedback_insight", "suggestion_reflection"]
        learnings_raw = await ethos_core.get_recent_learnings(learning_types=learning_types, user_id_context=user_id_filter, limit=limit)
        validated_learnings: List[ApiMemoryEntry] = []
        for entry_data in learnings_raw:
            try:
                if isinstance(entry_data, dict): validated_learnings.append(ApiMemoryEntry(**entry_data))
                elif hasattr(entry_data, 'model_dump'): validated_learnings.append(ApiMemoryEntry(**entry_data.model_dump()))
            except ValidationError as e: logger.error(f"MemoryEntry validation failed for learning: {e.json(indent=2)}\nEntry data:\n{entry_data}")
        return JSONResponse(content=jsonable_encoder(validated_learnings))
    except Exception as e: logger.error(f"Error fetching agent learnings: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error fetching agent learnings.")

@app.get("/v1/agent/knowledge_verifications", response_model=List[ApiMemoryEntry], tags=["Agent State"]) # Use ApiMemoryEntry
async def get_agent_knowledge_verifications(limit: int = 20, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    logger.info(f"Request for /v1/agent/knowledge_verifications. User: {x_user_id}, Limit: {limit}")
    try:
        if limit <= 0: limit = 20
        verifications_raw = await ethos_core.get_recent_knowledge_verifications(limit=limit)
        validated_verifications: List[ApiMemoryEntry] = []
        for entry_data in verifications_raw:
            try:
                if isinstance(entry_data, dict): validated_verifications.append(ApiMemoryEntry(**entry_data))
                elif hasattr(entry_data, 'model_dump'): validated_verifications.append(ApiMemoryEntry(**entry_data.model_dump()))
            except ValidationError as e: logger.error(f"MemoryEntry validation for knowledge verification: {e.json(indent=2)}\nData:\n{entry_data}")
        return JSONResponse(content=jsonable_encoder(validated_verifications))
    except Exception as e: logger.error(f"Error fetching agent knowledge verifications: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error fetching agent knowledge verifications.")

@app.get("/v1/pathos/schedule/today", response_model=List[ActivitySlot], tags=["Pathos Chronos"])
async def get_pathos_todays_schedule():
    global ethos_core
    if not ethos_core or not ethos_core.chronos_engine: raise HTTPException(status_code=503, detail="Schedule system not ready.")
    try: return await ethos_core.chronos_engine.get_todays_schedule_for_user()
    except Exception as e: logger.error(f"Error retrieving schedule: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.get("/v1/pathos/events/upcoming", response_model=List[PathosEvent], tags=["Pathos Chronos"])
async def get_pathos_upcoming_events(days_ahead: int = 7):
    global ethos_core
    if not ethos_core or not ethos_core.chronos_engine: raise HTTPException(status_code=503, detail="Event system not ready.")
    if not (1 <= days_ahead <= 90): raise HTTPException(status_code=400, detail="days_ahead must be 1-90.")
    try: return await ethos_core.chronos_engine.get_upcoming_events(days_ahead=days_ahead)
    except Exception as e: logger.error(f"Error retrieving upcoming events: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Error: {e}")

class AddPathosEventRequestAPI(BaseModel):
    title: str; start_date: str; end_date: str; event_type: EventType
    description: Optional[str] = None; location: Optional[str] = None
    details: Optional[PathosEventDetails] = None
@app.post("/v1/pathos/events/add", response_model=PathosEvent, status_code=201, tags=["Pathos Chronos"])
async def add_pathos_planned_event_api(event_request: AddPathosEventRequestAPI, x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")):
    global ethos_core
    admin_pw_cfg = Config.get_admin_password()
    if admin_pw_cfg and (not x_admin_password or not secrets.compare_digest(x_admin_password, admin_pw_cfg)): raise HTTPException(status_code=403, detail="Forbidden: Admin credentials required.")
    if not ethos_core or not ethos_core.chronos_engine: raise HTTPException(status_code=503, detail="Event system not ready.")
    try:
        event_data_for_storage = event_request.model_dump(exclude_unset=True); event_data_for_storage['user_id'] = PATHOS_USER_ID
        added_event = await ethos_core.chronos_engine.add_planned_event(event_data_for_storage)
        if added_event: return added_event
        else: raise HTTPException(status_code=500, detail="Failed to add event.")
    except ValueError as ve: raise HTTPException(status_code=422, detail=f"Invalid event data: {ve}")
    except Exception as e: logger.error(f"Error adding event: {e}", exc_info=True); raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = None; connection_ok = False
    try:
        while True:
            data = await websocket.receive_json(); logger.debug(f"WS received: {data}")
            if data.get("type") == "auth" and data.get("payload", {}).get("userId"):
                raw_temp_uid = data["payload"]["userId"]
                temp_uid = raw_temp_uid.lower().strip().replace(" ", "_") if isinstance(raw_temp_uid, str) and raw_temp_uid else None
                if not temp_uid: logger.warning(f"WS: Invalid user_id '{raw_temp_uid}'. Closing."); break
                user_id = temp_uid
                if await manager.connect(websocket, user_id):
                    connection_ok = True; logger.info(f"WS connected for user: {user_id}")
                    await manager.send_personal_message({"type": "status", "payload": {"message": "Connected to Eidos WS."}}, user_id)
                else: logger.error(f"WS: ConnectionManager failed for user {user_id}. Closing."); await websocket.send_json({"type": "error", "payload": {"message": "Failed to register."}}); await websocket.close(code=1011); break
            elif user_id is None: logger.warning("WS: Message before auth. Closing."); await websocket.send_json({"type": "error", "payload": {"message": "Auth required."}}); await websocket.close(code=1008); break
            else: logger.warning(f"WS: Unhandled message type '{data.get('type')}' from user {user_id}.")
    except WebSocketDisconnect: logger.info(f"WS: Disconnected user: {user_id if user_id else 'unauthenticated'}.")
    except Exception as e:
        logger.error(f"WS: Error for user {user_id if user_id else 'unknown'}: {e}", exc_info=True)
        try:
            if websocket.client_state == websocket.client_state.CONNECTED: await websocket.send_json({"type": "error", "payload": {"message": f"Error: {str(e)}"}})
        except Exception as e_send: logger.error(f"WS: Could not send error to user {user_id if user_id else 'unknown'}: {e_send}")
        try:
            if websocket.client_state != websocket.client_state.DISCONNECTED: await websocket.close(code=1011)
        except Exception as e_close: logger.error(f"WS: Error during forced close for user {user_id if user_id else 'unknown'}: {e_close}")
    finally:
        if user_id and connection_ok: manager.disconnect(websocket, user_id); logger.info(f"WS: Ensured user {user_id} disconnected from ConnectionManager.")
        elif user_id: logger.info(f"WS: User {user_id} (not fully registered) closing.")
        else: logger.info("WS: Unauthenticated client closing.")

if __name__ == "__main__":
    uvicorn.run("main:app", host=Config.API.get('host','0.0.0.0'), port=Config.API.get('port',8088), log_level=Config.API.get('log_level','info'), reload=False)