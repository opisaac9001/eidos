# main.py

import asyncio
import logging
import sys
import time
import uuid
import httpx
import io # For BytesIO in StreamingResponse
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
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse # Ensure StreamingResponse is here
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder

from pydantic import BaseModel, ValidationError, Field

# Eidos Agent imports
from eidos_agent.core.config import Config # Config.setup() is called on import
from eidos_agent.utils.logger import get_logger, configure_logging

# --- Configure logging at the very start ---
configure_logging()
logger = get_logger(__name__)

# --- Define BASE_DIR and WEBAPP_DIR at module level ---
BASE_DIR = Path(__file__).resolve().parent
WEBAPP_DIR = BASE_DIR / "webapp"

# --- Import other Eidos components AFTER basic setup ---
from eidos_agent.services.openweathermap import OpenWeatherMapService
from eidos_agent.modules.ethos_core.memory_storage import MemoryEntry
from eidos_agent.services.home_assistant import HomeAssistantService
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.pathos_interface import PathosInterface # PathosInterface will be modified
from eidos_agent.modules.oneiros_module import OneirosModule
from eidos_agent.core.input_router import InputRouter, RoutingResult
from eidos_agent.core.api_models import (
    ChatCompletionRequest, ChatCompletionResponse, ChatMessage,
    ChatCompletionChoice, ChatCompletionUsage, ModelList, ModelCard,
    UserSettingItem, UserSettingsRequest, ClearUserMemoryRequest,
    FeedbackRequest, DreamEntryResponse
)
# MemoryEntry is already imported from ethos_core.memory_storage
from eidos_agent.core.connection_manager import ConnectionManager
from eidos_agent.services.external_tts_service import ExternalTTSService


# --- Global Variables ---
ethos_core: Optional[EthosCore] = None
logos_core: Optional[LogosCore] = None
pathos_interface: Optional[PathosInterface] = None # Will be instantiated in lifespan
oneiros_module: Optional[OneirosModule] = None
router: Optional[InputRouter] = None
background_tasks: List[asyncio.Task] = []
manager = ConnectionManager()
eidos_tts_service_instance: Optional[ExternalTTSService] = None # For TTS synthesis

# NEW: Global cache for temporary audio chunks for TTS streaming
TEMP_AUDIO_CACHE: Dict[str, bytes] = {}
# Optional: Add a lock if you anticipate highly concurrent access modifying this dict,
# though FastAPI's event loop usually serializes access to globals within handlers.
# TEMP_AUDIO_CACHE_LOCK = asyncio.Lock()


# --- Helper for VLLM Cache Warming ---
async def warm_vllm_cache(pathos_if: PathosInterface, static_system_prompt: str):
    if not pathos_if.pathos_llm_config or \
       not pathos_if.pathos_llm_config.get('url') or \
       not static_system_prompt:
        logger.warning("VLLM Cache Warming: LLM config or static prompt content missing. Skipping.")
        return

    logger.info("Attempting to warm VLLM cache with the static system prompt...")
    try:
        warmup_messages = [
            {"role": "system", "content": static_system_prompt},
            {"role": "user", "content": "Hello."}
        ]
        
        # Use a simplified, non-streaming call via PathosInterface's http_client
        # or directly construct the call here.
        # This reuses some logic from PathosInterface._prepare_llm_call_params
        # but for a one-off, non-streaming call.

        llm_config = pathos_if.pathos_llm_config
        final_api_url, final_model_name, headers, _, _ = pathos_if._prepare_llm_call_params(
            temperature=0.1, # Low temp for warming
            max_tokens_override=5, # Minimal tokens needed
            llm_provider_url_override=None, # Use configured URL
            pathos_model_override=None # Use configured model
        )

        if not final_api_url or not final_model_name:
            logger.error("VLLM Cache Warming: Could not determine API URL or model name. Skipping.")
            return

        payload = {
            "model": final_model_name,
            "messages": warmup_messages,
            "max_tokens": 5,
            "temperature": 0.1,
            "stream": False # Non-streaming for warming
        }

        async with httpx.AsyncClient(timeout=30.0) as client: # Dedicated client for warming
            response = await client.post(final_api_url, headers=headers, json=payload)
            response.raise_for_status()
        
        logger.info(f"VLLM cache warming request sent successfully for model '{final_model_name}'. "
                    f"Prefix for static system prompt (length: {len(static_system_prompt)}) should now be in vLLM's KV cache.")

    except Exception as e:
        logger.error(f"Failed to warm VLLM cache: {e}", exc_info=True)


# --- FastAPI Lifecycle Events ---
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global ethos_core, logos_core, pathos_interface, oneiros_module, router, background_tasks, manager, eidos_tts_service_instance
    
    ha_service: Optional[HomeAssistantService] = None
    owm_service: Optional[OpenWeatherMapService] = None

    logger.info("--- Initializing Eidos System for API (Lifespan Startup) ---")
    try:
        logger.info("Lifespan: Starting core component initialization...")
        # ... (EthosCore, HA, OWM, Oneiros, LogosCore initialization as before) ...
        ethos_core = EthosCore(Config)
        ethos_core.set_connection_manager(manager)

        if Config.get_ha_config():
             ha_service = HomeAssistantService(Config, ethos_core.memory_storage)
             try: await ha_service.connect()
             except Exception as ha_e: logger.error(f"Lifespan: Failed to connect HomeAssistantService: {ha_e}", exc_info=True); ha_service = None
        
        if Config.get_openweathermap_config() and Config.get_openweathermap_config().get('api_key'):
             owm_service = OpenWeatherMapService(Config)
             if not owm_service.is_available: logger.warning("Lifespan: OWMService not available (e.g., API key missing).")
        
        if Config.ENABLE_ONEIROS and ethos_core:
            oneiros_module = OneirosModule(Config, ethos_core)
            ethos_core.oneiros_module = oneiros_module
        
        logos_core = LogosCore(Config, ethos_core, ha_service, owm_service)
        await logos_core.initialize_services()
        if ethos_core: ethos_core.logos_core = logos_core


        # Initialize PathosInterface
        logger.info("Lifespan: Initializing PathosInterface...")
        pathos_interface = PathosInterface(Config, ethos_core, logos_core, manager)
        logger.info("Lifespan: PathosInterface initialized.")
        if ethos_core:
            ethos_core.set_pathos_interface(pathos_interface) # Ethos needs Pathos for proactive message generation
            logger.info("Lifespan: PathosInterface set in EthosCore.")

        # Initialize InputRouter
        logger.info("Lifespan: Initializing InputRouter...")
        if ethos_core and logos_core and pathos_interface:
            router = InputRouter(config=Config, ethos_core=ethos_core, logos_core=logos_core, pathos_interface=pathos_interface)
            logger.info("Lifespan: InputRouter initialized.")
        else:
            logger.error("Lifespan: InputRouter NOT initialized due to missing core components.")
            raise RuntimeError("Failed to initialize InputRouter due to missing core components.")

        # Initialize ExternalTTSService
        if Config.EIDOS_TTS and isinstance(Config.EIDOS_TTS, dict) and Config.EIDOS_TTS.get('api_url'):
            logger.info("Lifespan: Initializing ExternalTTSService...")
            try:
                eidos_tts_service_instance = ExternalTTSService(config=Config)
                if eidos_tts_service_instance.is_available():
                    logger.info("Lifespan: ExternalTTSService initialized successfully and is available.")
                    if pathos_interface: # Pass TTS service to PathosInterface
                        pathos_interface.set_tts_service(eidos_tts_service_instance)
                else:
                    logger.error("Lifespan: ExternalTTSService initialized BUT IS NOT AVAILABLE.")
                    eidos_tts_service_instance = None
            except Exception as e_tts_init:
                logger.error(f"Lifespan: Failed to initialize ExternalTTSService: {e_tts_init}", exc_info=True)
                eidos_tts_service_instance = None
        else:
            logger.warning(f"Lifespan: ExternalTTSService initialization SKIPPED (Config missing or api_url not set).")
            eidos_tts_service_instance = None
        
        # LLM Availability Check
        await check_critical_llm_availability()

        # NEW: VLLM Cache Warming
        if pathos_interface and Config.LLM.get("PATHOS", {}).get("url"): # Check if Pathos LLM is configured
            logger.info("Lifespan: Attempting to warm vLLM cache for Pathos static system prompt...")
            static_prompt_for_vllm = pathos_interface.get_static_system_prompt_content()
            if static_prompt_for_vllm:
                await warm_vllm_cache(pathos_interface, static_prompt_for_vllm)
            else:
                logger.warning("Lifespan: Could not get static system prompt for vLLM cache warming.")
        else:
            logger.info("Lifespan: Skipping vLLM cache warming (PathosInterface or Pathos LLM URL not available).")


        # Background tasks from EthosCore
        if ethos_core:
            background_tasks = await ethos_core.get_background_tasks()
            for task in background_tasks: logger.info(f"Lifespan: Created background task: {task.get_name()}")
        
        logger.info("--- Eidos System Initialized Successfully (End of Lifespan Startup Try Block) ---")
        yield
        logger.info("--- Shutting Down Eidos System (Lifespan Shutdown) ---")
        # ... (Shutdown logic as before: cancel tasks, close connections) ...
        active_bg_tasks = [task for task in background_tasks if not task.done()]
        if active_bg_tasks:
            logger.info(f"Lifespan: Cancelling {len(active_bg_tasks)} background tasks...")
            for task in active_bg_tasks: task.cancel()
            try: await asyncio.wait(active_bg_tasks, timeout=5.0)
            except asyncio.TimeoutError: logger.warning("Lifespan: Timeout waiting for some background tasks to cancel.")
            except asyncio.CancelledError: logger.debug("Lifespan: Background task group cancellation processed.")
        if manager: await manager.disconnect_all()
        if pathos_interface: await pathos_interface.close()
        if logos_core: await logos_core.close()
        if ha_service: await ha_service.disconnect()
        if owm_service and hasattr(owm_service, 'close'): await owm_service.close()
        if oneiros_module: await oneiros_module.close()
        if ethos_core: await ethos_core.close_memory_connection()
        if eidos_tts_service_instance: await eidos_tts_service_instance.close()
        TEMP_AUDIO_CACHE.clear() # Clear in-memory audio cache on shutdown
        logger.info("--- Eidos System Shutdown Complete ---")

    except Exception as e_lifespan_main:
        logger.critical(f"--- System Initialization Failed Critically in Lifespan ---: {str(e_lifespan_main)}", exc_info=True)
        # Attempt to clean up any partially initialized components if possible
        if 'pathos_interface' in locals() and pathos_interface and hasattr(pathos_interface, 'close'): await pathos_interface.close()
        if 'logos_core' in locals() and logos_core and hasattr(logos_core, 'close'): await logos_core.close()
        # ... other cleanup ...
        raise RuntimeError("Eidos system failed to initialize during lifespan startup.") from e_lifespan_main


app = FastAPI(title="Eidos Agent API", version="1.0", lifespan=lifespan)

# --- Mount static files (as before) ---
# ... (Static file mounting logic for webapp and dream_images) ...
if WEBAPP_DIR.is_dir():
    js_dir = WEBAPP_DIR / "js"; css_dir = WEBAPP_DIR / "css"
    if js_dir.is_dir(): app.mount("/js", StaticFiles(directory=js_dir), name="js")
    else: logger.warning(f"JS directory not found at {js_dir}.")
    if css_dir.is_dir(): app.mount("/css", StaticFiles(directory=css_dir), name="css")
    else: logger.warning(f"CSS directory not found at {css_dir}.")
else: logger.error(f"WebApp directory '{WEBAPP_DIR}' not found.")

if Config.ENABLE_ONEIROS and Config.ONEIROS and Config.ONEIROS.get('enable_image_dreams') and Config.IMAGE_OUTPUT_DIR:
    try:
        image_output_path_static = Path(Config.IMAGE_OUTPUT_DIR)
        if not image_output_path_static.is_absolute(): image_output_path_static = BASE_DIR / Config.IMAGE_OUTPUT_DIR
        image_output_path_static.mkdir(parents=True, exist_ok=True)
        if image_output_path_static.is_dir():
            app.mount("/dream_images", StaticFiles(directory=str(image_output_path_static.resolve())), name="dream_images")
            logger.info(f"Mounted dream images directory at /dream_images from {str(image_output_path_static.resolve())}")
    except Exception as e_mount_static: logger.error(f"Error mounting dream image directory: {e_mount_static}", exc_info=True)


# --- CORS Middleware (as before) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-User-Id", "X-Admin-Password"],
)

# --- LLM Availability Check Functions (as before, ensure vLLM API key handling is included) ---
async def check_llm_role_availability(role_name: str, llm_config: Optional[Dict[str, Any]]):
    if not llm_config or not llm_config.get('url') or not llm_config.get('model'):
        logger.warning(f"LLM Check: Role '{role_name}' is not configured with a URL and model. Skipping.")
        return True # Not configured is not a "failure" for this check, just a skip.
    
    api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"
    model_name = llm_config['model']
    headers = {"Content-Type": "application/json"}
    api_key = llm_config.get('api_key')
    # MODIFIED: Added 'vllm', 'none' to keys that don't need Bearer token
    if api_key and api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {"model": model_name, "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 5, "temperature": 0.1}
    try:
        timeout_val = float(llm_config.get('timeout', 5)) # Reduced from 15 to 5 for faster startup
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            logger.info(f"LLM Check: Pinging model '{model_name}' for role '{role_name}' at {api_url}...")
            response = await client.post(api_url, headers=headers, json=payload)
            # ... (rest of check_llm_role_availability logic as before) ...
            if response.status_code == 200:
                logger.info(f"LLM Check: SUCCESS - Role '{role_name}' (Model: {model_name}) is responding at {llm_config['url']}.")
                return True
            # ... (error handling for 404, etc.)
            logger.error(f"LLM Check: FAILED - Role '{role_name}' (Model: {model_name}) at {llm_config['url']} returned {response.status_code}. Resp: {response.text[:200]}")
            return False
    except httpx.ConnectError: logger.error(f"LLM Check: FAILED - Connection refused for role '{role_name}' (Model: {model_name}) at {llm_config['url']}. Ensure LLM provider is running."); return False
    except Exception as e: logger.error(f"LLM Check: FAILED - Error checking role '{role_name}' (Model: {model_name}) at {llm_config['url']}: {e}", exc_info=True); return False


async def check_critical_llm_availability():
    # ... (as before) ...
    logger.info("--- Performing Critical LLM Availability Checks ---"); all_critical_llms_ok = True
    critical_roles_map = {
        "PATHOS": Config.LLM.get('PATHOS'),
        "LOGOS_TECHNE (Summarization/Reflection/Upkeep)": Config.get_llm_config(Config.ETHOS.get('summarization_llm_role', 'LOGOS_TECHNE')),
        "ONEIROS_DREAM_LLM": Config.get_llm_config(Config.ONEIROS.get('dream_llm_role', 'PATHOS')) if Config.ONEIROS else None
    }
    if Config.ENABLE_VISION_PROCESSING: critical_roles_map["LOGOS_VISION_CONTEXT"] = Config.LLM.get('LOGOS_VISION_CONTEXT')
    if Config.ENABLE_KNOWLEDGE_UPKEEP: critical_roles_map["KNOWLEDGE_UPKEEP_LLM"] = Config.get_llm_config(Config.ETHOS.get('knowledge_upkeep_llm_role', 'LOGOS_TECHNE'))

    for role_description, llm_config_to_check in critical_roles_map.items():
        if llm_config_to_check:
            if not await check_llm_role_availability(role_description, llm_config_to_check): all_critical_llms_ok = False
        else: logger.warning(f"LLM Check: Config for critical role '{role_description}' not found/incomplete. Skipping check.")
    if not all_critical_llms_ok:
        logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.critical("!!! WARNING: One or more critical LLMs are not available or not configured. !!!"); logger.critical("!!! Eidos functionality will be significantly impaired.                   !!!"); logger.critical("!!! Please check logs and ensure LLM provider is running with models loaded.!!!"); logger.critical("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else: logger.info("--- All checked critical LLMs appear to be available. ---")


# --- Input Parsing (MODIFIED to include auto_tts_enabled_for_response) ---
def extract_input_to_eidos_format(body: dict, request_id: str, user_id_from_header: Optional[str]) -> dict:
    raw_user_id = user_id_from_header or body.get('user') or 'api_guest_user'
    final_user_id = raw_user_id.lower().strip().replace(" ", "_") if raw_user_id else 'api_guest_user'
    if not final_user_id: final_user_id = 'api_guest_user'
    logger.debug(f"Request {request_id}: User ID for this request set to (normalized): '{final_user_id}' (Raw was: '{raw_user_id}')")
    
    temperature_from_body = body.get('temperature')
    model_from_body = body.get('model') # This is the model selected in GUI dropdown
    max_tokens_override, llm_provider_url_override = None, None
    auto_tts_enabled = False # Default

    if body_metadata := body.get('metadata'): # Eidos-specific metadata from client
        if isinstance(body_metadata, dict):
            max_tokens_override = body_metadata.get('max_tokens_override')
            llm_provider_url_override = body_metadata.get('llm_provider_url_override')
            # NEW: Extract auto_tts_enabled_for_response
            auto_tts_enabled = body_metadata.get('auto_tts_enabled_for_response', False)
            if max_tokens_override: logger.debug(f"Request {request_id}: Found max_tokens_override in metadata: {max_tokens_override}")
            if llm_provider_url_override: logger.debug(f"Request {request_id}: Found llm_provider_url_override in metadata: {llm_provider_url_override}")
            logger.debug(f"Request {request_id}: auto_tts_enabled_for_response from metadata: {auto_tts_enabled}")


    input_data = {
        "type": "text", "text_content": "", "image_content_b64": None, "document_text": None,
        "metadata": {
            "conversation_history": [], "source": "api_openai_compat_new_parser",
            "timestamp": datetime.now(timezone.utc).isoformat(), "user_id": final_user_id,
            "temperature": temperature_from_body,
            "max_tokens_override": max_tokens_override,
            "llm_provider_url_override": llm_provider_url_override,
            "pathos_model_override": model_from_body, # This is the GUI selected model
            "engaged_proactive_id": body.get('metadata', {}).get('engaged_proactive_id'),
            "force_web_search_requested": False,
            "auto_tts_enabled_for_response": auto_tts_enabled # Store the flag
        }
    }
    # ... (rest of message parsing logic as before, including FORCE_SEARCH_PREFIX) ...
    messages = body.get("messages", [])
    if not messages: logger.warning(f"Request {request_id}: No messages found in body."); return input_data
    if len(messages) > 1:
        for msg_dict in messages[:-1]: # History messages
            role, content = msg_dict.get("role"), msg_dict.get("content")
            tool_calls, tool_id = msg_dict.get("tool_calls"), msg_dict.get("tool_call_id")
            if role not in ["system", "user", "assistant", "tool"]: continue
            entry: Dict[str, Any] = {"role": role}
            if isinstance(content, str): entry["content"] = content
            elif isinstance(content, list): # Handle multimodal history content
                txt_parts, img_hist = [], False
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text": txt_parts.append(part.get("text", ""))
                    elif isinstance(part, dict) and part.get("type") == "image_url": img_hist = True
                final_txt = " ".join(txt_parts).strip()
                if img_hist: final_txt += " [Image was present in history]"
                entry["content"] = final_txt.strip() or None
            elif content is not None: entry["content"] = str(content) # Fallback for other types
            if tool_calls: entry["tool_calls"] = tool_calls
            if role == "tool" and tool_id: entry["tool_call_id"] = tool_id
            if entry.get("content") or entry.get("tool_calls") or entry.get("tool_call_id"):
                input_data["metadata"]["conversation_history"].append(entry)

    last_msg = messages[-1] # Current user message
    if last_msg.get("role") != "user": logger.warning(f"Request {request_id}: Last message not from 'user', role: {last_msg.get('role')}.")
    last_content = last_msg.get("content", ""); text_parts_concat = []
    if isinstance(last_content, str): text_parts_concat.append(last_content)
    elif isinstance(last_content, list): # Multimodal input
        input_data["type"] = "multimodal_input"
        for part_item in last_content:
            if isinstance(part_item, dict):
                if part_item.get("type") == "text":
                    text_part = part_item.get("text", "")
                    doc_match = re.search(r"--- Uploaded Document Content ---\n([\s\S]*?)\n--- End Uploaded Document Content ---", text_part)
                    if doc_match:
                         input_data["document_text"] = doc_match.group(1).strip()
                         text_parts_concat.append(text_part.split("--- Uploaded Document Content ---")[0].strip())
                         text_parts_concat.append(text_part.split("--- End Uploaded Document Content ---")[-1].strip())
                    else: text_parts_concat.append(text_part)
                elif part_item.get("type") == "image_url":
                    img_url_data = part_item.get("image_url", {})
                    if isinstance(img_url_data, dict) and (img_url_str := img_url_data.get("url")) and img_url_str.startswith("data:image"):
                        try: input_data["image_content_b64"] = img_url_str.split(",", 1)[1]
                        except IndexError: logger.error(f"Request {request_id}: Malformed base64 image URL.")
            else: text_parts_concat.append(str(part_item)) # Non-dict items in list, treat as text
    raw_text_content = " ".join(filter(None, text_parts_concat)).strip()
    FORCE_SEARCH_PREFIX_PY = "[FORCE_WEB_SEARCH] "
    if raw_text_content.startswith(FORCE_SEARCH_PREFIX_PY):
        input_data["metadata"]["force_web_search_requested"] = True
        input_data["text_content"] = raw_text_content[len(FORCE_SEARCH_PREFIX_PY):].strip()
    else: input_data["text_content"] = raw_text_content
    if isinstance(input_data["text_content"], str) and "#### Tools Available" in input_data["text_content"]:
        input_data["text_content"] = input_data["text_content"].split("#### Tools Available")[0].strip()
    
    logger.info(
        f"Request {request_id}: Input parser. Type: {input_data['type']}. "
        f"ForceSearch: {input_data['metadata']['force_web_search_requested']}. "
        f"TTS Enabled for Resp: {input_data['metadata']['auto_tts_enabled_for_response']}. " # Log new flag
        f"Img: {bool(input_data['image_content_b64'])}. Doc: {bool(input_data['document_text'])}. "
        f"Temp: {input_data['metadata'].get('temperature')}. MaxTokOverride: {input_data['metadata'].get('max_tokens_override')}. "
        f"LLMProviderOverride: {input_data['metadata'].get('llm_provider_url_override')}. "
        f"PathosModel(Dropdown): {input_data['metadata'].get('pathos_model_override')}. "
        f"EngagedProactiveID: {input_data['metadata'].get('engaged_proactive_id')}. "
        f"Text: '{str(input_data['text_content'])[:50]}...'"
    )
    return input_data


# --- API Endpoints ---

@app.delete("/v1/memory/entry/{memory_id}", status_code=200)
async def delete_memory_entry_endpoint(
    memory_id: str = FastApiPath(..., title="The ID of the memory entry to delete", min_length=36, max_length=36),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")
):
    global ethos_core
    if not ethos_core:
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    # --- Normalize the requesting user ID ---
    requesting_user_raw: Optional[str] = x_user_id
    requesting_user_normalized: str = "unknown_api_caller" # Default if all else fails

    if requesting_user_raw and isinstance(requesting_user_raw, str):
        normalized = requesting_user_raw.lower().strip().replace(" ", "_")
        if normalized: # Ensure not empty after normalization
            requesting_user_normalized = normalized
    
    logger.info(
        f"API: Request to delete memory entry ID '{memory_id}'. "
        f"Requesting user (normalized): '{requesting_user_normalized}' (Raw X-User-Id: '{requesting_user_raw}')."
    )
    # --- End User ID Normalization ---

    entry_to_delete = ethos_core.memory_storage.get_entry(memory_id)
    if not entry_to_delete:
        raise HTTPException(status_code=404, detail=f"Memory entry with ID '{memory_id}' not found.")

    # The entry_owner_id from the database metadata should already be normalized (e.g., "isaac")
    # if it was stored correctly after our previous normalization changes.
    entry_owner_id = entry_to_delete.get('metadata', {}).get('user_id') 
    
    is_admin_attempt = False
    admin_pw_cfg = Config.get_admin_password()

    if admin_pw_cfg and x_admin_password:
        if secrets.compare_digest(x_admin_password, admin_pw_cfg):
            is_admin_attempt = True
            logger.info(f"Admin authenticated for deleting memory entry '{memory_id}'.")
        else:
            logger.warning(f"Admin password provided but incorrect for deleting memory entry '{memory_id}'.")

    can_delete = False
    if is_admin_attempt:
        can_delete = True
    # Compare the NORMALIZED requesting user ID with the (expectedly normalized) owner ID from DB
    elif entry_owner_id == requesting_user_normalized and entry_to_delete.get('type') == 'user_fact':
        can_delete = True
    elif entry_to_delete.get('type') != 'user_fact':
        logger.warning(
            f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) attempted to delete non-user_fact entry '{memory_id}' without admin rights."
        )
    else: 
        logger.warning(
            f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) does not own user_fact '{memory_id}' (owner: '{entry_owner_id}')."
        )

    if not can_delete:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to delete this memory entry.")

    try:
        if ethos_core.memory_storage.delete_entry(memory_id):
            logger.info(f"Successfully deleted memory entry '{memory_id}'.")
            await ethos_core.add_memory_entry({
                "type": "system",
                "content": f"Memory entry '{memory_id}' (type: {entry_to_delete.get('type')}, owner: {entry_owner_id or 'N/A'}) deleted by '{requesting_user_normalized}' (Admin: {is_admin_attempt}). Raw request user: '{requesting_user_raw}'.",
                "metadata": {
                    "user_id": "system_admin",
                    "action": "memory_entry_delete",
                    "deleted_entry_id": memory_id,
                    "deleted_entry_type": entry_to_delete.get('type'),
                    "deleted_entry_owner": entry_owner_id,
                    "requesting_user_normalized": requesting_user_normalized,
                    "requesting_user_raw": requesting_user_raw,
                    "is_admin_action": is_admin_attempt,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }, user_id_context="system_admin")
            return JSONResponse(content={"message": f"Memory entry '{memory_id}' deleted successfully."})
        else:
            raise HTTPException(status_code=500, detail=f"Failed to delete memory entry '{memory_id}', or it was already deleted.")
    except Exception as e:
        logger.error(f"Error during deletion of memory entry '{memory_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during memory deletion: {str(e)}")

@app.get("/v1/user/facts", response_model=List[MemoryEntry], tags=["User"])
async def get_user_facts_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    raw_actual_user_id = x_user_id or "unknown_user"
    actual_user_id = raw_actual_user_id.lower().strip().replace(" ", "_") if raw_actual_user_id else "unknown_user"
    if not actual_user_id:
         actual_user_id = "unknown_user"

    if actual_user_id in ["unknown_user", "api_guest_user", "default_user"]:
        logger.info(f"Request for user facts from a generic user context ('{actual_user_id}'). Returning empty list.")
        return []

    logger.info(f"API: Request for user facts for user_id (normalized): '{actual_user_id}' (Raw was: '{raw_actual_user_id}').")
    try:
        user_facts = await ethos_core.get_all_user_facts(user_id=actual_user_id) # Pass normalized ID
        return user_facts
    except Exception as e:
        logger.error(f"API: Error fetching user facts for '{actual_user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching user facts.")

@app.get("/", include_in_schema=False)
async def get_gui_root():
    gui_html_path = WEBAPP_DIR / "gui.html"
    if gui_html_path.is_file(): return FileResponse(str(gui_html_path))
    else: return JSONResponse(content={"error": "Eidos GUI not found."}, status_code=404)

@app.get("/v1/models", response_model=ModelList)
async def list_models_endpoint():
    logger.info("Request received for /v1/models")
    model_id = Config.LLM['PATHOS']['model'] if Config.LLM and Config.LLM.get('PATHOS') and Config.LLM['PATHOS'].get('model') else 'eidos-agent'
    model_id = model_id.split('#')[0].strip() if model_id else 'eidos-agent' # Ensure model_id is not None
    eidos_model_card = ModelCard(id=model_id, owned_by="eidos-project")
    logger.info(f"Reporting model ID: {model_id}")
    return ModelList(data=[eidos_model_card])


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(fastapi_request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    # This endpoint will NOT be a StreamingResponse for the main text.
    # TTS audio chunks will be sent via WebSocket.
    global router, ethos_core, logos_core, pathos_interface, manager
    if not all([router, ethos_core, logos_core, pathos_interface, manager]):
        raise HTTPException(status_code=503, detail="Eidos system core components not fully ready.")

    request_id = str(uuid.uuid4())
    logger.critical(f">>> Request {request_id}: chat_completions ENTERED <<<")
    logger.info(f"Request {request_id}: X-User-Id Header: '{x_user_id}'")

    try:
        body = await fastapi_request.json()
    except json.JSONDecodeError:
        logger.error(f"Request {request_id}: Invalid JSON body.")
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    try:
        # Validate against Pydantic model
        parsed_request = ChatCompletionRequest(**body)
        if parsed_request.stream:
            # While we are streaming TTS audio via WebSocket, the main HTTP response for text is not streamed.
            # Client might still send stream=true if it's a generic OpenAI client.
            # We can choose to ignore it or return an error if we don't support HTTP streaming for text.
            logger.warning(f"Request {request_id}: Client requested streaming (stream=true), "
                           f"but this endpoint returns full text. TTS audio is streamed via WebSocket if enabled.")
            # For now, we'll proceed and return a non-streamed text response.
            # If strict OpenAI compatibility for text streaming is needed, this would change.
    except ValidationError as pydantic_exc:
        logger.error(f"Request {request_id}: Pydantic validation error: {pydantic_exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid request body: {pydantic_exc}")

    # Use the modified extract_input_to_eidos_format
    input_data = extract_input_to_eidos_format(body, request_id, user_id_from_header=x_user_id)

    try:
        logger.info(f"Request {request_id}: Calling router.route_input (User ID: {input_data['metadata']['user_id']}). "
                    f"ForceSearchFlag: {input_data['metadata'].get('force_web_search_requested')}, "
                    f"TTS Enabled for Resp: {input_data['metadata'].get('auto_tts_enabled_for_response')}")
        
        result: RoutingResult = await router.route_input(input_data)
        
        logger.info(f"Request {request_id}: router.route_input success: {result.success}")
        router_metadata = result.metadata or {}
        final_response_content = result.content

        # --- Construct ChatCompletionResponse (as before) ---
        message_metadata_keys = ["mood_at_response", "active_user_id_for_turn", "hexus_scores", "vision_llm_output", "retrieved_memory_ids", "tool_calls_from_pathos", "engaged_proactive_id", "forced_action", "tts_stream_attempted"]
        message_metadata = {k: router_metadata.get(k) for k in message_metadata_keys if router_metadata.get(k) is not None}
        
        usage_data_keys = ["prompt_tokens_from_llm", "completion_tokens_from_llm", "estimated_prompt_tokens"]
        usage_data_from_router = {k.replace("_from_llm",""): router_metadata.get(k) for k in usage_data_keys if router_metadata.get(k) is not None}
        if 'prompt_tokens' in usage_data_from_router and 'completion_tokens' in usage_data_from_router:
            usage_data_from_router['total_tokens'] = usage_data_from_router['prompt_tokens'] + usage_data_from_router['completion_tokens']
        
        usage_data = ChatCompletionUsage(**usage_data_from_router) if any(v is not None for v in usage_data_from_router.values()) else None
        
        final_tool_calls = message_metadata.get("tool_calls_from_pathos") # This comes from PathosInterface metadata
        response_message = ChatMessage(
            role="assistant",
            content=final_response_content,
            tool_calls=final_tool_calls, # Pass tool_calls if any
            metadata=message_metadata if message_metadata else None
        )
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "null"] = "tool_calls" if final_tool_calls else "stop"
        choice = ChatCompletionChoice(index=0, message=response_message, finish_reason=finish_reason)
        
        final_model_name_for_response = (body.get("model", 'eidos-agent').split('#')[0].strip() if body.get("model") else 'eidos-agent')

        api_response = ChatCompletionResponse(
            id=f"chatcmpl-{request_id}",
            object="chat.completion", # Not chat.completion.chunk
            created=int(datetime.now(timezone.utc).timestamp()),
            model=final_model_name_for_response,
            choices=[choice],
            usage=usage_data
        )
        logger.critical(f"<<< Request {request_id}: chat_completions EXITING (sending full text response) <<<")
        return api_response

    except HTTPException as http_exc:
        logger.error(f"!!! Request {request_id}: HTTPException during routing/response generation: {http_exc.detail}", exc_info=False)
        raise http_exc
    except Exception as e:
        logger.error(f"!!! Request {request_id}: Unhandled API exception in chat_completions: {e}", exc_info=True)
        # Ensure a valid JSON error response
        return JSONResponse(
            status_code=500,
            content={"error": {"message": f"Internal Server Error: {str(e)}", "type": "internal_error", "code": "internal_server_error"}}
        )

# --- NEW: Endpoint to serve cached TTS audio chunks ---
@app.get("/v1/tts/audio_chunk/{chunk_id}")
async def get_tts_audio_chunk(chunk_id: str):
    global TEMP_AUDIO_CACHE
    logger.debug(f"Request received for TTS audio chunk ID: {chunk_id}")
    # Optional: Use lock if modifying cache concurrently, though get is usually safe.
    # async with TEMP_AUDIO_CACHE_LOCK:
    # audio_bytes = TEMP_AUDIO_CACHE.get(chunk_id)
    # For simplicity, direct access if main event loop handles it:
    audio_bytes = TEMP_AUDIO_CACHE.pop(chunk_id, None) # Pop to remove after first fetch (single use)

    if audio_bytes:
        logger.info(f"Serving TTS audio chunk ID: {chunk_id}, Length: {len(audio_bytes)} bytes.")
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
    else:
        logger.warning(f"TTS audio chunk ID: {chunk_id} not found in cache or already served.")
        raise HTTPException(status_code=404, detail="Audio chunk not found or already served.")

@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(fastapi_request: Request, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global router, ethos_core, logos_core, pathos_interface, manager
    if not all([router, ethos_core, logos_core, pathos_interface, manager]): raise HTTPException(status_code=503, detail="Eidos system core components not fully ready.")
    request_id = str(uuid.uuid4()); logger.critical(f">>> Request {request_id}: chat_completions ENTERED <<<"); logger.info(f"Request {request_id}: X-User-Id Header: '{x_user_id}'")
    try: body = await fastapi_request.json()
    except json.JSONDecodeError: logger.error(f"Request {request_id}: Invalid JSON body."); raise HTTPException(status_code=400, detail="Invalid JSON body.")
    try:
        parsed_request = ChatCompletionRequest(**body)
        if parsed_request.stream: logger.warning(f"Request {request_id}: Streaming requested but not implemented."); return JSONResponse(status_code=501, content={"error": {"message": "Streaming is not implemented...", "type": "unimplemented_feature", "code": "streaming_not_implemented"}})
        logger.info(f"Request {request_id}: Validated request. Model='{parsed_request.model}', Messages={len(parsed_request.messages)}")
    except Exception as pydantic_exc: logger.error(f"Request {request_id}: Pydantic validation error: {pydantic_exc}", exc_info=True); raise HTTPException(status_code=400, detail=f"Invalid request body: {pydantic_exc}")

    input_data = extract_input_to_eidos_format(body, request_id, user_id_from_header=x_user_id)
    try:
        logger.info(f"Request {request_id}: Calling router.route_input (User ID: {input_data['metadata']['user_id']}). ForceSearchFlag: {input_data['metadata'].get('force_web_search_requested')}")
        result: RoutingResult = await router.route_input(input_data)
        logger.info(f"Request {request_id}: router.route_input success: {result.success}"); router_metadata = result.metadata or {}; final_response_content = result.content
        message_metadata_keys = ["mood_at_response", "active_user_id_for_turn", "hexus_scores", "vision_llm_output", "retrieved_memory_ids", "tool_calls_from_pathos", "engaged_proactive_id", "forced_action"]
        message_metadata = {k: router_metadata.get(k) for k in message_metadata_keys if router_metadata.get(k) is not None}
        usage_data_keys = ["prompt_tokens_from_llm", "completion_tokens_from_llm", "estimated_prompt_tokens"]
        usage_data_from_router = {k.replace("_from_llm",""): router_metadata.get(k) for k in usage_data_keys if router_metadata.get(k) is not None}
        if 'prompt_tokens' in usage_data_from_router and 'completion_tokens' in usage_data_from_router: usage_data_from_router['total_tokens'] = usage_data_from_router['prompt_tokens'] + usage_data_from_router['completion_tokens']
        usage_data = ChatCompletionUsage(**usage_data_from_router) if any(v is not None for v in usage_data_from_router.values()) else None
        final_message_content_for_api = final_response_content; final_tool_calls = message_metadata.get("tool_calls_from_pathos")
        response_message = ChatMessage(role="assistant", content=final_message_content_for_api, tool_calls=final_tool_calls, metadata=message_metadata if message_metadata else None)
        finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "null"] = "tool_calls" if final_tool_calls else "stop"
        choice = ChatCompletionChoice(index=0, message=response_message, finish_reason=finish_reason)
        final_model_name_for_response = (body.get("model", 'eidos-agent').split('#')[0].strip() if body.get("model") else 'eidos-agent')
        api_response = ChatCompletionResponse(id=f"chatcmpl-{request_id}", object="chat.completion", created=int(datetime.now(timezone.utc).timestamp()), model=final_model_name_for_response, choices=[choice], usage=usage_data)
        logger.critical(f"<<< Request {request_id}: chat_completions EXITING (sending response) <<<"); return api_response
    except HTTPException as http_exc: logger.error(f"!!! Request {request_id}: HTTPException: {http_exc.detail}", exc_info=False); raise http_exc
    except Exception as e: logger.error(f"!!! Request {request_id}: Unhandled API exception: {e}", exc_info=True); return JSONResponse(status_code=500, content={"error": {"message": f"Internal Server Error: {str(e)}", "type": "internal_error", "code": "internal_server_error"}})


@app.get("/v1/weather", status_code=200)
async def get_weather_endpoint(location: str, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global logos_core;
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
    raw_user_id_from_payload = settings_request.user_id
    raw_user_id_from_header = x_user_id_header
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
            fact_result_str = await logos_core.execute_store_user_fact(
                attribute_name=item.attribute_name, attribute_value=str(item.attribute_value),
                user_statement_context=item.user_statement_context or f"User set {item.attribute_name} via GUI settings.",
                user_id=user_id_for_storage # Use normalized ID
            )
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

VALID_PITCH_SPEED_VALUES_FOR_API = ["very_low", "low", "moderate", "high", "very_high"]
VALID_GENDER_VALUES_FOR_API = ["female", "male"]

class TTSRequest(BaseModel):
    text: str
    gender: Optional[str] = None # e.g., "female", "male"
    pitch: Optional[str] = None  # e.g., "moderate", "high"
    speed: Optional[str] = None  # e.g., "moderate", "high"

@app.post("/v1/tts/synthesize", tags=["TTS"])
async def synthesize_speech(request_data: TTSRequest): # Assuming TTSRequest Pydantic model
    global eidos_tts_service_instance
    if not eidos_tts_service_instance or not eidos_tts_service_instance.is_available():
        raise HTTPException(status_code=503, detail="TTS service is not available or not configured.")
    # ... (input validation for gender, pitch, speed as before) ...
    # Validate inputs if they are provided
    if request_data.gender is not None and request_data.gender.lower() not in VALID_GENDER_VALUES_FOR_API: # VALID_... constants from main.py or config
        raise HTTPException(status_code=422, detail=f"Invalid gender. Choose from {VALID_GENDER_VALUES_FOR_API}")
    if request_data.pitch is not None and request_data.pitch.lower() not in VALID_PITCH_SPEED_VALUES_FOR_API:
        raise HTTPException(status_code=422, detail=f"Invalid pitch. Choose from {VALID_PITCH_SPEED_VALUES_FOR_API}")
    if request_data.speed is not None and request_data.speed.lower() not in VALID_PITCH_SPEED_VALUES_FOR_API:
        raise HTTPException(status_code=422, detail=f"Invalid speed. Choose from {VALID_PITCH_SPEED_VALUES_FOR_API}")

    logger.info(f"Eidos TTS API: Synthesis request for text: '{request_data.text[:50]}...' G:{request_data.gender} P:{request_data.pitch} S:{request_data.speed}")
    try:
        audio_bytes = await eidos_tts_service_instance.synthesize(
            text=request_data.text,
            gender_override=request_data.gender.lower() if request_data.gender else None,
            pitch_override=request_data.pitch.lower() if request_data.pitch else None,
            speed_override=request_data.speed.lower() if request_data.speed else None
        )
        if audio_bytes:
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
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
    try: file_content = await file.read();
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

# --- Agent Specific Endpoints ---
@app.get("/v1/agent/dreams", response_model=List[DreamEntryResponse])
async def get_agent_dreams(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: 
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")
    
    logger.info(f"API: Request for /v1/agent/dreams. User: {x_user_id}, Limit: {limit}")
    
    try:
        # Get raw dream entries (which are 'queued_discussion_point' with specific metadata)
        # EthosCore's get_recent_dreams should handle filtering by user_id_context appropriately
        raw_dreams = await ethos_core.get_recent_dreams(user_id_context=x_user_id, limit=limit)
        
        response_dreams: List[DreamEntryResponse] = []
        for entry in raw_dreams:
            img_url = None
            metadata = entry.get('metadata', {})
            local_img_path_str = metadata.get('dream_image_path')

            if local_img_path_str:
                try:
                    # Ensure the path is valid and construct the web-accessible URL
                    img_filename = Path(local_img_path_str).name
                    # This assumes your /dream_images static mount is working correctly
                    img_url = f"/dream_images/{img_filename}" 
                except Exception as e_path:
                    logger.error(f"Error constructing image URL from dream_image_path '{local_img_path_str}': {e_path}")
            
            response_dreams.append(
                DreamEntryResponse(
                    id=entry.get('id', str(uuid.uuid4())), # Provide a fallback ID if missing
                    timestamp=entry.get('timestamp', datetime.now(timezone.utc).isoformat()), # Fallback timestamp
                    content=entry.get('content', '[No dream content]'),
                    dream_image_url=img_url,
                    dream_seed_summary=metadata.get('dream_seed_summary')
                )
            )
        return response_dreams
    except Exception as e:
        logger.error(f"API: Error fetching agent dreams: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching agent dreams.")

@app.get("/v1/agent/learnings", response_model=List[MemoryEntry])
async def get_agent_learnings(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core:
        raise HTTPException(status_code=503, detail="Eidos system not ready.")
    
    user_id_filter = x_user_id
    logger.info(f"Request for /v1/agent/learnings. User: {user_id_filter}, Limit: {limit}")

    try:
        learning_types = ["learned_correction", "learned_feedback_insight", "suggestion_reflection"]
        learnings = await ethos_core.get_recent_learnings(
            learning_types=learning_types,
            user_id_context=user_id_filter,
            limit=limit
        )

        # ✅ Validate entries without using isinstance
        for i, entry in enumerate(learnings):
            try:
                entry_dict = dict(entry)
                MemoryEntry(**entry_dict)
            except ValidationError as e:
                logger.error(f"\n❌ MemoryEntry validation failed at index {i}:\n{e.json(indent=2)}\nEntry data:\n{entry_dict}\n")

        return JSONResponse(content=jsonable_encoder(learnings))

    except Exception as e:
        logger.error(f"Error fetching agent learnings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching agent learnings.")
    
@app.get("/v1/agent/knowledge_verifications", response_model=List[MemoryEntry])
async def get_agent_knowledge_verifications(limit: int = 20, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    global ethos_core
    if not ethos_core: raise HTTPException(status_code=503, detail="Eidos system not ready.")
    logger.info(f"Request for /v1/agent/knowledge_verifications. User: {x_user_id}, Limit: {limit}")
    try:
        if limit <= 0: limit = 20
        verifications = await ethos_core.get_recent_knowledge_verifications(limit=limit)
        return verifications
    except Exception as e: logger.error(f"Error fetching agent knowledge verifications: {e}", exc_info=True); raise HTTPException(status_code=500, detail="Internal server error fetching agent knowledge verifications.")

# --- WebSocket Endpoint (ensure user_id normalization) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id = None
    connection_ok = False

    try:
        while True:
            data = await websocket.receive_json()
            logger.debug(f"WS received: {data}")

            if data.get("type") == "auth" and data.get("payload", {}).get("userId"):
                raw_temp_uid = data["payload"]["userId"]
                temp_uid = raw_temp_uid.lower().strip().replace(" ", "_") if isinstance(raw_temp_uid, str) and raw_temp_uid else None

                if not temp_uid: 
                    logger.warning(f"WS: Invalid user_id '{raw_temp_uid}'. Closing.")
                    break
                user_id = temp_uid 
                if await manager.connect(websocket, user_id):
                    connection_ok = True
                    logger.info(f"WS connected for user: {user_id}")
                    await manager.send_personal_message({
                        "type": "status",
                        "payload": {"message": "Connected to Eidos WS."}
                    }, user_id)
                else:
                    logger.error(f"WS: ConnectionManager failed for user {user_id}. Closing.")
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": "Failed to register."}
                    })
                    await websocket.close(code=1011)
                    break

            elif user_id is None:
                logger.warning("WS: Message before auth. Closing.")
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": "Auth required."}
                })
                await websocket.close(code=1008)
                break

            else:
                logger.warning(f"WS: Unhandled message type '{data.get('type')}' from user {user_id}.")

    except WebSocketDisconnect:
        logger.info(f"WS: Disconnected user: {user_id if user_id else 'unauthenticated'}.")

    except Exception as e:
        logger.error(f"WS: Error for user {user_id if user_id else 'unknown'}: {e}", exc_info=True)
        try:
            if websocket.client_state == websocket.client_state.CONNECTED:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": f"Error: {str(e)}"}
                })
        except Exception as e_send:
            logger.error(f"WS: Could not send error to user {user_id if user_id else 'unknown'}: {e_send}")
        try:
            if websocket.client_state != websocket.client_state.DISCONNECTED:
                await websocket.close(code=1011)
        except Exception as e_close:
            logger.error(f"WS: Error during forced close for user {user_id if user_id else 'unknown'}: {e_close}")

    finally:
        if user_id and connection_ok:
            manager.disconnect(websocket, user_id)
            logger.info(f"WS: Ensured user {user_id} disconnected from ConnectionManager.")
        elif user_id:
            logger.info(f"WS: User {user_id} (not fully registered) closing.")
        else:
            logger.info("WS: Unauthenticated client closing.")

if __name__ == "__main__":
    try:
        api_cfg = Config.get_api_config()
        host = api_cfg.get('host','0.0.0.0')
        port = api_cfg.get('port',8088)
        uvicorn_log_level = api_cfg.get('log_level','info').lower()

        print(f"--- Starting Eidos API Server (main.py) ---")
        print(f"Serving WebApp from: {WEBAPP_DIR.resolve()}")
        print(f"Access GUI at: http://{host}:{port}/")
        print(f"Uvicorn Log Level: {uvicorn_log_level}")
        eidos_app_log_level = Config.API.get('log_level', 'info').upper() if Config.API else 'INFO'
        print(f"Eidos App Log Level (from API_LOG_LEVEL in .env): {eidos_app_log_level}")
        print("-" * 30)
        print("Open WebUI (or other client) Config:")
        print(f"  API Base URL: http://{host}:{port}/v1")
        print(f"  API Key: (Leave empty or use any string)")
        pathos_model_name = 'eidos-agent'
        if Config.LLM and Config.LLM.get('PATHOS') and Config.LLM['PATHOS'].get('model'):
            pathos_model_name = Config.LLM['PATHOS']['model'].split('#')[0].strip() if Config.LLM['PATHOS']['model'] else 'eidos-agent'
        print(f"  Model Selection: Choose '{pathos_model_name}' (or the one you set in your client)")
        print("-" * 30)
        print(f"Feedback Endpoint:        POST http://{host}:{port}/v1/feedback")
        print(f"Document Upload Endpoint:   POST http://{host}:{port}/v1/documents/upload")
        print(f"Clear Memory Endpoint:      POST http://{host}:{port}/v1/memory/clear (Requires X-Admin-Password header)")
        print(f"Clear User Memory Endpoint: POST http://{host}:{port}/v1/memory/clear_user")
        print(f"Agent Learnings Endpoint:   GET  http://{host}:{port}/v1/agent/learnings")
        print(f"Agent Dreams Endpoint:      GET  http://{host}:{port}/v1/agent/dreams")
        print(f"Knowledge Log Endpoint:     GET  http://{host}:{port}/v1/agent/knowledge_verifications")
        print(f"Dream Images Served At:        http://{host}:{port}/dream_images/<filename.png>")
        print(f"Health Check Endpoint:      GET  http://{host}:{port}/health")
        print(f"WebSocket Endpoint:         ws://{host}:{port}/ws")
        print(f"User Settings Endpoint:     POST http://{host}:{port}/v1/user/settings")
        print(f"Daily Briefing Endpoint:    GET  http://{host}:{port}/v1/briefing")
        print(f"Weather Endpoint:           GET  http://{host}:{port}/v1/weather")
        print("-" * 30)

        uvicorn.run("main:app", host=host, port=port, log_level=uvicorn_log_level, reload=False)
    except Exception as e_main:
        log_func = logger.critical if logger and getattr(logger, 'handlers', None) else lambda msg, exc_info=False: print(f"CRITICAL STARTUP ERROR: {msg}", file=sys.stderr)
        if isinstance(e_main, (KeyError, ValueError)) and "Config" in str(e_main): log_func(f"Configuration error: {e_main}. Check .env or config.py.", exc_info=True)
        elif isinstance(e_main, ImportError): log_func(f"Import error: {e_main}. Check requirements.txt.", exc_info=True)
        elif isinstance(e_main, RuntimeError) and "Eidos system failed to initialize" in str(e_main): print(f"CRITICAL: Eidos system failed to initialize. Check logs. Error: {e_main}", file=sys.stderr)
        else: log_func(f"Failed to start Eidos API server: {e_main}", exc_info=True)
        sys.exit(1)