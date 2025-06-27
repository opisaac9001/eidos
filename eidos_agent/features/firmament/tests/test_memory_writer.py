# eidos_agent/features/firmament/tests/test_memory_writer.py

import unittest
from unittest.mock import Mock, patch # Using unittest.mock

# Attempt to import necessary modules from Firmament
try:
    from ..core.memory_writer import MemoryWriter
    # MemoryWriter uses EthosWriterAdapter, so we'll mock that.
    from ..integrations.ethos_writer import EthosWriterAdapter
except ImportError:
    print("ImportError in test_memory_writer.py. Some tests may fail or not run correctly.")
    print("Ensure PYTHONPATH is set up correctly.")
    # Define dummy classes if imports fail
    class MemoryWriter:
        _instance = None
        def __init__(self, ethos_writer_adapter_instance=None): self.ethos_adapter = ethos_writer_adapter_instance
        @classmethod
        def instance(cls, ethos_writer_adapter_instance=None):
            if not cls._instance: cls._instance = cls(ethos_writer_adapter_instance)
            return cls._instance
        def write_to_memory(self, data): return False
    class EthosWriterAdapter: pass


class TestMemoryWriter(unittest.TestCase):

    def setUp(self):
        """Set up test environment before each test method."""
        print(f"\n--- Setting up for: {self._testMethodName} ---")

        # Create a mock instance of EthosWriterAdapter.
        # This mock will allow us to control its behavior (e.g., return values)
        # and assert that its methods (e.g., save_memory_entry) are called correctly.
        self.mock_ethos_adapter = Mock(spec=EthosWriterAdapter)

        # Configure the mock's save_memory_entry method to return True by default (simulating success).
        self.mock_ethos_adapter.save_memory_entry.return_value = True
        self.mock_ethos_adapter.batch_save_memory_entries.return_value = (0,0) # (success_count, total_count)

        # Get a MemoryWriter instance, injecting the mock adapter.
        # Since MemoryWriter is a singleton, we need to be careful if other tests
        # might have already initialized it without a mock.
        # For robust testing, MemoryWriter.instance() might need a reset mechanism,
        # or we could patch `MemoryWriter._instance = None` before getting a new one.
        # For this test suite, let's assume we can reset it for a clean injection.
        MemoryWriter._instance = None # Reset singleton for clean injection
        self.memory_writer = MemoryWriter.instance(ethos_writer_adapter_instance=self.mock_ethos_adapter)

        print("Setup complete. MemoryWriter initialized with mock EthosWriterAdapter.")


    def test_write_valid_memory_entry_success(self):
        """
        Tests that MemoryWriter successfully processes a valid memory entry
        and calls the EthosWriterAdapter's save_memory_entry method.
        """
        print("Running: test_write_valid_memory_entry_success")
        valid_data = {
            "type": "test_thought",
            "content": "This is a valid test thought for the memory writer.",
            "timestamp": "2023-01-01T12:00:00Z", # Timestamp is important
            "metadata": {"source": "unittest", "urgency": "medium"}
        }

        success = self.memory_writer.write_to_memory(valid_data)

        self.assertTrue(success, "MemoryWriter.write_to_memory should return True for a valid entry when adapter succeeds.")
        # Verify that the underlying adapter's save_memory_entry was called once with the correct data.
        self.mock_ethos_adapter.save_memory_entry.assert_called_once_with(valid_data)
        print("Test Passed: Valid entry processed, adapter called.")


    def test_write_valid_memory_entry_failure_at_adapter(self):
        """
        Tests that MemoryWriter returns False if the EthosWriterAdapter fails to save.
        """
        print("Running: test_write_valid_memory_entry_failure_at_adapter")
        # Configure the mock adapter's save_memory_entry to simulate a failure.
        self.mock_ethos_adapter.save_memory_entry.return_value = False

        valid_data = {
            "type": "test_event",
            "content": "An event that the adapter fails to save.",
            "timestamp": "2023-01-01T12:05:00Z"
        }

        success = self.memory_writer.write_to_memory(valid_data)

        self.assertFalse(success, "MemoryWriter.write_to_memory should return False when adapter fails.")
        self.mock_ethos_adapter.save_memory_entry.assert_called_once_with(valid_data)
        print("Test Passed: Failure at adapter level handled correctly.")


    def test_write_invalid_data_type_input(self):
        """
        Tests that MemoryWriter handles non-dictionary input gracefully and does not call the adapter.
        """
        print("Running: test_write_invalid_data_type_input")
        invalid_input = "this is not a dictionary"

        success = self.memory_writer.write_to_memory(invalid_input)

        self.assertFalse(success, "MemoryWriter.write_to_memory should return False for non-dict input.")
        # Verify that save_memory_entry was NOT called on the adapter.
        self.mock_ethos_adapter.save_memory_entry.assert_not_called()
        print("Test Passed: Non-dictionary input handled, adapter not called.")


    def test_write_entry_missing_required_type_field(self):
        """
        Tests that MemoryWriter rejects entries missing the 'type' field.
        """
        print("Running: test_write_entry_missing_required_type_field")
        entry_missing_type = {
            # "type": "missing", # 'type' field is absent
            "content": "This entry has no type specified.",
            "timestamp": "2023-01-01T12:10:00Z"
        }

        success = self.memory_writer.write_to_memory(entry_missing_type)

        self.assertFalse(success, "MemoryWriter.write_to_memory should return False for an entry missing 'type'.")
        self.mock_ethos_adapter.save_memory_entry.assert_not_called()
        print("Test Passed: Entry missing 'type' rejected, adapter not called.")


    def test_write_entry_missing_required_content_field(self):
        """
        Tests that MemoryWriter rejects entries missing the 'content' field.
        """
        print("Running: test_write_entry_missing_required_content_field")
        entry_missing_content = {
            "type": "test_observation",
            # "content": "missing", # 'content' field is absent
            "timestamp": "2023-01-01T12:15:00Z"
        }

        success = self.memory_writer.write_to_memory(entry_missing_content)

        self.assertFalse(success, "MemoryWriter.write_to_memory should return False for an entry missing 'content'.")
        self.mock_ethos_adapter.save_memory_entry.assert_not_called()
        print("Test Passed: Entry missing 'content' rejected, adapter not called.")

    def test_write_entry_missing_timestamp_is_accepted_with_warning(self):
        """
        Tests that MemoryWriter accepts entries missing 'timestamp' but logs a warning.
        The MemoryWriter itself might not add the timestamp; that could be the adapter's job.
        MemoryWriter's primary validation is for type and content.
        """
        print("Running: test_write_entry_missing_timestamp_is_accepted_with_warning")
        entry_missing_timestamp = {
            "type": "test_note",
            "content": "This note is missing a timestamp, but should still be passed to adapter."
            # "timestamp": "missing"
        }

        # We expect MemoryWriter to pass this to the adapter. The adapter might add a timestamp.
        # We'll use a patch to spy on print calls to check for the warning.
        with patch('builtins.print') as mock_print:
            success = self.memory_writer.write_to_memory(entry_missing_timestamp)

        self.assertTrue(success, "MemoryWriter should pass entry missing timestamp to adapter if type/content are valid.")
        self.mock_ethos_adapter.save_memory_entry.assert_called_once_with(entry_missing_timestamp)

        # Check if the warning about missing timestamp was printed by MemoryWriter
        warning_found = False
        for call_args in mock_print.call_args_list:
            if "MemoryWriter Warning: 'timestamp' is missing" in str(call_args):
                warning_found = True
                break
        self.assertTrue(warning_found, "MemoryWriter should print a warning for missing timestamp.")
        print("Test Passed: Entry missing timestamp accepted (with warning), adapter called.")

    # Add more tests for other scenarios:
    # - Different types of valid entries.
    # - Behavior of the singleton `instance()` method (e.g., returns same instance).

if __name__ == '__main__':
    unittest.main(verbosity=2)
