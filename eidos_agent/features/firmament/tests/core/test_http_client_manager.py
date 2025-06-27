# eidos_agent/features/firmament/tests/core/test_http_client_manager.py

import unittest
from unittest.mock import patch, MagicMock, AsyncMock # AsyncMock might be useful if methods were more complex
import httpx # For type hinting and checking instance types
import asyncio # For running async methods in tests
import logging
from typing import Optional, Any # For singleton pattern

# Adjust import path based on actual file structure
# Assuming tests/core is a subdir of tests/, and firmament/core/ is where http_client_manager is
try:
    # Path assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.core.http_client_manager import HTTPClientManager, DEFAULT_HTTP_CLIENT_TIMEOUT
except ImportError: # pragma: no cover
    # Fallback for simpler structures or direct execution
    print("CRITICAL: Could not resolve imports for HTTPClientManager test. Using dummy class.")
    DEFAULT_HTTP_CLIENT_TIMEOUT = 10.0 #type:ignore
    class HTTPClientManager: #type:ignore
        _instance: Optional['HTTPClientManager'] = None
        _client: Optional[httpx.AsyncClient] = None # Use Optional[httpx.AsyncClient] for type hint

        def __init__(self):
            # Simplified dummy init for testing structure
            # In dummy, ensure _client is a MagicMock that can be awaited for aclose
            if HTTPClientManager._client is None or getattr(HTTPClientManager._client, 'is_closed', True):
                 # HTTPClientManager._client = MagicMock(spec=httpx.AsyncClient)
                 # To make `aclose` awaitable on the mock:
                 _mock_async_client = MagicMock(spec=httpx.AsyncClient)
                 _mock_async_client.aclose = AsyncMock() # Make aclose an AsyncMock
                 _mock_async_client.is_closed = False
                 HTTPClientManager._client = _mock_async_client

        @classmethod
        def instance(cls):
            if cls._instance is None:
                # print("Dummy HTTPClientManager: Creating new instance.")
                cls._instance = cls()
            # Simulate re-init if client is bad
            elif cls._client is None or getattr(cls._client, 'is_closed', True):
                # print("Dummy HTTPClientManager: Client bad, re-running __init__ on instance.")
                cls._instance.__init__() # Re-initialize client on existing instance
            return cls._instance

        def get_client(self) -> Optional[httpx.AsyncClient]: # Ensure return type hint matches
            # print(f"Dummy get_client called. Client: {self._client}, Closed: {getattr(self._client, 'is_closed', 'N/A')}")
            if self._client and not getattr(self._client, 'is_closed', True):
                return self._client
            # Try to re-init if get_client is called and client is bad
            # print("Dummy get_client: client was bad, attempting re-init.")
            self.__init__() # This should re-create self._client if None or closed
            return self._client if self._client and not getattr(self._client, 'is_closed', True) else None

        async def startup(self):
            # print("Dummy startup called.")
            self.get_client() # Ensure client is attempted to be initialized
            pass

        async def shutdown(self):
            # print("Dummy shutdown called.")
            if self._client and hasattr(self._client, 'aclose') and callable(self._client.aclose):
                await self._client.aclose()
                # Simulate behavior of real shutdown
                if hasattr(self._client, 'is_closed'): self._client.is_closed = True # type: ignore
            HTTPClientManager._client = None # As per real implementation


# Using unittest.IsolatedAsyncioTestCase for better async test management if available
# Fallback to unittest.TestCase and asyncio.run if not (though modern unittest handles async def tests)
# For this environment, assume modern unittest.TestCase handles async def test methods.
BaseTestCase = unittest.TestCase

class TestHTTPClientManager(BaseTestCase):

    def setUp(self):
        # Reset the singleton's class variables for each test to ensure complete isolation
        if hasattr(HTTPClientManager, '_instance'): # Check if dummy or real class has it
            HTTPClientManager._instance = None
        if hasattr(HTTPClientManager, '_client'):
            HTTPClientManager._client = None
        # print(f"HTTPClientManager singleton reset in setUp for {self._testMethodName}")


    async def asyncTearDown(self): # unittest.IsolatedAsyncioTestCase uses this
        # Ensure any client created during a test that wasn't shut down is handled
        if HTTPClientManager._client and not HTTPClientManager._client.is_closed: # pragma: no cover
            # print(f"Tearing down dangling client for {self._testMethodName}")
            await HTTPClientManager._client.aclose()
        HTTPClientManager._instance = None
        HTTPClientManager._client = None

    # Fallback tearDown for unittest.TestCase if asyncTearDown is not called by runner
    def tearDown(self): # pragma: no cover
        if HTTPClientManager._client and not HTTPClientManager._client.is_closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # This is tricky if loop is from a higher level test runner for multiple async tests
                    # print("Warning: Event loop running in tearDown, cannot reliably close client with asyncio.run.")
                    pass # Avoid asyncio.run in a running loop if not using IsolatedAsyncioTestCase properly
                else:
                    asyncio.run(HTTPClientManager._client.aclose())
            except RuntimeError: # If loop is closed or other issues
                 pass # Best effort
        HTTPClientManager._instance = None
        HTTPClientManager._client = None


    def test_singleton_instance_creation_and_client_initialization(self): # Renamed for clarity
        print("Running: test_singleton_instance_creation_and_client_initialization")
        instance1 = HTTPClientManager.instance()
        self.assertIsNotNone(instance1, "First instance should not be None.")

        client1 = instance1.get_client() # get_client ensures client is init'd if instance() didn't or it was reset
        self.assertIsNotNone(client1, "Client should be initialized by first instance() or subsequent get_client().")
        self.assertIsInstance(client1, httpx.AsyncClient, "Client should be an httpx.AsyncClient instance.")
        self.assertFalse(client1.is_closed, "Client should be open after initialization.")

        instance2 = HTTPClientManager.instance()
        self.assertIs(instance1, instance2, "instance() should return the same singleton manager object.")
        client2 = instance2.get_client()
        self.assertIs(client1, client2, "Client object should be the same singleton across calls if not closed.")
        print("Test Passed: Singleton instance created and client initialized correctly.")

    def test_get_client_returns_active_client(self):
        print("Running: test_get_client_returns_active_client")
        manager = HTTPClientManager.instance()
        client = manager.get_client()
        self.assertIsNotNone(client, "get_client() should return a client instance.")
        self.assertIsInstance(client, httpx.AsyncClient)
        self.assertFalse(client.is_closed)
        # Check if the client returned is the one stored at class level (by singleton logic)
        self.assertIs(client, HTTPClientManager._client, "get_client() should return the internally stored client.")
        print("Test Passed: get_client() returns an active client.")

    async def test_shutdown_closes_client_and_resets_internal_client(self): # Renamed for clarity
        print("Running: test_shutdown_closes_client_and_resets_internal_client")
        manager = HTTPClientManager.instance()
        client_before_shutdown = manager.get_client()
        self.assertIsNotNone(client_before_shutdown, "Client should exist before shutdown.")
        self.assertFalse(client_before_shutdown.is_closed)

        await manager.shutdown() # This is an async method

        self.assertTrue(client_before_shutdown.is_closed, "Client instance should be closed after manager.shutdown().")
        self.assertIsNone(HTTPClientManager._client, "Class's internal _client reference should be None after shutdown.")
        print("Test Passed: shutdown() closes the client and resets class's _client attribute.")

    async def test_get_client_after_shutdown_reinitializes_new_client(self): # Renamed for clarity
        print("Running: test_get_client_after_shutdown_reinitializes_new_client")
        manager = HTTPClientManager.instance()
        original_client = manager.get_client()
        self.assertIsNotNone(original_client, "Original client should be initialized.")

        await manager.shutdown() # Shutdown the first client
        self.assertTrue(original_client.is_closed, "Original client should be closed after shutdown.")
        self.assertIsNone(HTTPClientManager._client, "Internal _client should be None after shutdown.")


        # Calling get_client() again on the same manager instance should trigger re-initialization
        new_client = manager.get_client()
        self.assertIsNotNone(new_client, "get_client() should re-initialize a new client after shutdown.")
        self.assertFalse(new_client.is_closed, "New client should be open.")
        self.assertIsNot(new_client, original_client, "A new client instance should be created, different from the original.")
        self.assertIs(HTTPClientManager._client, new_client, "Class's _client should now point to the new client.")
        print("Test Passed: get_client() re-initializes a new client after shutdown.")

    async def test_startup_method_ensures_client_is_available(self): # Renamed for clarity
        print("Running: test_startup_method_ensures_client_is_available")
        # Ensure client is not initialized at first by resetting after default setUp's instance call
        HTTPClientManager._instance = None # Force instance re-creation
        HTTPClientManager._client = None  # Force client re-creation within new instance

        manager = HTTPClientManager.instance() # This will call __init__ and create a client
        # To truly test startup's effect if client was somehow None *after* instance() was called
        # (e.g. if some other process set _client to None without calling shutdown), we can do this:
        HTTPClientManager._client = None # Manually set class _client to None *after* instance exists

        await manager.startup() # Startup should call get_client(), which re-initializes if _client is None

        client_after_startup = manager.get_client() # This get_client should find the client from startup's internal get_client
        self.assertIsNotNone(client_after_startup, "Client should be available after startup().")
        self.assertFalse(client_after_startup.is_closed, "Client should be open after startup().")
        self.assertIs(HTTPClientManager._client, client_after_startup)
        print("Test Passed: startup() ensures client is available, re-initializing if necessary.")

    @patch('httpx.AsyncClient', side_effect=RuntimeError("Simulated client creation failure"))
    def test_initialization_failure_handles_gracefully(self, MockAsyncClientWithFailure):
        print("Running: test_initialization_failure_handles_gracefully")

        # Reset singleton to force re-initialization attempt with the faulty AsyncClient
        HTTPClientManager._instance = None
        HTTPClientManager._client = None # Explicitly ensure no prior client

        with self.assertLogs(logger='eidos_agent.features.firmament.core.http_client_manager', level='ERROR') as log_cm:
            manager = HTTPClientManager.instance() # This will attempt to init client, which will fail due to patch

        self.assertIsNone(HTTPClientManager._client, "Internal _client should be None if initialization fails.")
        # The manager instance itself might still exist, but its client is bad
        self.assertIsNotNone(manager, "Manager instance should still be created.")

        self.assertTrue(any("Failed to initialize httpx.AsyncClient" in msg for msg in log_cm.output),
                        "Expected error log for client initialization failure not found.")

        # get_client should also return None if init failed and cannot recover
        # It will try to re-init, which will fail again due to the patch.
        with self.assertLogs(logger='eidos_agent.features.firmament.core.http_client_manager', level='ERROR') as log_cm_get:
            client_from_get = manager.get_client()
        self.assertIsNone(client_from_get, "get_client() should return None if client initialization persistently fails.")
        self.assertTrue(any("Failed to initialize httpx.AsyncClient" in msg for msg in log_cm_get.output) or \
                        any("Failed to provide an open httpx.AsyncClient" in msg for msg in log_cm_get.output),
                        "Expected error log during get_client after init failure not found.")
        print("Test Passed: Initialization failure handled, get_client returns None.")

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    unittest.main(verbosity=2)
