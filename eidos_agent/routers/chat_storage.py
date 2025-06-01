from fastapi import APIRouter, HTTPException, Header
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone # Import timezone
import uuid
import json # For loading/dumping content if stored as JSON string in memory
from pydantic import ValidationError

from ..utils.logger import get_logger
from ..models.chat_storage import ChatState, ChatMessage # Import from the models file
from ..core.config import Config # Not directly used here, but good for context
from ..modules.ethos_core.core import EthosCore

logger = get_logger(__name__)

router = APIRouter()
ethos_core_instance: Optional[EthosCore] = None # Will be set during app startup

def init_router(_ethos_core: EthosCore):
    global ethos_core_instance
    ethos_core_instance = _ethos_core
    logger.info("Chat Storage Router initialized with EthosCore instance.")

@router.post("/chat/current", response_model=ChatState, status_code=200)
async def save_current_chat(
    chat: ChatState,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> ChatState:
    """Save the current active chat state."""
    if not ethos_core_instance or not ethos_core_instance.memory_storage:
        logger.error("Chat storage (EthosCore/MemoryStorage) not available for save_current_chat.")
        raise HTTPException(status_code=503, detail="Chat storage system not available")

    user_id_to_use = x_user_id or chat.userId
    if not user_id_to_use or not user_id_to_use.strip():
        logger.warning("User ID missing in save_current_chat.")
        raise HTTPException(status_code=400, detail="User ID required")
    
    # Ensure chat.userId is consistent if x_user_id is provided and different
    if x_user_id and x_user_id != chat.userId:
        logger.warning(f"User ID mismatch in save_current_chat. Header: '{x_user_id}', Chat: '{chat.userId}'. Using header ID.")
        chat.userId = x_user_id # Prioritize header if different

    try:
        chat.timestamp = datetime.now(timezone.utc) # Ensure UTC timestamp
        chat.isArchived = False
        
        chat_dict = chat.model_dump(mode='json') # Use model_dump for Pydantic v2
        
        key = f"chat:current:{chat.userId}"
        await ethos_core_instance.memory_storage.set(key, chat_dict) # set expects dict or serializable
        logger.info(f"Saved current chat for user '{chat.userId}' with ID '{chat.id}'.")
        return chat
    except Exception as e:
        logger.error(f"Error saving current chat for user '{chat.userId}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error saving chat data: {str(e)}")

@router.get("/chat/current", response_model=Optional[ChatState], status_code=200)
async def get_current_chat(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> Optional[ChatState]:
    """Get the current active chat state."""
    if not ethos_core_instance or not ethos_core_instance.memory_storage:
        logger.error("Chat storage (EthosCore/MemoryStorage) not available for get_current_chat.")
        raise HTTPException(status_code=503, detail="Chat storage system not available")
    
    if not x_user_id or not x_user_id.strip():
        logger.warning("User ID missing in get_current_chat.")
        raise HTTPException(status_code=400, detail="User ID required")
    
    try:
        key = f"chat:current:{x_user_id}"
        chat_data = await ethos_core_instance.memory_storage.get(key)
        
        if not chat_data:
            logger.debug(f"No current chat found for user '{x_user_id}'.")
            return None
            
        if not isinstance(chat_data, dict):
            logger.error(f"Invalid chat data type for user '{x_user_id}': {type(chat_data)}. Expected dict.")
            # Attempt to parse if it's a JSON string
            if isinstance(chat_data, str):
                try:
                    chat_data = json.loads(chat_data)
                    if not isinstance(chat_data, dict):
                        raise HTTPException(status_code=500, detail="Stored chat data is not a valid JSON object.")
                except json.JSONDecodeError:
                    raise HTTPException(status_code=500, detail="Stored chat data is not valid JSON.")
            else:
                raise HTTPException(status_code=500, detail="Invalid chat data format in storage.")
        
        try:
            chat_state = ChatState(**chat_data)
            if not chat_state.id: chat_state.id = str(uuid.uuid4())
            if not chat_state.userId: chat_state.userId = x_user_id
            if not chat_state.timestamp: chat_state.timestamp = datetime.now(timezone.utc)
            if chat_state.conversation is None: chat_state.conversation = []
            
            logger.info(f"Retrieved current chat for user '{x_user_id}' with ID '{chat_state.id}'.")
            return chat_state
            
        except ValidationError as validation_error:
            logger.error(f"Chat data validation failed for user '{x_user_id}': {validation_error.errors()}", exc_info=True)
            logger.debug(f"Invalid chat data from storage: {chat_data}")
            raise HTTPException(status_code=500, detail="Chat data failed validation upon retrieval.")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving current chat for user '{x_user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error retrieving chat data: {str(e)}")

@router.post("/chat/archive", response_model=ChatState, status_code=200)
async def archive_chat(
    chat: ChatState,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> ChatState:
    """Archive a chat to history. Implements upsert logic."""
    if not ethos_core_instance or not ethos_core_instance.memory_storage:
        logger.error("Chat storage (EthosCore/MemoryStorage) not available for archive_chat.")
        raise HTTPException(status_code=503, detail="Chat storage system not available")

    user_id_to_use = x_user_id or chat.userId
    if not user_id_to_use or not user_id_to_use.strip():
        logger.warning("User ID missing in archive_chat.")
        raise HTTPException(status_code=400, detail="User ID required")

    if x_user_id and x_user_id != chat.userId:
        logger.warning(f"User ID mismatch in archive_chat. Header: '{x_user_id}', Chat: '{chat.userId}'. Using header ID.")
        chat.userId = x_user_id

    try:
        chat.timestamp = datetime.now(timezone.utc)
        chat.isArchived = True
        
        chat_dict = chat.model_dump(mode='json')
        
        history_key = f"chat:history:{chat.userId}:{chat.id}"
        index_key = f"chat:history:index:{chat.userId}"
        
        history_index_raw = await ethos_core_instance.memory_storage.get(index_key)
        history_index: List[str] = []
        if isinstance(history_index_raw, list) and all(isinstance(item, str) for item in history_index_raw):
            history_index = history_index_raw
        elif history_index_raw is not None: # If it exists but is not a list of strings
            logger.warning(f"Corrupted history index for user '{chat.userId}'. Resetting. Data: {history_index_raw}")
            history_index = []

        if chat.id in history_index: history_index.remove(chat.id)
        history_index.insert(0, chat.id)
        
        max_history_items = Config.get_nested_value(Config.ETHOS, ['chat_history_max_items'], 50) # Example config path
        if len(history_index) > max_history_items:
            ids_to_remove = history_index[max_history_items:]
            history_index = history_index[:max_history_items]
            for old_id in ids_to_remove:
                if old_id != chat.id: # Don't delete the one we are currently archiving
                    await ethos_core_instance.memory_storage.delete(f"chat:history:{chat.userId}:{old_id}")
        
        await ethos_core_instance.memory_storage.set(history_key, chat_dict)
        await ethos_core_instance.memory_storage.set(index_key, history_index)
        
        logger.info(f"Archived chat ID '{chat.id}' for user '{chat.userId}'. History index size: {len(history_index)}.")
        return chat
    except Exception as e:
        logger.error(f"Error archiving chat for user '{chat.userId}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error archiving chat: {str(e)}")

@router.get("/chat/history", response_model=List[ChatState], status_code=200)
async def get_chat_history(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
) -> List[ChatState]:
    """Get the user's chat history."""
    if not ethos_core_instance or not ethos_core_instance.memory_storage:
        logger.error("Chat storage (EthosCore/MemoryStorage) not available for get_chat_history.")
        raise HTTPException(status_code=503, detail="Chat storage system not available")
        
    if not x_user_id or not x_user_id.strip():
        logger.warning("User ID missing in get_chat_history.")
        raise HTTPException(status_code=400, detail="User ID required")
    
    try:
        index_key = f"chat:history:index:{x_user_id}"
        history_index_raw = await ethos_core_instance.memory_storage.get(index_key)
        history_index: List[str] = []
        if isinstance(history_index_raw, list) and all(isinstance(item, str) for item in history_index_raw):
            history_index = history_index_raw
        elif history_index_raw is not None:
            logger.warning(f"Corrupted history index for user '{x_user_id}'. Returning empty. Data: {history_index_raw}")
            history_index = []
            
        history: List[ChatState] = []
        for chat_id in history_index:
            try:
                key = f"chat:history:{x_user_id}:{chat_id}"
                chat_data = await ethos_core_instance.memory_storage.get(key)
                if chat_data and isinstance(chat_data, dict):
                    chat_state = ChatState(**chat_data)
                    if not chat_state.timestamp: chat_state.timestamp = datetime.now(timezone.utc) # Fallback
                    history.append(chat_state)
                elif chat_data:
                    logger.warning(f"Skipping chat ID '{chat_id}' for user '{x_user_id}' due to invalid data format: {type(chat_data)}")
            except ValidationError as ve:
                logger.error(f"Validation error for chat ID '{chat_id}' (user '{x_user_id}'): {ve.errors()}", exc_info=True)
            except Exception as e_item:
                logger.error(f"Error loading individual chat '{chat_id}' for user '{x_user_id}': {e_item}", exc_info=True)
        
        logger.info(f"Retrieved {len(history)} chat history entries for user '{x_user_id}'.")
        return history
    except Exception as e:
        logger.error(f"Error retrieving chat history for user '{x_user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving chat history: {str(e)}")

@router.delete("/chat/all", status_code=200)
async def clear_chat_history(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """Clear all chat history for a user."""
    if not ethos_core_instance or not ethos_core_instance.memory_storage:
        logger.error("Chat storage (EthosCore/MemoryStorage) not available for clear_chat_history.")
        raise HTTPException(status_code=503, detail="Chat storage system not available")
        
    if not x_user_id or not x_user_id.strip():
        logger.warning("User ID missing in clear_chat_history.")
        raise HTTPException(status_code=400, detail="User ID required")
    
    try:
        index_key = f"chat:history:index:{x_user_id}"
        history_index_raw = await ethos_core_instance.memory_storage.get(index_key)
        history_index: List[str] = []
        if isinstance(history_index_raw, list) and all(isinstance(item, str) for item in history_index_raw):
            history_index = history_index_raw
        
        deletion_errors = []
        for chat_id in history_index:
            try: await ethos_core_instance.memory_storage.delete(f"chat:history:{x_user_id}:{chat_id}")
            except Exception as delete_error: deletion_errors.append(f"Error deleting chat {chat_id}: {delete_error}")
        
        await ethos_core_instance.memory_storage.delete(index_key)
        await ethos_core_instance.memory_storage.delete(f"chat:current:{x_user_id}")
        
        if deletion_errors: logger.warning(f"Some chats could not be deleted for user '{x_user_id}': {deletion_errors}")
        logger.info(f"Cleared all chat history for user '{x_user_id}'.")
        return {"message": "All chat history cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing chat history for user '{x_user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error clearing chat history: {str(e)}")