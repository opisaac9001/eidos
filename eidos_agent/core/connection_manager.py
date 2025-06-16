import logging
from typing import Dict, List, Any, Optional, Tuple 
from fastapi import WebSocket

logger = logging.getLogger(__name__) 

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        logger.info("ConnectionManager initialized.")

    async def connect(self, websocket: WebSocket, user_id: str) -> bool: # Added return type hint
        """
        Adds an ALREADY ACCEPTED WebSocket connection and associates it with a user_id.
        If the user_id is new, a new list for their connections is created.
        Returns True if successful, False otherwise.
        """
        if not user_id or not isinstance(user_id, str):
            logger.warning(f"ConnectionManager: Attempted to add WebSocket with invalid user_id: {user_id}.")
            # The endpoint should handle closing the websocket if user_id is invalid before calling this.
            return False 

        # CRITICAL: DO NOT call await websocket.accept() here. 
        # It must be done in the FastAPI endpoint handler BEFORE calling this method.
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
            logger.debug(f"ConnectionManager: Created connection list for new user: {user_id}")
        
        if websocket not in self.active_connections[user_id]: # Avoid duplicate additions
            self.active_connections[user_id].append(websocket)
            logger.debug(f"ConnectionManager: User {user_id} WebSocket {id(websocket)} added. Total connections for user: {len(self.active_connections[user_id])}")
            return True
        else:
            logger.warning(f"ConnectionManager: WebSocket {id(websocket)} for user {user_id} already in active connections.")
            return True # Still considered successful if already there for some reason

    # ... rest of the ConnectionManager class (disconnect, send_personal_message, etc.)
    # should remain as in the previous complete version I provided.
    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                logger.debug(f"ConnectionManager: User {user_id} disconnected WebSocket {id(websocket)}. Remaining connections: {len(self.active_connections[user_id])}")
                if not self.active_connections[user_id]: 
                    del self.active_connections[user_id]
                    logger.debug(f"ConnectionManager: No connections left for user {user_id}. Removed user entry.")
            except ValueError:
                logger.warning(f"ConnectionManager: Attempted to remove WebSocket for user {user_id} (ID: {id(websocket)}) but it was not found in their active list.")
        else:
            logger.warning(f"ConnectionManager: Attempted to disconnect WebSocket for unknown or already cleared user_id: {user_id}")

    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        if user_id in self.active_connections:
            sockets_for_user = list(self.active_connections[user_id]) 
            if not sockets_for_user:
                logger.debug(f"ConnectionManager: No active sockets found for user {user_id} when trying to send personal message (list was empty).")
                if user_id in self.active_connections and not self.active_connections[user_id]: 
                    del self.active_connections[user_id]
                return

            logger.debug(f"ConnectionManager: Sending personal message to user {user_id} ({len(sockets_for_user)} socket(s)). Message: {str(message)[:100]}...")
            
            disconnected_websockets_during_send: List[WebSocket] = []
            for websocket_conn in sockets_for_user:
                try:
                    await websocket_conn.send_json(message)
                    logger.debug(f"ConnectionManager: Sent message to user {user_id} via WebSocket {id(websocket_conn)}.")
                except Exception as e:
                    logger.error(f"ConnectionManager: Failed to send message to user {user_id} via WebSocket {id(websocket_conn)}: {e}. Marking for disconnect.")
                    disconnected_websockets_during_send.append(websocket_conn)

            for ws_to_remove in disconnected_websockets_during_send:
                self.disconnect(ws_to_remove, user_id) 
        else:
            logger.debug(f"ConnectionManager: Attempted to send personal message to user {user_id}, but no active connections or user entry found.")

    async def broadcast(self, message: Dict[str, Any]):
        logger.debug(f"ConnectionManager: Broadcasting message to all active users. Message: {str(message)[:100]}...")
        sockets_to_disconnect: List[Tuple[str, WebSocket]] = []

        for user_id, websockets_list in list(self.active_connections.items()):
            for websocket_conn in list(websockets_list): 
                try:
                    await websocket_conn.send_json(message)
                    logger.debug(f"ConnectionManager: Broadcast message to user {user_id} via WebSocket {id(websocket_conn)}.")
                except Exception as e:
                    logger.error(f"ConnectionManager: Failed to broadcast message to user {user_id} via WebSocket {id(websocket_conn)}: {e}. Marking for disconnect.")
                    sockets_to_disconnect.append((user_id, websocket_conn))
        
        for uid, ws_to_remove in sockets_to_disconnect:
            self.disconnect(ws_to_remove, uid)

    async def disconnect_all(self):
        logger.info("ConnectionManager: Closing all active WebSocket connections...")
        all_user_ids = list(self.active_connections.keys())
        
        for user_id in all_user_ids:
            if user_id in self.active_connections: 
                sockets_to_close = list(self.active_connections[user_id])
                for websocket_conn in sockets_to_close:
                    try:
                        await websocket_conn.close(code=1000) 
                        logger.debug(f"ConnectionManager: Closed WebSocket {id(websocket_conn)} for user {user_id}.")
                    except RuntimeError as e_runtime: 
                        logger.warning(f"ConnectionManager: Runtime error closing WebSocket {id(websocket_conn)} for user {user_id} (likely already closed): {e_runtime}")
                    except Exception as e_close:
                        logger.error(f"ConnectionManager: Error closing WebSocket {id(websocket_conn)} for user {user_id}: {e_close}", exc_info=True)
            
            if user_id in self.active_connections:
                del self.active_connections[user_id]
                logger.debug(f"ConnectionManager: Cleared connection entry for user {user_id} during disconnect_all.")
        
        self.active_connections.clear() 
        logger.info("ConnectionManager: All WebSocket connections processed for closure.")