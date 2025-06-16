# eidos_agent/features/firmament/core/memory_writer.py

# This module will be responsible for interfacing with EthosCore
# to write various types of experiences, thoughts, or events
# into Pathos's memory.

# from ..integrations.ethos_writer_adapter import EthosWriterAdapter # Example, if an adapter is used

class MemoryWriter:
    _instance = None

    def __init__(self, ethos_writer_adapter_instance=None):
        """
        Initializes the MemoryWriter.
        In a real scenario, this would take an instance of an EthosCore interface/adapter.
        For now, it uses a placeholder.
        """
        # self.ethos_adapter = ethos_writer_adapter_instance if ethos_writer_adapter_instance else EthosWriterAdapter()
        # For placeholder purposes, we'll simulate the adapter.
        self.ethos_adapter = ethos_writer_adapter_instance
        if self.ethos_adapter:
            print("MemoryWriter initialized with a provided Ethos adapter.")
        else:
            print("MemoryWriter initialized. (Note: EthosCore connection is a placeholder/mocked).")

    @classmethod
    def instance(cls, ethos_writer_adapter_instance=None):
        """Provides a singleton instance of MemoryWriter."""
        if not cls._instance:
            # Pass the adapter instance only on first creation if provided
            cls._instance = MemoryWriter(ethos_writer_adapter_instance=ethos_writer_adapter_instance)
        elif ethos_writer_adapter_instance and not cls._instance.ethos_adapter:
            # If an adapter is provided later and the current instance doesn't have one
            cls._instance.ethos_adapter = ethos_writer_adapter_instance
            print("MemoryWriter singleton updated with an Ethos adapter.")
        return cls._instance

    def write_to_memory(self, memory_data: dict) -> bool:
        """
        Writes a piece of data to memory via an EthosCore adapter.

        Args:
            memory_data (dict): A dictionary containing the data to be written.
                                Expected to have keys like 'type', 'content',
                                and other relevant metadata (e.g., timestamp, mood_impact).
        Returns:
            bool: True if writing was successful (or simulated as such), False otherwise.
        """
        if not isinstance(memory_data, dict):
            print("MemoryWriter Error: memory_data must be a dictionary.")
            return False

        entry_type = memory_data.get("type")
        content = memory_data.get("content")
        timestamp = memory_data.get("timestamp") # Timestamps are generally crucial for memories

        if not entry_type or not content:
            print("MemoryWriter Error: memory_data must include at least 'type' and 'content'.")
            return False

        if not timestamp:
            print("MemoryWriter Warning: 'timestamp' is missing from memory_data. This is highly recommended.")
            # Potentially generate a timestamp here if policy allows, e.g.:
            # from datetime import datetime, timezone
            # memory_data['timestamp'] = datetime.now(timezone.utc).isoformat()

        # In a real implementation, this would call the EthosCore writing mechanism via the adapter
        if self.ethos_adapter:
            # success = self.ethos_adapter.save_memory_entry(memory_data)
            # For now, simulate the call if an adapter (even mock) is present
            print(f"MemoryWriter (via adapter): Attempting to write to EthosCore:")
            success = True # Simulate success
        else:
            # Placeholder logic if no adapter is configured
            print(f"MemoryWriter (placeholder): Attempting to write to EthosCore:")
            success = True # Simulate success

        print(f"  Type: {entry_type}")
        print(f"  Content: \"{content}\"")
        if timestamp:
            print(f"  Timestamp: {timestamp}")

        if success:
            print("  Successfully written to memory (simulated).")
            return True
        else:
            print("  Failed to write to memory (simulated).")
            return False

# Example of how this might be used (optional, for testing)
if __name__ == '__main__':
    # Get the singleton instance of MemoryWriter
    # For this test, we're not providing a mock adapter, so it will use its internal placeholder logic.
    memory_writer_service = MemoryWriter.instance()

    print("\n--- Test Case 1: Valid Thought Data ---")
    thought_data = {
        "type": "thought",
        "content": "The car that reversed in the driveway was suspicious. I should remember that.",
        "related_event_id": "evt_car_driveby_001",
        "mood_at_time": "uneasy",
        "timestamp": "2023-10-27T10:30:00Z" # Using ISO format with Z for UTC
    }
    result1 = memory_writer_service.write_to_memory(thought_data)
    print(f"Result: {'Success' if result1 else 'Failure'}")

    print("\n--- Test Case 2: Valid Event Observation ---")
    event_data = {
        "type": "world_event_observation",
        "content": "Observed a mailman delivering a package. He seemed friendly.",
        "npc_involved": "Mailman_NPC_ID_007",
        "location": "front_porch",
        "timestamp": "2023-10-27T10:25:00Z"
    }
    result2 = memory_writer_service.write_to_memory(event_data)
    print(f"Result: {'Success' if result2 else 'Failure'}")

    print("\n--- Test Case 3: Invalid Data (Not a Dict) ---")
    invalid_data_1 = "this is not a dictionary"
    result3 = memory_writer_service.write_to_memory(invalid_data_1)
    print(f"Result: {'Success' if result3 else 'Failure'}")

    print("\n--- Test Case 4: Incomplete Data (Missing Content) ---")
    invalid_data_2 = {"type": "thought_fragment", "timestamp": "2023-10-27T11:00:00Z"}
    result4 = memory_writer_service.write_to_memory(invalid_data_2)
    print(f"Result: {'Success' if result4 else 'Failure'}")

    print("\n--- Test Case 5: Data Missing Timestamp (Warning Expected) ---")
    event_missing_ts = {
        "type": "internal_realization",
        "content": "I need to consider how memories are time-stamped.",
    }
    result5 = memory_writer_service.write_to_memory(event_missing_ts)
    print(f"Result: {'Success' if result5 else 'Failure'}")

    print("\nMemoryWriter testing finished.")
