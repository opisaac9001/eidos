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

    async def is_user_connected(self, user_id: str) -> bool:
        """
        Checks if a given user_id has any active WebSocket connections.
        """
        if not user_id:
            return False

        # Ensure active_connections is accessed in a thread-safe manner if needed,
        # though typical FastAPI/Starlette usage with websockets per user often aligns.
        # For this implementation, direct access is shown.
        if user_id in self.active_connections and self.active_connections[user_id]:
            # Additionally, one might want to ping or check websocket.client_state
            # to ensure connections are truly alive, but for now, presence in the list is sufficient.
            logger.debug(f"ConnectionManager: User '{user_id}' has {len(self.active_connections[user_id])} active connection(s). Reporting as connected.")
            return True

        logger.debug(f"ConnectionManager: User '{user_id}' has no active connections. Reporting as not connected.")
        return False

if __name__ == '__main__':
    import asyncio
    import unittest.mock # For mocking WebSocket
    from starlette.websockets import WebSocket # For spec in mock

    # Configure logger for __main__ testing (if not already configured by top-level logging setup)
    if not logger.handlers: # Check if logger already has handlers
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    async def main_test_runner():
        logger.info("--- Testing ConnectionManager ---")
        manager = ConnectionManager()

        # Mock WebSockets
        # These mocks need to be AsyncMock if methods like send_json or close are awaited directly on them.
        # For ConnectionManager's current usage (adding/removing from list, checking presence),
        # a basic MagicMock or a simple object might suffice if we don't call methods on the websocket itself.
        # However, using AsyncMock with spec=WebSocket is more robust for future changes.
        mock_ws_user1_conn1 = unittest.mock.AsyncMock(spec=WebSocket)
        mock_ws_user1_conn2 = unittest.mock.AsyncMock(spec=WebSocket)
        mock_ws_user2_conn1 = unittest.mock.AsyncMock(spec=WebSocket)

        logger.info("\n--- Testing connect and disconnect ---")
        # Test connecting user1
        await manager.connect(mock_ws_user1_conn1, "user1")
        assert "user1" in manager.active_connections, "User1 should be in active_connections."
        assert mock_ws_user1_conn1 in manager.active_connections["user1"], "mock_ws_user1_conn1 should be in user1's list."
        logger.info("User1 (conn1) connected.")

        # Test connecting another instance for user1
        await manager.connect(mock_ws_user1_conn2, "user1")
        assert len(manager.active_connections["user1"]) == 2, "User1 should have 2 active connections."
        logger.info("User1 (conn2) connected.")

        # Test connecting user2
        await manager.connect(mock_ws_user2_conn1, "user2")
        assert "user2" in manager.active_connections, "User2 should be in active_connections."
        assert len(manager.active_connections["user2"]) == 1, "User2 should have 1 active connection."
        logger.info("User2 (conn1) connected.")

        # Test disconnecting one instance of user1
        manager.disconnect(mock_ws_user1_conn1, "user1")
        assert len(manager.active_connections["user1"]) == 1, "User1 should have 1 connection remaining."
        assert mock_ws_user1_conn1 not in manager.active_connections["user1"], "mock_ws_user1_conn1 should be removed."
        logger.info("User1 (conn1) disconnected.")

        # Test disconnecting the other instance of user1 (should remove user1 from active_connections)
        manager.disconnect(mock_ws_user1_conn2, "user1")
        assert "user1" not in manager.active_connections, "User1 should be removed from active_connections."
        logger.info("User1 (conn2) disconnected, user1 entry removed.")

        logger.info("\n--- Testing is_user_connected ---")
        # User1 is fully disconnected
        assert not await manager.is_user_connected("user1"), "User1 should not be connected after all disconnects."

        # User2 is still connected
        assert await manager.is_user_connected("user2"), "User2 should still be connected."
        logger.info(f"is_user_connected('user2'): {await manager.is_user_connected('user2')}")

        # Check a non-existent user
        assert not await manager.is_user_connected("user_nonexistent"), "Non-existent user should not be connected."
        logger.info(f"is_user_connected('user_nonexistent'): {await manager.is_user_connected('user_nonexistent')}")

        # Reconnect user1 for further tests
        await manager.connect(mock_ws_user1_conn1, "user1")
        assert await manager.is_user_connected("user1"), "User1 should be re-connected."
        logger.info(f"is_user_connected('user1') after reconnect: {await manager.is_user_connected('user1')}")

        # Test disconnect for user2
        manager.disconnect(mock_ws_user2_conn1, "user2")
        assert not await manager.is_user_connected("user2"), "User2 should be disconnected now."
        logger.info(f"is_user_connected('user2') after disconnect: {await manager.is_user_connected('user2')}")

        logger.info("\n--- Testing send_personal_message (mocked send) ---")
        # User1 is connected, User2 is not.
        test_message = {"type": "test", "content": "Hello from __main__"}

        # Spy on the websocket's send_json method
        mock_ws_user1_conn1.send_json = unittest.mock.AsyncMock() # Reset mock if used before or ensure it's fresh

        await manager.send_personal_message(test_message, "user1")
        mock_ws_user1_conn1.send_json.assert_called_once_with(test_message)
        logger.info("send_personal_message called for user1. send_json on mock_ws_user1_conn1 was called.")

        # Try sending to a disconnected user
        mock_ws_user2_conn1.send_json = unittest.mock.AsyncMock() # Ensure it's fresh if it was ever connected
        await manager.send_personal_message(test_message, "user2") # User2 is disconnected
        mock_ws_user2_conn1.send_json.assert_not_called()
        logger.info("send_personal_message called for user2 (disconnected). send_json on mock_ws_user2_conn1 was NOT called.")

        logger.info("\n--- Testing disconnect_all ---")
        # User1 is currently connected.
        assert await manager.is_user_connected("user1"), "User1 should be connected before disconnect_all."

        # Setup mock_ws_user1_conn1.close to be an async mock
        mock_ws_user1_conn1.close = unittest.mock.AsyncMock()

        await manager.disconnect_all()
        assert not manager.active_connections, "active_connections should be empty after disconnect_all."
        assert not await manager.is_user_connected("user1"), "User1 should not be connected after disconnect_all."
        mock_ws_user1_conn1.close.assert_called_once_with(code=1000)
        logger.info("disconnect_all called. active_connections is empty. User1 is_user_connected is False. WebSocket close was called.")

        logger.info("\n--- ConnectionManager tests finished ---")

    asyncio.run(main_test_runner())