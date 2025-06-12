import logging
import uuid
import json
import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Header, Path as FastApiPath
from fastapi.responses import JSONResponse

from eidos_agent.schemas import ClearUserMemoryRequest, ApiMemoryEntry
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct from previous step, ensuring it stays
from eidos_agent.core.config import Config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/memory", tags=["Memory Management"])

_ethos_core: Optional[EthosCore] = None
_config: Optional[Config] = None

def init_memory_management_router(
    ethos: EthosCore,
    config_instance: Config
):
    global _ethos_core, _config
    _ethos_core = ethos
    _config = config_instance
    logger.info("Memory Management Router initialized with Eidos core components.")

@router.post("/clear", status_code=200)
async def clear_eidos_memory(x_user_id: Optional[str] = Header(None, alias="X-User-Id"), x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")): # pragma: no cover
    if not _ethos_core or not _config:
        logger.error("Memory Management Router: EthosCore or Config not initialized for /clear.")
        raise HTTPException(status_code=503, detail="Eidos system (core memory components) not ready.")

    admin_pw_cfg = _config.get_admin_password()
    if admin_pw_cfg:
        if not x_admin_password:
            logger.warning(f"Clear all memory attempt by '{x_user_id or 'unknown'}' - no admin password provided.")
            raise HTTPException(status_code=401, detail="Unauthorized: Admin password required.")
        if not secrets.compare_digest(x_admin_password, admin_pw_cfg):
            logger.warning(f"Clear all memory attempt by '{x_user_id or 'unknown'}' - incorrect admin password.")
            raise HTTPException(status_code=403, detail="Forbidden: Incorrect admin password.")
    else: # pragma: no cover
        logger.warning("Executing clear all Eidos memory without password protection (EIDOS_ADMIN_PASSWORD not set). This is a security risk.")

    logger.warning(f"API request to clear all Eidos memory from '{x_user_id or 'unknown'}' (Authenticated if password was required).")
    try:
        if await _ethos_core.memory_storage.clear_all_memory(): # Assuming clear_all_memory might become async
             if x_user_id: # Log who initiated it
                 await _ethos_core.add_memory_entry({
                     "type": "system",
                     "content": f"User '{x_user_id}' initiated full Eidos memory clear via API.",
                     "metadata": {
                         "user_id": "system_admin", # Logged as system_admin action
                         "initiating_user_id": x_user_id,
                         "action": "memory_clear_all",
                         "timestamp": datetime.now(timezone.utc).isoformat()
                     }
                 }, user_id_context="system_admin")
             return JSONResponse(content={"message": "Eidos memory cleared successfully."})
        else: # pragma: no cover
            logger.error("Memory storage clear_all_memory returned false.")
            raise HTTPException(status_code=500, detail="Failed to clear memory in storage.")
    except Exception as e: # pragma: no cover
        logger.error(f"Error during clear_all_memory(): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during memory clearing.")

@router.post("/clear_user", status_code=200)
async def clear_user_memory(request_data: ClearUserMemoryRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")):
    if not _ethos_core:
        logger.error("Memory Management Router: EthosCore not initialized for /clear_user.")
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    user_to_clear = request_data.user_id
    requesting_user = x_user_id_header or "unknown_api_caller" # User from header is the one making the request

    logger.warning(f"API request to clear memory for user_id '{user_to_clear}' from requesting_user '{requesting_user}'.")

    if not user_to_clear:
        raise HTTPException(status_code=400, detail="Target 'user_id' must be provided in the request body.")

    try:
        success = await _ethos_core.clear_memory_for_user(user_to_clear)
        if success:
            await _ethos_core.add_memory_entry({
                "type": "system",
                "content": f"Memory for user '{user_to_clear}' cleared by '{requesting_user}' via API.",
                "metadata": {
                    "user_id": "system_admin", # Logged as system_admin action
                    "action": "user_memory_clear",
                    "target_user_id": user_to_clear,
                    "requesting_user_id": requesting_user,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }, user_id_context="system_admin")
            return JSONResponse(content={"message": f"Memory for user '{user_to_clear}' cleared successfully."})
        else: # pragma: no cover
            logger.error(f"clear_memory_for_user returned false for user_id '{user_to_clear}'.")
            raise HTTPException(status_code=500, detail=f"Failed to clear memory for user '{user_to_clear}'.")
    except Exception as e: # pragma: no cover
        logger.error(f"Error during clear_memory_for_user (user: '{user_to_clear}'): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/entry/{memory_id}", status_code=200) # Removed tags, as it's on the router
async def delete_memory_entry_endpoint(
    memory_id: str = FastApiPath(..., title="The ID of the memory entry to delete", min_length=36, max_length=36), # Ensure FastApiPath is imported
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")
):
    if not _ethos_core or not _config:
        logger.error("Memory Management Router: EthosCore or Config not initialized for /entry/{memory_id} delete.")
        raise HTTPException(status_code=503, detail="Eidos system (core memory components) not ready.")

    requesting_user_raw: Optional[str] = x_user_id
    requesting_user_normalized: str = "unknown_api_caller" # Default
    if requesting_user_raw and isinstance(requesting_user_raw, str):
        normalized = requesting_user_raw.lower().strip().replace(" ", "_")
        if normalized:
            requesting_user_normalized = normalized

    logger.info(f"API: Request to delete memory entry ID '{memory_id}'. Requesting user (normalized): '{requesting_user_normalized}' (Raw X-User-Id: '{requesting_user_raw}').")

    entry_to_delete = await _ethos_core.memory_storage.get_entry(memory_id) # Assuming get_entry might be async
    if not entry_to_delete:
        raise HTTPException(status_code=404, detail=f"Memory entry with ID '{memory_id}' not found.")

    entry_owner_id = entry_to_delete.get('metadata', {}).get('user_id')

    is_admin_action = False
    admin_pw_cfg = _config.get_admin_password()
    if admin_pw_cfg and x_admin_password:
        if secrets.compare_digest(x_admin_password, admin_pw_cfg):
            is_admin_action = True
            logger.info(f"Admin privileges confirmed for deleting memory entry '{memory_id}' by user '{requesting_user_normalized}'.")
        else: # pragma: no cover
            logger.warning(f"Admin password provided but incorrect for deleting memory entry '{memory_id}' by user '{requesting_user_normalized}'.")
            # Do not immediately deny; let ownership check proceed. If admin intended, this is a failed admin attempt.

    can_delete = False
    if is_admin_action:
        can_delete = True
    elif entry_owner_id == requesting_user_normalized and entry_to_delete.get('type') == 'user_fact':
        can_delete = True # User can delete their own user_facts
    # Add other specific conditions for deletion if necessary, e.g. system can delete anything, specific roles, etc.
    elif entry_to_delete.get('type') != 'user_fact' and not is_admin_action: # pragma: no cover
         logger.warning(f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) attempted to delete non-user_fact entry '{memory_id}' (type: {entry_to_delete.get('type')}, owner: {entry_owner_id}) without admin rights.")
    elif entry_owner_id != requesting_user_normalized and not is_admin_action: # pragma: no cover
        logger.warning(f"User '{requesting_user_normalized}' (Raw: {requesting_user_raw}) does not own entry '{memory_id}' (owner: '{entry_owner_id}') and is not admin.")

    if not can_delete:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to delete this memory entry.")

    try:
        if await _ethos_core.memory_storage.delete_entry(memory_id): # Assuming delete_entry might be async
            logger.info(f"Successfully deleted memory entry '{memory_id}' by user '{requesting_user_normalized}' (Admin: {is_admin_action}).")
            await _ethos_core.add_memory_entry({
                "type": "system",
                "content": f"Memory entry '{memory_id}' (type: {entry_to_delete.get('type')}, owner: {entry_owner_id or 'N/A'}) deleted by '{requesting_user_normalized}' (Admin: {is_admin_action}). Raw request user: '{requesting_user_raw}'.",
                "metadata": {
                    "user_id": "system_admin",
                    "action": "memory_entry_delete",
                    "deleted_entry_id": memory_id,
                    "deleted_entry_type": entry_to_delete.get('type'),
                    "deleted_entry_owner": entry_owner_id,
                    "requesting_user_normalized": requesting_user_normalized,
                    "requesting_user_raw": requesting_user_raw,
                    "is_admin_action": is_admin_action,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }, user_id_context="system_admin")
            return JSONResponse(content={"message": f"Memory entry '{memory_id}' deleted successfully."})
        else: # pragma: no cover
            # This case might occur if the entry was deleted between the get_entry and delete_entry calls (race condition)
            logger.warning(f"Failed to delete memory entry '{memory_id}', or it was already deleted before this operation.")
            raise HTTPException(status_code=404, detail=f"Failed to delete memory entry '{memory_id}', possibly already deleted.")
    except Exception as e: # pragma: no cover
        logger.error(f"Error during deletion of memory entry '{memory_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during memory deletion: {str(e)}")
