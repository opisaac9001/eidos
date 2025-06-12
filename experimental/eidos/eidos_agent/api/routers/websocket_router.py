import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Core Eidos component (to be injected)
from eidos_agent.core.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])

_manager: Optional[ConnectionManager] = None

def init_websocket_router(
    conn_manager: ConnectionManager
):
    global _manager
    _manager = conn_manager
    logger.info("WebSocket Router initialized with ConnectionManager.")

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket): # pragma: no cover
    if not _manager:
        # This scenario should ideally not happen if init_websocket_router is called correctly at startup.
        # Log an error and close the connection gracefully.
        logger.error("WebSocket Router: ConnectionManager not initialized. Cannot accept WebSocket connection.")
        await websocket.close(code=1011) # Internal Error
        return

    await websocket.accept()
    user_id = None
    connection_ok = False # Flag to track if manager.connect was successful for this user_id

    try:
        while True:
            data = await websocket.receive_json()
            logger.debug(f"WS received: {data}")

            if data.get("type") == "auth" and data.get("payload", {}).get("userId"):
                raw_temp_uid = data["payload"]["userId"]
                # Normalize user_id
                temp_uid = raw_temp_uid.lower().strip().replace(" ", "_") if isinstance(raw_temp_uid, str) and raw_temp_uid else None

                if not temp_uid:
                    logger.warning(f"WS: Invalid user_id format or empty: '{raw_temp_uid}'. Closing connection.")
                    await websocket.send_json({"type": "error", "payload": {"message": "Invalid user ID format."}})
                    break # Exit while loop, will lead to finally block and close

                user_id = temp_uid
                if await _manager.connect(websocket, user_id):
                    connection_ok = True # Mark connection as successfully registered with manager
                    logger.info(f"WS connected for user: {user_id}")
                    await _manager.send_personal_message({"type": "status", "payload": {"message": "Connected to Eidos WS."}}, user_id)
                else:
                    # This case might happen if connect itself has logic to prevent multiple connections for the same user object,
                    # or if the manager is at capacity (if such logic exists).
                    logger.error(f"WS: ConnectionManager refused connection for user {user_id}. Closing.")
                    # No need to send error here as manager.connect might have already closed it or sent a message.
                    # If not, the connection will be closed in finally.
                    break
            elif user_id is None: # No auth message received yet
                logger.warning("WS: Message received before successful authentication. Closing connection.")
                await websocket.send_json({"type": "error", "payload": {"message": "Authentication required."}})
                break
            else: # Authenticated, but unhandled message type
                logger.warning(f"WS: Unhandled message type '{data.get('type')}' from user {user_id}.")
                # Optionally, send a message back to client about unhandled type
                # await _manager.send_personal_message({"type": "warning", "payload": {"message": f"Unhandled message type: {data.get('type')}"}}, user_id)

    except WebSocketDisconnect:
        logger.info(f"WS: Disconnected user: {user_id if user_id else 'unauthenticated'}.")
    except Exception as e:
        logger.error(f"WS: Error for user {user_id if user_id else 'unknown'}: {e}", exc_info=True)
        # Attempt to inform client of error before closing, if websocket is still open
        if websocket.client_state == websocket.client_state.CONNECTED:
            try:
                await websocket.send_json({"type": "error", "payload": {"message": f"Server error: {str(e)}"}})
            except Exception as e_send: # pragma: no cover
                logger.error(f"WS: Could not send error to user {user_id if user_id else 'unknown'} before closing: {e_send}")
    finally:
        if user_id and connection_ok: # Only disconnect from manager if successfully connected
            _manager.disconnect(websocket, user_id)
            logger.info(f"WS: Ensured user {user_id} disconnected from ConnectionManager.")

        # Ensure WebSocket is closed if not already
        if websocket.client_state != websocket.client_state.DISCONNECTED: # pragma: no cover
            try:
                await websocket.close(code=1011 if 'e' in locals() else 1000) # Use 1011 if an exception occurred
            except Exception as e_close:
                 logger.error(f"WS: Error during forced close for user {user_id if user_id else 'unknown'}: {e_close}")

        if user_id and not connection_ok:
             logger.info(f"WS: User {user_id} (connection not fully registered with manager) session ended.")
        elif not user_id:
             logger.info("WS: Unauthenticated client session ended.")
