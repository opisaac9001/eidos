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
# Updated EthosCore imports to persona_logic
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry # Used in response_model
# Removed HomeAssistantService import
from eidos_agent.persona_logic.ethos_core.core import EthosCore
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
from eidos_agent.llm_integrations.pathos_interface import PathosInterface # Updated import
from eidos_agent.features.oneiros import OneirosModule # Updated import
from eidos_agent.core.input_router import InputRouter, RoutingResult
# Updated import to use eidos_agent.schemas
from eidos_agent.schemas.oai_schemas import (
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
    ChatCompletionChoice, ChatCompletionUsage, ModelList, ModelCard
)
from eidos_agent.schemas.user_profile_schemas import UserSettingItem, UserSettingsRequest
from eidos_agent.schemas.ethos_schemas import ClearUserMemoryRequest, ApiMemoryEntry
from eidos_agent.schemas.feedback_schemas import FeedbackRequest
from eidos_agent.schemas.oneiros_schemas import DreamEntryResponse
from eidos_agent.core.connection_manager import ConnectionManager
from eidos_agent.services.external_tts_service import ExternalTTSService
# Updated imports for ChronosEngine and its models
from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine
from eidos_agent.persona_logic.chronos_engine.models import (
    PATHOS_USER_ID, ActivitySlot
)
# PathosEvent, EventType, PathosEventDetails were from a previous structure and not in the new models.py

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
from eidos_agent.api.routers.agent_state_router import router as agent_state_router
from eidos_agent.api.routers.agent_state_router import init_agent_state_router
from eidos_agent.api.routers.pathos_chronos_router import router as pathos_chronos_api_router
from eidos_agent.api.routers.pathos_chronos_router import init_pathos_chronos_router
from eidos_agent.api.routers.websocket_router import router as websocket_api_router # Import WebSocket router
from eidos_agent.api.routers.websocket_router import init_websocket_router # Import WebSocket router init function

# Firmament related imports
from eidos_agent.features.firmament.module import FirmamentModule
from eidos_agent.features.firmament.chronos_adapter import ChronosAdapter
from eidos_agent.features.firmament.npcs.npc_improviser import NPCImproviser
from eidos_agent.features.firmament.core.http_client_manager import HTTPClientManager # Added
from eidos_agent.llm_integrations.llm_client import LLMClient # Added

from eidos_agent.features.oneiros.tasks import oneiros_processing_task
from eidos_agent.system_tasks.subconscious_context_scheduler import SCHEDULER_STATE, init_scheduler as init_subconscious_scheduler
from eidos_agent.core.subconscious_orchestrator import (
    launch_subconscious_node_process,
    initialize_subconscious_node_state,
    check_subconscious_api_health,
    terminate_subconscious_node_process,
    SUBCONSCIOUS_NODE_STATE
)

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
    global ethos_core, logos_core, pathos_interface, oneiros_module, router, background_tasks, manager, eidos_tts_service_instance, SUBCONSCIOUS_NODE_STATE # Added firmament_module
    # ha_service: Optional[HomeAssistantService] = None # Removed
    owm_service: Optional[OpenWeatherMapService] = None
    # firmament_module global variable is removed as it's instantiated and used within lifespan
    # firmament_module: Optional[FirmamentModule] = None
    http_client_manager_instance: Optional[HTTPClientManager] = None # For global access if needed, and shutdown
    llm_client_instance: Optional[LLMClient] = None

    logger.info("--- Initializing Eidos System for API (Lifespan Startup) ---")
    try:
        http_client_manager_instance = HTTPClientManager()
        await http_client_manager_instance.startup()
        llm_client_instance = LLMClient(http_client_manager_instance)
        logger.info("Lifespan: HTTPClientManager and LLMClient initialized.")

        logger.info("Lifespan: Starting core component initialization...")
        if not llm_client_instance: raise RuntimeError("LLMClient not initialized, cannot proceed.") # Should not happen
        ethos_core = EthosCore(Config, llm_client_instance) # Pass LLMClient to EthosCore
        # chat_storage.init_router(ethos_core) # This is now done by chat_storage_router itself if it needs ethos_core

        from eidos_agent.api.routers.chat_storage_router import init_router # Import init function
        init_router(ethos_core) # Call init function for chat_storage_router
        ethos_core.set_connection_manager(manager)
        # Removed HomeAssistantService initialization block
        if Config.get_openweathermap_config() and Config.get_openweathermap_config().get('api_key'):
            owm_service = OpenWeatherMapService(Config)
            if not owm_service.is_available: logger.warning("Lifespan: OWMService not available.")
        if Config.ENABLE_ONEIROS and ethos_core:
            oneiros_module = OneirosModule(Config, ethos_core)
            if ethos_core: ethos_core.oneiros_module = oneiros_module

        # Instantiate LogosCore
        if not llm_client_instance: raise RuntimeError("LLMClient not available for LogosCore")
        if not http_client_manager_instance: raise RuntimeError("HTTPClientManager not available for LogosCore")

        logos_core = LogosCore(
            Config,
            ethos_core,
            llm_client_instance, # Pass LLMClient
            # http_client_manager_instance, # Pass HTTPClientManager - check LogosCore __init__
            owm_service=owm_service,
            firmament_module=None # Initially None, will be set later
        )
        # Note: The skeletal LogosCore __init__ was (config, ethos_core, llm_client, firmament_module)
        # It did not include http_client_manager or owm_service directly in the last skeletal version.
        # For now, I'll match the skeletal version. If other tools in a fuller LogosCore need these,
        # the __init__ of the *full* LogosCore would need to be updated.
        # The current skeletal LogosCore __init__:
        # (self, config: Config, ethos_core: EthosCore, llm_client: LLMClient, firmament_module: Optional[FirmamentModule] = None)
        # So, owm_service and http_client_manager are not passed to this version.
        # This might need adjustment if we were restoring full LogosCore functionality.
        # For now, using the skeletal __init__(config, ethos_core, llm_client, firmament_module=None)
        logos_core = LogosCore(
            config=Config,
            ethos_core=ethos_core,
            llm_client=llm_client_instance,
            firmament_module=None # Set later
        )
        # await logos_core.initialize_services() # This method might not exist in skeletal LogosCore or be needed yet

        if ethos_core: ethos_core.set_logos_core(logos_core) # Set logos_core in ethos_core

        chronos_engine_instance: Optional[ChronosEngine] = None
        if ethos_core:
            chronos_engine_instance = ChronosEngine(Config, ethos_core)
            if ethos_core: ethos_core.set_chronos_engine(chronos_engine_instance)
            logger.info("Lifespan: ChronosEngine initialized and set in EthosCore.")
        else:
            logger.warning("Lifespan: ChronosEngine NOT initialized due to missing EthosCore.")

        # Instantiate PathosInterface
        if not http_client_manager_instance: raise RuntimeError("HTTPClientManager not available for PathosInterface")
        if not ethos_core: raise RuntimeError("EthosCore not available for PathosInterface")
        if not logos_core: raise RuntimeError("LogosCore not available for PathosInterface")
        # FirmamentModule and ChronosEngine can be None initially for PathosInterface

        pathos_interface = PathosInterface(
            config=Config,
            ethos_core=ethos_core,
            logos_core=logos_core,
            connection_manager=manager,
            firmament_module=None, # Will be set later if Firmament initializes
            chronos_engine=chronos_engine_instance, # Can be None if ChronosEngine failed
            http_client_manager=http_client_manager_instance
        )
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

        # Initialize Pathos Chronos Router with dependencies
        if all([ethos_core, Config]): # Config is directly available
            init_pathos_chronos_router(ethos_core, Config)
        else: # pragma: no cover
            logger.error("One or more core components are None (EthosCore or Config), Pathos Chronos router not initialized.")

        # Initialize WebSocket Router with dependencies
        if manager: # manager is the ConnectionManager instance
            init_websocket_router(manager)
        else: # pragma: no cover
            logger.error("ConnectionManager (manager) is None, WebSocket router not initialized.")

        firmament_module_instance: Optional[FirmamentModule] = None # Define for use in shutdown
        if ethos_core and chronos_engine_instance and Config.get_firmament_module_config().get("enable_firmament"):
            logger.info("Lifespan: Firmament is enabled. Initializing FirmamentModule...")
            try:
                # Initialize Firmament components
                npc_improviser_instance = NPCImproviser() # Uses Config internally for LLM role
                if not chronos_engine_instance: # Should not happen if ethos_core exists
                    raise RuntimeError("ChronosEngine not initialized, cannot create ChronosAdapter for Firmament.")
                chronos_adapter_instance = ChronosAdapter(chronos_engine=chronos_engine_instance, ethos_core=ethos_core)

                firmament_module_instance = FirmamentModule(
                    config=Config,
                    ethos_core=ethos_core,
                    chronos_adapter=chronos_adapter_instance,
                    npc_improviser=npc_improviser_instance,
                    llm_client=llm_client_instance # Pass LLMClient to FirmamentModule
                )
                await firmament_module_instance.start()
                if ethos_core: ethos_core.set_firmament_module(firmament_module_instance) # ethos_core already checked above

                # Set FirmamentModule in LogosCore
                if logos_core and firmament_module_instance:
                    logos_core.set_firmament_module(firmament_module_instance)
                    logger.info("Lifespan: FirmamentModule instance set in LogosCore.")
                elif logos_core:
                    logger.warning("Lifespan: FirmamentModule instance is None after init, not setting in LogosCore.")

                logger.info("Lifespan: FirmamentModule initialized, started, and set in EthosCore.")
            except Exception as e_firmament:
                logger.error(f"Lifespan: Failed to initialize or start FirmamentModule: {e_firmament}", exc_info=True)
                firmament_module_instance = None # Ensure it's None if init fails
        elif Config.get_firmament_module_config().get("enable_firmament"):
            logger.warning("Lifespan: FirmamentModule enabled in config, but core dependencies (EthosCore, ChronosEngine, or LLMClient) are missing. Firmament will not be initialized.")

        # Update PathosInterface with FirmamentModule if it was successfully created
        if pathos_interface and firmament_module_instance:
            pathos_interface.firmament_module = firmament_module_instance # Directly set if PathosInterface has this attr
            logger.info("Lifespan: FirmamentModule instance set in PathosInterface.")


        if ethos_core: # ethos_core check is still relevant for other tasks
            background_tasks = await ethos_core.get_background_tasks() # EthosCore now potentially adds Firmament task via set_firmament_module
            # Initialize subconscious_context_scheduler after ethos_core is ready
            try:
                current_loop = asyncio.get_running_loop()
                init_subconscious_scheduler(ethos_core, current_loop) # Pass the running event loop
                logger.info("Lifespan: Subconscious context scheduler initialized with EthosCore and event loop.")
            except RuntimeError as e_loop: # pragma: no cover
                logger.error(f"Lifespan: Could not get running event loop for subconscious scheduler: {e_loop}", exc_info=True)
                # Decide if this is critical enough to stop startup
                # For now, we'll log an error and continue, scheduler might not work.
            except Exception as e_sched_init: # pragma: no cover
                logger.error(f"Lifespan: Failed to initialize subconscious_context_scheduler: {e_sched_init}", exc_info=True)


            # Launch Subconscious Node Process
            # Note: orchestrator functions are synchronous, removed await.
            subconscious_process_obj = launch_subconscious_node_process()
            if subconscious_process_obj: # Check if process object was returned
                logger.info(f"Lifespan: Subconscious Node process launch attempted (PID: {subconscious_process_obj.pid if subconscious_process_obj else 'Unknown'}).")
                if check_subconscious_api_health():
                    logger.info("Lifespan: Subconscious Node API is healthy.")
                    if initialize_subconscious_node_state(): # AWAKE_THINKING is default
                        logger.info("Lifespan: Subconscious Node state initialized.")
                    else:
                        logger.error("Lifespan: Failed to initialize Subconscious Node state.")
                else:
                    logger.error("Lifespan: Subconscious Node API health check failed.")
            else:
                logger.error("Lifespan: Failed to launch Subconscious Node process (launch_subconscious_node_process returned None).")

            # Launch Oneiros Processing Task
            if oneiros_module and Config.ENABLE_ONEIROS: # Check if oneiros is enabled
                try:
                    # Get interval from the renamed config key
                    oneiros_check_interval = Config.ONEIROS.get('oneiros_check_interval_seconds', 300) # Default 5 mins (300s)
                    if not isinstance(oneiros_check_interval, (int, float)) or oneiros_check_interval <= 0: # Validate interval
                        logger.warning(f"Lifespan: Invalid Oneiros oneiros_check_interval_seconds ({oneiros_check_interval}). Using default 300s.")
                        oneiros_check_interval = 300

                    logger.info(f"Lifespan: Launching Oneiros processing task with check interval {oneiros_check_interval}s.")
                    oneiros_proc_task = asyncio.create_task(
                        oneiros_processing_task( # This task is defined in eidos_agent.features.oneiros.tasks
                            oneiros_module=oneiros_module,
                            subconscious_scheduler_state=SCHEDULER_STATE, # For checking if Pathos is sleeping
                            processing_interval_seconds=int(oneiros_check_interval) # This param name is used by the task
                        )
                    )
                    background_tasks.append(oneiros_proc_task) # Add to existing list for shutdown handling
                    logger.info("Lifespan: oneiros_processing_task added to background tasks.")
                except Exception as e_oneiros_task_start:
                    logger.error(f"Lifespan: Failed to create or add oneiros_processing_task: {e_oneiros_task_start}", exc_info=True)
            elif Config.ENABLE_ONEIROS: # Oneiros enabled but module instance is None (init failed)
                logger.warning("Lifespan: Oneiros enabled in config, but OneirosModule instance not available. Processing task not started.")
            else: # Oneiros not enabled at all
                logger.info("Lifespan: Oneiros is disabled by configuration. Processing task not started.")

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
        # if ha_service: await ha_service.disconnect() # Removed
        if owm_service and hasattr(owm_service, 'close'): await owm_service.close() # type: ignore
        if firmament_module_instance: await firmament_module_instance.close() # Close FirmamentModule
        if oneiros_module: await oneiros_module.close()
        if ethos_core: await ethos_core.close()
        if eidos_tts_service_instance: await eidos_tts_service_instance.close()
        if http_client_manager_instance: # Shutdown HTTPClientManager
            await http_client_manager_instance.shutdown()
            logger.info("Lifespan: HTTPClientManager shutdown.")
        # Terminate Subconscious Node Process
        # Note: orchestrator function is synchronous, removed await.
        # It also manages its own process reference internally.
        logger.info("Lifespan: Attempting to terminate Subconscious Node process...")
        terminate_subconscious_node_process()
        # The function logs success/failure internally.

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
app.include_router(agent_state_router)
app.include_router(pathos_chronos_api_router)
app.include_router(websocket_api_router) # Include WebSocket router

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
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']: 
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model_name, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 5, "temperature": 0.1}
    try:
        timeout_val = float(llm_config.get('timeout', 5))  # Reduced from 15 to 5 for faster startup
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
# The /v1/pathos/schedule/today endpoint has been moved to the pathos_chronos_router.
# @app.get("/v1/pathos/schedule/today", response_model=List[ActivitySlot], tags=["Pathos Chronos"])
# async def get_pathos_todays_schedule(): # pragma: no cover
#     global ethos_core
#     # ... implementation ...

# The /v1/pathos/events/upcoming endpoint has been moved to the pathos_chronos_router.
# @app.get("/v1/pathos/events/upcoming", response_model=List[PathosEvent], tags=["Pathos Chronos"])
# async def get_pathos_upcoming_events(days_ahead: int = 7):
#     global ethos_core
#     # ... implementation ...

# The AddPathosEventRequestAPI model has been moved to the pathos_chronos_router.
# class AddPathosEventRequestAPI(BaseModel):
#     title: str; start_date: str; end_date: str; event_type: EventType
#     description: Optional[str] = None; location: Optional[str] = None
#     details: Optional[PathosEventDetails] = None

# The /v1/pathos/events/add endpoint has been moved to the pathos_chronos_router.
# @app.post("/v1/pathos/events/add", response_model=PathosEvent, status_code=201, tags=["Pathos Chronos"])
# The /ws WebSocket endpoint has been moved to the websocket_router.
# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket): # pragma: no cover
#     # ... implementation ...

if __name__ == "__main__": # pragma: no cover
    uvicorn.run("main:app", host=Config.API.get('host','0.0.0.0'), port=Config.API.get('port',8088), log_level=Config.API.get('log_level','info'), reload=False)