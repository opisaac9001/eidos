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
# Updated import to use eidos_agent.schemas
from eidos_agent.schemas import (
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
    ChatCompletionChoice, ChatCompletionUsage, ModelList, ModelCard,
    UserSettingItem, UserSettingsRequest, ClearUserMemoryRequest,
    FeedbackRequest, DreamEntryResponse, MemoryEntry as ApiMemoryEntry # Use ApiMemoryEntry for response_model
)
from eidos_agent.core.connection_manager import ConnectionManager
from eidos_agent.services.external_tts_service import ExternalTTSService
from eidos_agent.modules.chronos_engine import ChronosEngine, PATHOS_USER_ID
from eidos_agent.modules.chronos_models import ActivitySlot, PathosEvent, EventType, PathosEventDetails
# Updated import for chat_storage_router
from eidos_agent.api.routers.chat_storage_router import router as chat_storage_router
# Removed chat_storage init import, it's done in lifespan
from eidos_agent.api.routers.pathos_hooks_router import router as pathos_hooks_router # Renamed to avoid conflict
from eidos_agent.api.routers.tts_router import router as tts_api_router
from eidos_agent.api.routers.tts_router import init_tts_router
from eidos_agent.api.routers.oai_compatible_router import router as oai_router
from eidos_agent.api.routers.oai_compatible_router import init_oai_router
from eidos_agent.api.routers.utility_router import router as utility_router
from eidos_agent.api.routers.utility_router import init_utility_router
from eidos_agent.api.routers.user_profile_router import router as user_profile_router
from eidos_agent.api.routers.user_profile_router import init_user_profile_router
from eidos_agent.api.routers.agent_actions_router import router as agent_actions_router
from eidos_agent.api.routers.agent_actions_router import init_agent_actions_router
from eidos_agent.api.routers.memory_management_router import router as memory_management_router
from eidos_agent.api.routers.memory_management_router import init_memory_management_router
from eidos_agent.api.routers.agent_state_router import router as agent_state_router # Import Agent State router
from eidos_agent.api.routers.agent_state_router import init_agent_state_router # Import Agent State router init function

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
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: # pragma: no cover
        headers["Authorization"] = f"Bearer {api_key}"
    warmup_messages = [{"role": "system", "content": static_system_prompt}, {"role": "user", "content": "Hello."}]
    payload = {"model": llm_model_name, "messages": warmup_messages, "max_tokens": 5, "temperature": 0.1, "stream": False}
    logger.debug(f"Warming VLLM cache: POST to {final_api_url} with model {llm_model_name}")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(final_api_url, headers=headers, json=payload)
            response.raise_for_status()
        logger.info(f"VLLM cache warming request sent successfully for Pathos model '{llm_model_name}' at {final_api_url}.")
    except Exception as e: # pragma: no cover
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
        # chat_storage.init_router(ethos_core) # This is now done by chat_storage_router itself if it needs ethos_core
        from eidos_agent.api.routers.chat_storage_router import init_chat_storage_router # Import init function
        init_chat_storage_router(ethos_core) # Call init function for chat_storage_router
        ethos_core.set_connection_manager(manager)
        if Config.get_ha_config(): # pragma: no cover
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
            static_prompt_for_vllm = pathos_interface.get_static_prompt_for_cache_warming() # Corrected method name
            if static_prompt_for_vllm: await warm_vllm_cache(pathos_interface, static_prompt_for_vllm)

        # Initialize TTS Router with dependencies
        if eidos_tts_service_instance:
            init_tts_router(eidos_tts_service_instance, TEMP_AUDIO_CACHE)
        else:
            logger.warning("ExternalTTSService instance not available in lifespan, TTS router not fully initialized.")

        # Initialize OpenAI Compatible Router with dependencies
        if all([Config, router, ethos_core, logos_core, pathos_interface, manager]): # router is InputRouter here
            init_oai_router(Config, router, ethos_core, logos_core, pathos_interface, manager)
        else: # pragma: no cover
            logger.error("One or more core components are None, OAI router not initialized.")

        # Initialize Utility Router with dependencies
        if all([logos_core, ethos_core, pathos_interface, router, manager]): # router is InputRouter here
            init_utility_router(logos_core, ethos_core, pathos_interface, router, manager)
        else: # pragma: no cover
            logger.error("One or more core components are None, Utility router not initialized.")

        # Initialize User Profile Router with dependencies
        if all([logos_core, ethos_core]):
            init_user_profile_router(logos_core, ethos_core)
        else: # pragma: no cover
            logger.error("One or more core components are None, User Profile router not initialized.")

        # Initialize Agent Actions Router with dependencies
        if all([pathos_interface, ethos_core, logos_core]):
            init_agent_actions_router(pathos_interface, ethos_core, logos_core)
        else: # pragma: no cover
            logger.error("One or more core components are None, Agent Actions router not initialized.")

        # Initialize Memory Management Router with dependencies
        if all([ethos_core, Config]): # Config is directly available
            init_memory_management_router(ethos_core, Config)
        else: # pragma: no cover
            logger.error("One or more core components are None (EthosCore or Config), Memory Management router not initialized.")

        # Initialize Agent State Router with dependencies
        if ethos_core:
            init_agent_state_router(ethos_core)
        else: # pragma: no cover
            logger.error("EthosCore is None, Agent State router not initialized.")

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
app.include_router(chat_storage_router, prefix="/v1")
app.include_router(pathos_hooks_router)
app.include_router(tts_api_router)
app.include_router(oai_router)
app.include_router(utility_router)
app.include_router(user_profile_router)
app.include_router(agent_actions_router)
app.include_router(memory_management_router)
app.include_router(agent_state_router) # Include Agent State router

if WEBAPP_DIR.is_dir(): # pragma: no cover
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

# The comments below indicate that these functions and endpoints have been moved.
# No need to define them here again.
# # Removed extract_input_to_eidos_format function (moved to oai_compatible_router.py)
# # Removed _log_final_parsed_input function (moved to oai_compatible_router.py)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError): # pragma: no cover
    logger.error(f"Pydantic Validation Error: {exc.errors()}")
    return PlainTextResponse(str(exc.errors()), status_code=422)

# --- API Endpoints ---

@app.get("/", include_in_schema=False)
async def get_gui_root(): # pragma: no cover
    gui_html_path = WEBAPP_DIR / "gui.html"
    if gui_html_path.is_file(): return FileResponse(str(gui_html_path))
    else: logger.error(f"GUI HTML file not found at {gui_html_path}"); return JSONResponse(content={"error": "Eidos GUI not found."}, status_code=404)

# # Removed list_models_endpoint (moved to oai_compatible_router.py)
# # Removed chat_completions endpoint (moved to oai_compatible_router.py)
# # Removed get_tts_audio_chunk endpoint (moved to tts_router.py)

# This /v1/weather endpoint seems to be a duplicate of the one below.
# Removing this first occurrence.
# @app.get("/v1/weather", status_code=200)
# The /v1/weather endpoint has been moved to the utility_router.
# @app.get("/v1/weather", status_code=200)
# async def get_weather_endpoint(location: str, x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
# The /v1/user/settings endpoint has been moved to the user_profile_router.
# @app.post("/v1/user/settings", status_code=200)
# async def update_user_settings(settings_request: UserSettingsRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
# The /v1/briefing endpoint has been moved to the agent_actions_router.
# @app.get("/v1/briefing", status_code=200)
# async def get_daily_briefing_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
#     global logos_core, ethos_core
#     # ... implementation ...

# Removed TTSRequestAPI model from here (already done in previous refactorings)
# Removed synthesize_speech_api endpoint from here (already done in previous refactorings)

# The /v1/feedback endpoint has been moved to the agent_actions_router.
# @app.post("/v1/feedback", status_code=202)
# async def receive_feedback(feedback_data: FeedbackRequest, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
#     global pathos_interface, ethos_core; request_id = str(uuid.uuid4())
#     # ... implementation ...

# The /health endpoint has been moved to the utility_router (already done).
# @app.get("/health")
# async def health_check():
#     # ... implementation ...

# The /v1/documents/upload endpoint has been moved to the agent_actions_router.
# @app.post("/v1/documents/upload", status_code=200)
# async def upload_document(file: UploadFile = File(..., description="Document (PDF, DOCX, TXT)"), x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
# The /v1/memory/clear endpoint has been moved to the memory_management_router.
# @app.post("/v1/memory/clear", status_code=200)
# async def clear_eidos_memory(x_user_id: Optional[str] = Header(None, alias="X-User-Id"), x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")): # pragma: no cover
#     global ethos_core
#     # ... implementation ...

# The /v1/memory/clear_user endpoint has been moved to the memory_management_router.
# @app.post("/v1/memory/clear_user", status_code=200)
# async def clear_user_memory(request_data: ClearUserMemoryRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")):
#     global ethos_core
#     # ... implementation ...

# The /v1/memory/entry/{memory_id} endpoint has been moved to the memory_management_router.
# @app.delete("/v1/memory/entry/{memory_id}", status_code=200, tags=["Memory Management"])
# async def delete_memory_entry_endpoint(
#     memory_id: str = FastApiPath(..., title="The ID of the memory entry to delete", min_length=36, max_length=36),
#     x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
#     x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")
# ):
#     global ethos_core
#     # ... implementation ...

# The /v1/user/facts endpoint has been moved to the user_profile_router (already done).
# @app.get("/v1/user/facts", response_model=List[ApiMemoryEntry], tags=["User Profile"])
# The /v1/agent/dreams endpoint has been moved to the agent_state_router.
# @app.get("/v1/agent/dreams", response_model=List[DreamEntryResponse], tags=["Agent State"])
# async def get_agent_dreams(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
#     global ethos_core
#     # ... implementation ...

# The /v1/agent/learnings endpoint has been moved to the agent_state_router.
# @app.get("/v1/agent/learnings", response_model=List[ApiMemoryEntry], tags=["Agent State"]) # Use ApiMemoryEntry
# async def get_agent_learnings(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
#     global ethos_core
#     # ... implementation ...

# The /v1/agent/knowledge_verifications endpoint has been moved to the agent_state_router.
# @app.get("/v1/agent/knowledge_verifications", response_model=List[ApiMemoryEntry], tags=["Agent State"]) # Use ApiMemoryEntry
# async def get_agent_knowledge_verifications(limit: int = 20, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
#     global ethos_core
#     # ... implementation ...

@app.get("/v1/pathos/schedule/today", response_model=List[ActivitySlot], tags=["Pathos Chronos"])
async def get_pathos_todays_schedule(): # pragma: no cover
    global ethos_core # This global is still used by other endpoints
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