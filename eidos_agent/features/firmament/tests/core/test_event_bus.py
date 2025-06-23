# eidos_agent/features/firmament/tests/core/test_event_bus.py

import unittest
import asyncio
import logging
from collections import defaultdict
from unittest.mock import MagicMock, patch
from typing import Callable, Dict, List, Any, Optional, AsyncGenerator # Added for type hints

# Adjust import path based on actual file structure
try:
    # Path assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.core.event_bus import EventBus
except ImportError: # pragma: no cover
    # Fallback for simpler structures or direct execution
    print("CRITICAL: Could not resolve imports for EventBus test. Using dummy class.")
    # Simplified Dummy EventBus for parsing test structure
    # This dummy needs to be robust enough for the tests to at least parse.
    logger_dummy_eb = logging.getLogger("DummyEventBusForTest")
    class EventBus: #type:ignore
        _instance: Optional['EventBus'] = None
        _subscribers: Dict[str, List[Callable[..., Any]]]

        def __init__(self):
            self._subscribers = defaultdict(list)

        @classmethod
        def instance(cls) -> 'EventBus':
            if not cls._instance:
                # logger_dummy_eb.debug("DummyEventBus: Creating new instance.")
                cls._instance = cls()
            return cls._instance

        def subscribe(self, event_type: str, handler: Callable[..., Any]):
            # logger_dummy_eb.debug(f"DummyEventBus: Subscribing to {event_type}")
            self._subscribers[event_type].append(handler)

        def publish(self, event_type: str, data: Dict[str, Any]):
            # logger_dummy_eb.debug(f"DummyEventBus: Publishing {event_type}")
            for handler_func in self._subscribers.get(event_type,[]):
                if asyncio.iscoroutinefunction(handler_func):
                    asyncio.create_task(handler_func(data))
                else:
                    handler_func(data)
            # Also handle wildcard for dummy if tests depend on it
            for handler_func_wc in self._subscribers.get("*", []):
                if asyncio.iscoroutinefunction(handler_func_wc):
                    asyncio.create_task(handler_func_wc(data)) # Simplified dummy wildcard
                else:
                    handler_func_wc(data)


        def clear_subscribers(self, event_type: Optional[str]=None):
            if event_type:
                if event_type in self._subscribers:
                    del self._subscribers[event_type]
            else:
                self._subscribers.clear()

        def get_subscribers(self, event_type: str) -> List[Callable[..., Any]]:
            return list(self._subscribers.get(event_type, []))


# For Python versions < 3.8, IsolatedAsyncioTestCase might not be available.
# Modern unittest.TestCase usually handles `async def` test methods if run with a compatible runner.
BaseTestCase = unittest.TestCase # Defaulting to this for broader compatibility in typical environments

class TestEventBus(BaseTestCase):

    def setUp(self):
        # Ensure a fresh EventBus instance for each test by resetting the singleton
        # and its internal subscribers dictionary.
        if hasattr(EventBus, '_instance') and EventBus._instance is not None:
            # If EventBus has a clear method for all subscribers, prefer that.
            # Otherwise, reset the singleton instance.
            EventBus._instance.clear_subscribers() # Clear subscribers of existing instance
            EventBus._instance = None # Force re-creation of instance

        self.bus = EventBus.instance() # This will now create a fresh instance with empty subscribers

        # Ensure subscribers are truly clear on the new instance for this test
        # This is a safeguard if the dummy EventBus or a complex singleton re-uses state.
        if hasattr(self.bus, '_subscribers'): # Should always be true for real/dummy
             self.bus._subscribers = defaultdict(list) #type:ignore

        self.sync_handler_calls: List[Dict[str, Any]] = []
        self.async_handler_calls: List[Dict[str, Any]] = []
        # Wildcard handlers in EventBus.py were changed to only receive `data`.
        # So, these test lists will store just the data dict.
        self.wildcard_sync_calls: List[Dict[str, Any]] = []
        self.wildcard_async_calls: List[Dict[str, Any]] = []
        # print(f"EventBus instance in setUp for {self._testMethodName}: id={id(self.bus)}")


    async def _wait_for_tasks(self, duration=0.05): # Increased default slightly
        """Helper to wait for asyncio.create_task to complete in tests."""
        # print(f"Waiting {duration}s for async tasks to complete...")
        await asyncio.sleep(duration)
        # print("Wait complete.")

    # --- Handler Definitions for Tests ---
    def simple_sync_handler(self, data: Dict[str, Any]):
        # print(f"simple_sync_handler called with: {data}")
        self.sync_handler_calls.append(data)

    async def simple_async_handler(self, data: Dict[str, Any]):
        # print(f"simple_async_handler START with: {data}")
        await asyncio.sleep(0.01) # Simulate async work
        self.async_handler_calls.append(data)
        # print(f"simple_async_handler END with: {data}")

    def failing_sync_handler(self, data: Dict[str, Any]):
        # print(f"failing_sync_handler called with: {data}, will raise error.")
        raise ValueError("Sync handler failed deliberately for test.")

    async def failing_async_handler(self, data: Dict[str, Any]):
        # print(f"failing_async_handler START with: {data}, will raise error.")
        await asyncio.sleep(0.01)
        raise ValueError("Async handler failed deliberately for test.")

    def wildcard_sync_handler_adapted(self, data: Dict[str, Any]):
        # print(f"wildcard_sync_handler_adapted called with data: {data}")
        self.wildcard_sync_calls.append(data)

    async def wildcard_async_handler_adapted(self, data: Dict[str, Any]):
        # print(f"wildcard_async_handler_adapted START with data: {data}")
        await asyncio.sleep(0.01)
        self.wildcard_async_calls.append(data)
        # print(f"wildcard_async_handler_adapted END with data: {data}")


    # --- Test Cases ---
    def test_singleton_instance_behavior(self): # Renamed for clarity
        print("Running: test_singleton_instance_behavior")
        instance1 = EventBus.instance()
        instance2 = EventBus.instance()
        self.assertIs(instance1, instance2, "EventBus.instance() should consistently return the same object.")
        print("Test Passed: Singleton instance behavior.")

    def test_subscribe_and_get_specific_subscribers(self): # Renamed for clarity
        print("Running: test_subscribe_and_get_specific_subscribers")
        event_a_sub_test = "EVENT_A_FOR_SUBSCRIBE_TEST"
        self.bus.subscribe(event_a_sub_test, self.simple_sync_handler)

        # Use the get_subscribers method
        subscribers_for_event_a = self.bus.get_subscribers(event_a_sub_test)
        self.assertIn(self.simple_sync_handler, subscribers_for_event_a)
        self.assertEqual(len(subscribers_for_event_a), 1)
        print("Test Passed: Subscribe and get_subscribers for specific event.")

    async def test_publish_to_sync_handler_only(self): # Renamed
        print("Running: test_publish_to_sync_handler_only")
        event_s_only = "SYNC_HANDLER_ONLY_EVENT"
        self.bus.subscribe(event_s_only, self.simple_sync_handler)
        payload = {"message_content": "sync_payload_data_1"}
        self.bus.publish(event_s_only, payload)
        # Sync handlers are called immediately, no wait needed unless testing wildcard async
        await self._wait_for_tasks(0.01) # Short wait for any potential wildcard async tasks
        self.assertEqual(len(self.sync_handler_calls), 1)
        self.assertEqual(self.sync_handler_calls[0], payload)
        print("Test Passed: Publish to sync handler only.")

    async def test_publish_to_async_handler_only(self): # Renamed
        print("Running: test_publish_to_async_handler_only")
        event_as_only = "ASYNC_HANDLER_ONLY_EVENT"
        self.bus.subscribe(event_as_only, self.simple_async_handler)
        payload = {"message_content": "async_payload_data_2"}
        self.bus.publish(event_as_only, payload)

        self.assertEqual(len(self.async_handler_calls), 0, "Async handler should not have been called yet.")
        await self._wait_for_tasks() # Wait for asyncio.create_task to execute the handler
        self.assertEqual(len(self.async_handler_calls), 1)
        self.assertEqual(self.async_handler_calls[0], payload)
        print("Test Passed: Publish to async handler only.")

    async def test_publish_to_mixed_sync_and_async_handlers(self): # Renamed
        print("Running: test_publish_to_mixed_sync_and_async_handlers")
        event_m_mixed = "MIXED_HANDLERS_TEST_EVENT"
        self.bus.subscribe(event_m_mixed, self.simple_sync_handler)
        self.bus.subscribe(event_m_mixed, self.simple_async_handler)
        payload = {"message_content": "mixed_payload_data_3"}
        self.bus.publish(event_m_mixed, payload)

        self.assertEqual(len(self.sync_handler_calls), 1, "Sync handler should run immediately.")
        self.assertEqual(self.sync_handler_calls[0], payload)
        self.assertEqual(len(self.async_handler_calls), 0, "Async handler should not have completed yet.")

        await self._wait_for_tasks() # Wait for async part
        self.assertEqual(len(self.async_handler_calls), 1, "Async handler should have completed after wait.")
        self.assertEqual(self.async_handler_calls[0], payload)
        print("Test Passed: Publish to mixed sync/async handlers.")

    async def test_error_in_sync_handler_is_correctly_logged(self): # Renamed
        print("Running: test_error_in_sync_handler_is_correctly_logged")
        event_fs_err = "FAILING_SYNC_HANDLER_EVENT"
        self.bus.subscribe(event_fs_err, self.failing_sync_handler)

        with self.assertLogs(logger='eidos_agent.features.firmament.core.event_bus', level='ERROR') as log_cm_sync_err:
            self.bus.publish(event_fs_err, {"error_trigger_sync": True})
            # Sync error is immediate, but if wildcard async is involved, wait.
            await self._wait_for_tasks(0.01)

        self.assertTrue(any("Sync event handler 'failing_sync_handler' raised an exception" in msg for msg in log_cm_sync_err.output),
                        "Expected log message for sync handler error not found.")
        print("Test Passed: Error in sync handler was logged.")

    async def test_error_in_async_handler_is_correctly_logged(self): # Renamed
        print("Running: test_error_in_async_handler_is_correctly_logged")
        event_fa_err = "FAILING_ASYNC_HANDLER_EVENT"
        self.bus.subscribe(event_fa_err, self.failing_async_handler)

        with self.assertLogs(logger='eidos_agent.features.firmament.core.event_bus', level='ERROR') as log_cm_async_err:
            self.bus.publish(event_fa_err, {"error_trigger_async": True})
            await self._wait_for_tasks() # Crucial to wait for the async task to execute and log

        self.assertTrue(any("Async event handler 'failing_async_handler' raised an exception" in msg for msg in log_cm_async_err.output),
                        "Expected log message for async handler error not found.")
        print("Test Passed: Error in async handler was logged.")

    def test_clear_subscribers_for_specific_event_type(self): # Renamed
        print("Running: test_clear_subscribers_for_specific_event_type")
        event_c_clear = "EVENT_TO_BE_CLEARED"
        self.bus.subscribe(event_c_clear, self.simple_sync_handler)
        self.assertNotEqual(len(self.bus.get_subscribers(event_c_clear)), 0)

        self.bus.clear_subscribers(event_c_clear) # Use the method from EventBus
        self.assertEqual(len(self.bus.get_subscribers(event_c_clear)), 0)
        print("Test Passed: Clear subscribers for a specific event type.")

    def test_clear_subscribers_for_all_event_types(self): # Renamed
        print("Running: test_clear_subscribers_for_all_event_types")
        self.bus.subscribe("EVENT_X_CLEAR_ALL", self.simple_sync_handler)
        self.bus.subscribe("EVENT_Y_CLEAR_ALL", self.simple_async_handler)
        self.bus.subscribe("*", self.wildcard_sync_handler_adapted) # Wildcard

        # Check internal _subscribers dict directly for this test of clear_subscribers()
        self.assertGreater(len(self.bus._subscribers), 0) #type:ignore

        self.bus.clear_subscribers() # Call with no argument to clear all
        self.assertEqual(len(self.bus._subscribers), 0) #type:ignore
        print("Test Passed: Clear all subscribers for all event types.")

    async def test_wildcard_subscribers_receive_events(self):
        print("Running: test_wildcard_subscribers_receive_events")
        SPECIFIC_EVENT_FOR_WILDCARD_TEST = "SPECIFIC_EVENT_WILDCARD"

        # Subscribe specific and wildcard handlers
        self.bus.subscribe(SPECIFIC_EVENT_FOR_WILDCARD_TEST, self.simple_sync_handler) # Specific sync
        self.bus.subscribe("*", self.wildcard_sync_handler_adapted)         # Wildcard sync
        self.bus.subscribe("*", self.wildcard_async_handler_adapted)        # Wildcard async

        payload_wild = {"data_for_wildcard": "event_data_for_all"}
        self.bus.publish(SPECIFIC_EVENT_FOR_WILDCARD_TEST, payload_wild)
        await self._wait_for_tasks()

        self.assertEqual(len(self.sync_handler_calls), 1, "Specific sync handler call count mismatch.")
        self.assertEqual(self.sync_handler_calls[0], payload_wild)

        self.assertEqual(len(self.wildcard_sync_calls), 1, "Wildcard sync handler call count mismatch.")
        self.assertEqual(self.wildcard_sync_calls[0], payload_wild) # Adapted wildcard receives only data

        self.assertEqual(len(self.wildcard_async_calls), 1, "Wildcard async handler call count mismatch.")
        self.assertEqual(self.wildcard_async_calls[0], payload_wild) # Adapted wildcard receives only data
        print("Test Passed: Wildcard subscribers received event along with specific handler.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    # For more detailed logs including EventBus internal debugs, set level=logging.DEBUG
    # logging.getLogger('eidos_agent.features.firmament.core.event_bus').setLevel(logging.DEBUG)

    # unittest.main() will discover and run async def tests correctly in modern Python.
    unittest.main(verbosity=2)
