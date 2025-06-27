# eidos_agent/features/firmament/core/http_client_manager.py
import httpx
import logging
from typing import Optional, Any # For singleton pattern

logger = logging.getLogger(__name__)

# Default timeout for the shared HTTP client (in seconds)
# This can be overridden by configuration if needed later by fetching from FirmamentConfig.
DEFAULT_HTTP_CLIENT_TIMEOUT = 20.0
DEFAULT_HTTP_CONNECT_TIMEOUT_FACTOR = 2 # connect timeout = timeout * factor

class HTTPClientManager:
    """
    Manages a shared httpx.AsyncClient instance for Firmament features.
    Ensures that HTTP connections can be reused efficiently and are closed gracefully
    when the application or the Firmament system shuts down.
    Implemented as a singleton to provide a single client instance across Firmament.
    """
    _instance: Optional['HTTPClientManager'] = None
    _client: Optional[httpx.AsyncClient] = None

    # Private constructor to enforce singleton pattern via instance()
    def __init__(self):
        """
        Private constructor. Use HTTPClientManager.instance() to get an instance.
        Initializes the httpx.AsyncClient if it hasn't been initialized or was closed.
        """
        # This check is important. If instance() calls __init__ on an existing _instance
        # because _client was None or closed, we want to re-initialize _client.
        # If _client exists and is open, we don't want to create a new one here.
        if HTTPClientManager._client is not None and not HTTPClientManager._client.is_closed: # pragma: no cover
            logger.debug("HTTPClientManager: Shared client already exists and is open. Reusing in __init__ context (should be rare).")
            return # Do not re-initialize an already open client directly via __init__

        try:
            # TODO: Make timeout configurable via Firmament's main application config if needed.
            #       For now, using a module-level default.
            connect_timeout = DEFAULT_HTTP_CLIENT_TIMEOUT * DEFAULT_HTTP_CONNECT_TIMEOUT_FACTOR
            timeout_config = httpx.Timeout(DEFAULT_HTTP_CLIENT_TIMEOUT, connect=connect_timeout)

            HTTPClientManager._client = httpx.AsyncClient(timeout=timeout_config)
            logger.info(f"HTTPClientManager: Shared httpx.AsyncClient initialized. Default request timeout: {DEFAULT_HTTP_CLIENT_TIMEOUT}s, Connect timeout: {connect_timeout}s.")
        except Exception as e: # pragma: no cover
            logger.error(f"HTTPClientManager: Failed to initialize httpx.AsyncClient: {e}", exc_info=True)
            HTTPClientManager._client = None # Ensure client is None if initialization fails

    @classmethod
    def instance(cls) -> 'HTTPClientManager':
        """
        Provides access to the singleton instance of HTTPClientManager.
        If the instance doesn't exist, or if its client is closed or None,
        it initializes/re-initializes it.
        """
        if cls._instance is None:
            logger.debug("HTTPClientManager: Creating new singleton instance.")
            cls._instance = cls() # Calls __init__, which initializes _client

        # Check if client needs re-initialization (e.g., after a shutdown or init failure)
        # This is important if get_client() is called after a shutdown().
        if cls._client is None or cls._client.is_closed:
            if cls._instance is None: # Should not happen if above logic is correct
                 cls._instance = cls() # pragma: no cover
            else:
                # Client is bad, re-run client initialization part of __init__ on existing instance
                logger.warning("HTTPClientManager: Client is None or closed. Re-initializing client for existing singleton instance.")
                # Directly call the client creation logic part of __init__ or a dedicated re-init method.
                # For simplicity, __init__ itself handles this by checking _client state.
                cls._instance.__init__() # This will try to recreate _client if it's None or closed.

        return cls._instance

    def get_client(self) -> Optional[httpx.AsyncClient]:
        """
        Returns the shared httpx.AsyncClient instance.
        This method ensures the client is initialized and open before returning.
        If the client was closed or never initialized, it attempts to initialize it.
        """
        # instance() method already contains logic to re-initialize client if None or closed.
        # Calling instance() here ensures we're working with a potentially re-initialized client.
        manager_singleton = HTTPClientManager.instance() # Ensures client is checked/re-initialized if needed

        if manager_singleton._client and not manager_singleton._client.is_closed:
            return manager_singleton._client
        else: # pragma: no cover
            # This path should ideally not be hit if instance() and __init__ work correctly.
            logger.error("HTTPClientManager.get_client(): Critical - Failed to provide an open httpx.AsyncClient even after instance call.")
            return None

    async def startup(self): # Optional explicit startup, e.g., for pre-warming
        """
        Ensures the client is initialized. Can be called during application startup.
        Currently, initialization is lazy (on first instance() or get_client() call).
        This method can be expanded if explicit startup actions are needed for the client.
        """
        client = self.get_client() # get_client() will attempt to initialize if needed
        if client:
            logger.info("HTTPClientManager: Startup check complete. Shared HTTP client is available.")
        else: # pragma: no cover
            logger.error("HTTPClientManager: Startup check FAILED. Shared HTTP client is NOT available.")


    async def shutdown(self):
        """
        Closes the shared httpx.AsyncClient if it exists and is open.
        This should be called when Firmament (or the main application) is shutting down
        to ensure graceful closure of HTTP resources.
        """
        # Use the class-level _client directly for shutdown logic
        client_to_close = HTTPClientManager._client

        if client_to_close and not client_to_close.is_closed:
            logger.info("HTTPClientManager: Shutting down shared httpx.AsyncClient...")
            try:
                await client_to_close.aclose()
                logger.info("HTTPClientManager: Shared httpx.AsyncClient closed successfully.")
            except Exception as e: # pragma: no cover
                logger.error(f"HTTPClientManager: Error during httpx.AsyncClient.aclose(): {e}", exc_info=True)
        elif client_to_close and client_to_close.is_closed: # pragma: no cover
            logger.info("HTTPClientManager: Shared httpx.AsyncClient was already closed.")
        else: # pragma: no cover
            logger.info("HTTPClientManager: No active client to shut down or client was None.")

        # Set class-level _client to None after closing to allow re-initialization
        # by instance() or get_client() if the application continues or restarts parts.
        HTTPClientManager._client = None
        # Resetting _instance to None means the next call to instance() will create a new manager object.
        # This might be desired if shutdown is a full stop and restart.
        # If the manager object itself should persist but just have its client renewed, don't reset _instance.
        # For now, let's assume shutdown means the current manager cycle is done.
        # HTTPClientManager._instance = None # Optional: if shutdown means full reset of manager singleton
        # Decided against resetting _instance here to allow re-use of the manager object
        # which would then re-init its client.


if __name__ == '__main__': # pragma: no cover
    import asyncio
    logging.basicConfig(level=logging.DEBUG) # Enable DEBUG to see all manager logs

    async def main_test_http_client_manager():
        print("\n--- Testing HTTPClientManager Singleton and Lifecycle ---")

        # Test 1: Get instance 1 - should create and initialize client
        print("\n1. Acquiring first instance...")
        manager1 = HTTPClientManager.instance()
        client1 = manager1.get_client()
        assert client1 is not None, "Client1 should be initialized."
        assert not client1.is_closed, "Client1 should be open."
        print(f"Client 1 acquired: ID {id(client1)}, Open: {not client1.is_closed}")

        # Test 2: Get instance 2 - should be the same instance and client
        print("\n2. Acquiring second instance...")
        manager2 = HTTPClientManager.instance()
        client2 = manager2.get_client()
        assert client2 is not None, "Client2 should be available."
        assert manager1 is manager2, "Singleton pattern failed for manager instance."
        assert client1 is client2, "Singleton pattern failed for client object (should be same)."
        print(f"Client 2 acquired: ID {id(client2)}, Open: {not client2.is_closed}. Same instance as Client 1: {client1 is client2}")

        # Test 3: Explicit startup call (should confirm client is ready)
        print("\n3. Calling startup()...")
        await manager1.startup()
        # No direct assert here, check logs for "Client is available"

        # Test 4: Shutdown the client
        print("\n4. Shutting down client via manager1...")
        await manager1.shutdown()
        assert client1.is_closed, "Client1 should be closed after manager1.shutdown()."
        # After shutdown, manager1._client (class var) should be None
        assert HTTPClientManager._client is None, "_client should be None after shutdown."
        print(f"Client 1 status after shutdown: Closed: {client1.is_closed}")

        # Test 5: Get client after shutdown - should re-initialize a new client
        print("\n5. Acquiring client again via manager1 (after shutdown)...")
        client3 = manager1.get_client() # manager1 is still the same singleton object
        assert client3 is not None, "Client3 should be re-initialized."
        assert not client3.is_closed, "Client3 should be open."
        assert client3 is not client1, "Client3 should be a NEW client instance, different from Client1."
        print(f"Client 3 acquired: ID {id(client3)}, Open: {not client3.is_closed}. Different from Client1: {client3 is not client1}")

        # Test 6: Get client via a new call to instance() after shutdown and re-get
        print("\n6. Acquiring client via new instance() call (after shutdown & re-get)...")
        manager3 = HTTPClientManager.instance() # Should return the same manager1 instance
        client4 = manager3.get_client()
        assert client4 is client3, "Client4 should be the same as Client3 (the re-initialized client)."
        assert manager3 is manager1, "Manager3 should be the same singleton instance as manager1."
        print(f"Client 4 acquired: ID {id(client4)}. Same as Client 3: {client4 is client3}")

        # Final shutdown
        print("\n7. Final shutdown...")
        await manager1.shutdown()
        assert client3.is_closed, "Client3 should be closed after final shutdown."
        assert HTTPClientManager._client is None, "_client should be None after final shutdown."

        print("\n--- HTTPClientManager __main__ test completed successfully. ---")

    # Run the async main function
    asyncio.run(main_test_http_client_manager())
