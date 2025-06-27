# eidos_agent/features/firmament/core/event_bus.py
import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Callable, Dict, List, Any, Optional # Added Optional

logger = logging.getLogger(__name__)

class EventBus:
    _instance: Optional['EventBus'] = None

    def __init__(self):
        """
        Initializes the EventBus.
        Private constructor, use EventBus.instance().
        """
        if EventBus._instance is not None: # pragma: no cover
            logger.warning("EventBus __init__ called on an existing instance's object. "
                           "This is unusual if using EventBus.instance(). Subscribers will be reset for this object.")
        self._subscribers: Dict[str, List[Callable[..., Any]]] = defaultdict(list)
        # logger.debug("EventBus initialized with empty subscribers list.") # Can be verbose

    @classmethod
    def instance(cls) -> 'EventBus':
        """Provides access to the singleton instance of the EventBus."""
        if not cls._instance:
            # logger.debug("Creating new EventBus singleton instance.")
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable[..., Any]):
        """
        Subscribes a handler to a specific event type.
        The handler can be a synchronous function or an async coroutine function.
        """
        handler_name = getattr(handler, '__name__', str(handler))
        # logger.debug(f"Subscribing handler '{handler_name}' to event type '{event_type}'. "
                    # f"Async: {inspect.iscoroutinefunction(handler)}")
        self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, data: Dict[str, Any]):
        """
        Publishes an event of a specific type with given data.
        Dispatches to all registered synchronous and asynchronous handlers for that event type.
        Asynchronous handlers are launched as tasks and not awaited directly by publish.
        """
        # logger.debug(f"Publishing event '{event_type}'. Data snippet: {str(data)[:100]}...")

        # Also handle wildcard subscribers if any were registered with '*'
        handlers_to_call = self._subscribers.get(event_type, []) + self._subscribers.get("*", [])

        if not handlers_to_call: # pragma: no cover
            # logger.debug(f"No subscribers found for event type '{event_type}' (or wildcard).")
            return

        for handler in handlers_to_call:
            handler_name = getattr(handler, '__name__', str(handler))
            try:
                if inspect.iscoroutinefunction(handler):
                    # logger.debug(f"Dispatching event '{event_type}' to async handler '{handler_name}' via asyncio.create_task.")

                    async def _async_handler_wrapper(h_coro_func: Callable[..., Any], h_event_data: Dict[str, Any]):
                        """Wrapper to execute and log errors for async event handlers."""
                        h_name = getattr(h_coro_func, '__name__', str(h_coro_func))
                        try:
                            await h_coro_func(h_event_data)
                        except Exception as e_async_handler: # pragma: no cover
                            logger.error(f"Async event handler '{h_name}' raised an exception while processing event '{event_type}': {e_async_handler}",
                                         exc_info=True,
                                         extra={"event_data_snippet": str(h_event_data)[:200]}) # Add context to log

                    asyncio.create_task(_async_handler_wrapper(handler, data))
                else:
                    # logger.debug(f"Dispatching event '{event_type}' to sync handler '{handler_name}'.")
                    handler(data)
            except Exception as e_sync_dispatch: # pragma: no cover
                # This catches errors during the synchronous handler call itself,
                # or errors during the asyncio.create_task call (though less likely for create_task).
                logger.error(f"Error occurred while dispatching to synchronous handler '{handler_name}' for event '{event_type}': {e_sync_dispatch}",
                             exc_info=True,
                             extra={"event_data_snippet": str(data)[:200]})

    def get_subscribers(self, event_type: str) -> List[Callable[..., Any]]:
        """Returns a list of handlers for a given event type (excluding wildcard). For testing/debug."""
        return list(self._subscribers.get(event_type, [])) # Return a copy

    def clear_subscribers(self, event_type: Optional[str] = None):
        """
        Clears subscribers for a specific event type, or all subscribers (including wildcard)
        if event_type is None. Useful for testing or resetting the bus.
        """
        if event_type:
            if event_type in self._subscribers:
                num_cleared = len(self._subscribers[event_type])
                del self._subscribers[event_type]
                # logger.debug(f"Cleared {num_cleared} subscribers for event type '{event_type}'.")
        else:
            total_cleared_types = len(self._subscribers)
            # logger.debug(f"Clearing all subscribers for all {total_cleared_types} event types.")
            self._subscribers.clear()


if __name__ == '__main__': # pragma: no cover
    # Configure logging for the __main__ test block
    # Set level to DEBUG to see all EventBus logs and handler logs.
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Test Scenario for Async and Sync Handlers ---
    event_bus_main_test = EventBus.instance()
    event_bus_main_test.clear_subscribers() # Ensure clean state if script is re-run

    SYNC_EVENT_TEST_TYPE = "sync_event_for_main_test"
    ASYNC_EVENT_TEST_TYPE = "async_event_for_main_test"
    MIXED_HANDLERS_EVENT_TYPE = "mixed_handlers_event_for_main_test"
    WILDCARD_TEST_EVENT = "wildcard_test_event_for_main"


    # Lists to track calls to handlers
    sync_handler_calls_main = []
    async_handler_calls_main = []
    wildcard_sync_calls_main = []
    wildcard_async_calls_main = []


    def my_test_sync_handler(data_payload: Dict[str, Any]):
        logger.info(f"SYNC_HANDLER executed with data: {data_payload}")
        sync_handler_calls_main.append(data_payload)

    async def my_test_async_handler(data_payload: Dict[str, Any]):
        logger.info(f"ASYNC_HANDLER started with data: {data_payload}. Simulating 0.02s work...")
        await asyncio.sleep(0.02)
        async_handler_calls_main.append(data_payload)
        logger.info(f"ASYNC_HANDLER finished processing data: {data_payload}")

    async def my_failing_test_async_handler(data_payload: Dict[str, Any]):
        logger.info(f"FAILING_ASYNC_HANDLER started with data: {data_payload}. Will raise error.")
        await asyncio.sleep(0.01)
        raise ValueError("This is a simulated error inside an async event handler.")

    def my_wildcard_sync_handler(event_type_actual: str, data_payload: Dict[str, Any]): # Wildcard gets event_type
        logger.info(f"WILDCARD_SYNC_HANDLER executed for event '{event_type_actual}' with data: {data_payload}")
        wildcard_sync_calls_main.append((event_type_actual, data_payload))

    async def my_wildcard_async_handler(event_type_actual: str, data_payload: Dict[str, Any]):
        logger.info(f"WILDCARD_ASYNC_HANDLER started for event '{event_type_actual}' with data: {data_payload}")
        await asyncio.sleep(0.01)
        wildcard_async_calls_main.append((event_type_actual, data_payload))
        logger.info(f"WILDCARD_ASYNC_HANDLER finished for event '{event_type_actual}'.")


    # Subscribe handlers
    event_bus_main_test.subscribe(SYNC_EVENT_TEST_TYPE, my_test_sync_handler)
    event_bus_main_test.subscribe(ASYNC_EVENT_TEST_TYPE, my_test_async_handler)
    event_bus_main_test.subscribe(ASYNC_EVENT_TEST_TYPE, my_failing_test_async_handler) # Test error logging

    event_bus_main_test.subscribe(MIXED_HANDLERS_EVENT_TYPE, my_test_sync_handler)
    event_bus_main_test.subscribe(MIXED_HANDLERS_EVENT_TYPE, my_test_async_handler)

    # Wildcard subscribers (note: publish() needs to be updated to pass event_type to wildcard handlers)
    # For now, the publish signature is (event_type, data), so handler will receive (data).
    # To pass event_type to wildcard, publish logic needs modification or handler needs to be a closure.
    # The current EventBus.publish sends only `data` to handlers.
    # For this test, let's adapt wildcard handlers to only expect `data`.
    def my_wildcard_sync_handler_adapted(data_payload: Dict[str, Any]):
        logger.info(f"WILDCARD_SYNC_HANDLER_ADAPTED executed with data: {data_payload}")
        wildcard_sync_calls_main.append(data_payload)
    async def my_wildcard_async_handler_adapted(data_payload: Dict[str, Any]):
        logger.info(f"WILDCARD_ASYNC_HANDLER_ADAPTED started with data: {data_payload}")
        await asyncio.sleep(0.01); wildcard_async_calls_main.append(data_payload)
        logger.info(f"WILDCARD_ASYNC_HANDLER_ADAPTED finished.")

    event_bus_main_test.subscribe("*", my_wildcard_sync_handler_adapted)
    event_bus_main_test.subscribe("*", my_wildcard_async_handler_adapted)


    async def run_all_event_bus_tests():
        logger.info("\n--- Publishing SYNC_EVENT_TEST_TYPE ---")
        payload_sync = {"id": 1, "message": "Hello to a synchronous world!"}
        event_bus_main_test.publish(SYNC_EVENT_TEST_TYPE, payload_sync)
        # Sync handler runs immediately. Async wildcard task is created.
        await asyncio.sleep(0.05) # Allow wildcard async task to run
        assert len(sync_handler_calls_main) == 1, f"Sync specific calls: {len(sync_handler_calls_main)}"
        assert sync_handler_calls_main[0] == payload_sync
        assert len(wildcard_sync_calls_main) == 1, f"Wildcard sync calls: {len(wildcard_sync_calls_main)}"
        assert wildcard_sync_calls_main[0] == payload_sync
        assert len(wildcard_async_calls_main) == 1, f"Wildcard async calls: {len(wildcard_async_calls_main)}"
        assert wildcard_async_calls_main[0] == payload_sync
        sync_handler_calls_main.clear(); wildcard_sync_calls_main.clear(); wildcard_async_calls_main.clear()

        logger.info("\n--- Publishing ASYNC_EVENT_TEST_TYPE (includes one failing async handler) ---")
        payload_async = {"id": 2, "message": "Hello to an asynchronous world!"}
        event_bus_main_test.publish(ASYNC_EVENT_TEST_TYPE, payload_async)
        logger.info("Async event published, tasks created (one specific, one wildcard). Waiting for them to complete...")
        await asyncio.sleep(0.1) # Wait longer for async handlers
        assert len(async_handler_calls_main) == 1, f"Async specific calls: {len(async_handler_calls_main)}" # my_test_async_handler
        if async_handler_calls_main: assert async_handler_calls_main[0] == payload_async
        # my_failing_test_async_handler also ran but raised an error (check logs for error message)
        assert len(wildcard_sync_calls_main) == 1, f"Wildcard sync calls: {len(wildcard_sync_calls_main)}"
        assert wildcard_sync_calls_main[0] == payload_async
        assert len(wildcard_async_calls_main) == 1, f"Wildcard async calls: {len(wildcard_async_calls_main)}"
        assert wildcard_async_calls_main[0] == payload_async
        async_handler_calls_main.clear(); wildcard_sync_calls_main.clear(); wildcard_async_calls_main.clear()

        logger.info("\n--- Publishing MIXED_HANDLERS_EVENT_TYPE ---")
        payload_mixed = {"id": 3, "message": "Hello to a world of mixed handlers!"}
        event_bus_main_test.publish(MIXED_HANDLERS_EVENT_TYPE, payload_mixed)
        logger.info("Mixed event published. Waiting for async handlers (specific and wildcard) to complete...")
        await asyncio.sleep(0.1) # Wait for async
        assert len(sync_handler_calls_main) == 1, f"Sync specific calls: {len(sync_handler_calls_main)}" # Specific sync handler
        if sync_handler_calls_main: assert sync_handler_calls_main[0] == payload_mixed
        assert len(async_handler_calls_main) == 1, f"Async specific calls: {len(async_handler_calls_main)}" # Specific async handler
        if async_handler_calls_main: assert async_handler_calls_main[0] == payload_mixed
        assert len(wildcard_sync_calls_main) == 1, f"Wildcard sync calls: {len(wildcard_sync_calls_main)}"
        assert wildcard_sync_calls_main[0] == payload_mixed
        assert len(wildcard_async_calls_main) == 1, f"Wildcard async calls: {len(wildcard_async_calls_main)}"
        assert wildcard_async_calls_main[0] == payload_mixed

        logger.info("\n--- EventBus __main__ tests completed. Check logs for async handler messages and any logged errors. ---")

    # Run the async test function
    asyncio.run(run_all_event_bus_tests())
