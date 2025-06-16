from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import json # For potential metadata parsing if content is JSON string
import uuid # For example usage

from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry, MemoryStorage
from eidos_agent.core.config import EthosConfig # For configuration parameters
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class SalienceForgettingService:
    def __init__(self, memory_storage: MemoryStorage, ethos_config: EthosConfig):
        self.memory_storage = memory_storage
        self.ethos_config = ethos_config
        # Default values from a conceptual EthosConfig structure for this service
        self.salience_decay_rate_per_day = self.ethos_config.get('salience_decay_rate_per_day', 0.05) # Example: 5% decay per day
        self.min_salience_for_decay = self.ethos_config.get('min_salience_for_decay', 0.1)
        self.archival_salience_threshold = self.ethos_config.get('archival_salience_threshold', 0.05) # Salience below which archival is considered
        self.deletion_salience_threshold = self.ethos_config.get('deletion_salience_threshold', 0.01) # Salience below which deletion is considered
        self.deletion_min_age_days = self.ethos_config.get('deletion_min_age_days', 365) # Min age for deletion
        self.detail_fading_salience_threshold = self.ethos_config.get('detail_fading_salience_threshold', 0.2)
        self.max_memories_to_process_per_cycle = self.ethos_config.get('salience_max_memories_per_cycle', 100)

        logger.info("SalienceForgettingService initialized.")

    async def get_candidate_memories_for_salience_update(self) -> List[MemoryEntry]:
        """
        (Conceptual) Retrieves memory entries that are candidates for salience update.
        This would ideally query memories that haven't been updated recently,
        or all memories if a full scan is intended.
        For this placeholder, it will not fetch actual data but return an empty list.
        Actual implementation requires enhanced MemoryStorage methods.
        """
        logger.info("Attempting to fetch candidate memories for salience update (conceptual).")
        # Placeholder: In a real system, this would be a DB query.
        # e.g., self.memory_storage.get_memories_for_salience_processing(limit=self.max_memories_to_process_per_cycle)
        # This method would look for memories not recently updated via 'timestamp_last_salience_update'
        # or based on other criteria like age or type.
        logger.warning("`get_candidate_memories_for_salience_update` is a placeholder and does not fetch real data.")
        return []

    async def update_memory_salience(self, memory: MemoryEntry) -> bool:
        """
        (Conceptual) Updates the salience of a memory based on decay rules.
        Returns True if changes were made that need to be persisted.
        """
        made_changes = False
        current_salience = memory.get('salience')
        if current_salience is None:
            current_salience = 0.5

        memory_id_str = str(memory.get('id', 'UnknownID'))


        if current_salience < self.min_salience_for_decay:
            if not memory.get('timestamp_last_salience_update'):
                memory['timestamp_last_salience_update'] = datetime.now(timezone.utc).isoformat()
                made_changes = True
            return made_changes

        last_update_str = memory.get('timestamp_last_salience_update')
        # Use creation timestamp if last_accessed_ts is not available
        last_accessed_str = memory.get('last_accessed_ts', memory.get('timestamp'))

        # Prefer last_update_str if available, otherwise use last_accessed_str
        reference_time_str = last_update_str if last_update_str else last_accessed_str

        if reference_time_str:
            try:
                # Ensure timestamp is timezone-aware (UTC)
                ref_time_naive = datetime.fromisoformat(reference_time_str.replace("Z", ""))
                ref_time = ref_time_naive.replace(tzinfo=timezone.utc) if ref_time_naive.tzinfo is None else ref_time_naive.astimezone(timezone.utc)

                days_since_ref = (datetime.now(timezone.utc) - ref_time).total_seconds() / (24 * 60 * 60)

                if days_since_ref > 0:
                    decay_amount = days_since_ref * self.salience_decay_rate_per_day
                    new_salience = max(0.0, current_salience - decay_amount)

                    if abs(new_salience - current_salience) > 1e-5:
                        memory['salience'] = new_salience
                        made_changes = True
                        logger.debug(f"Memory {memory_id_str} salience decayed from {current_salience:.3f} to {new_salience:.3f} over {days_since_ref:.2f} days.")
                    else:
                        logger.debug(f"Memory {memory_id_str} salience {current_salience:.3f} unchanged after {days_since_ref:.2f} days (decay too small or already at min).")
            except ValueError:
                logger.warning(f"Could not parse timestamp for memory {memory_id_str}: '{reference_time_str}'")

        # Always update the 'timestamp_last_salience_update' if we processed this memory
        new_last_update_ts = datetime.now(timezone.utc).isoformat()
        if memory.get('timestamp_last_salience_update') != new_last_update_ts:
            memory['timestamp_last_salience_update'] = new_last_update_ts
            made_changes = True # This itself is a change to persist

        return made_changes

    async def apply_detail_fading(self, memory: MemoryEntry) -> bool:
        """
        (Conceptual) Applies detail fading strategy.
        If salience is very low and a summary exists, content might be cleared.
        Returns True if changes were made.
        """
        made_changes = False
        current_salience = memory.get('salience', 0.5)
        memory_id_str = str(memory.get('id', 'UnknownID'))

        if current_salience < self.detail_fading_salience_threshold and \
           memory.get('summary_llm') and memory.get('content'): # Check if content exists before fading
            logger.info(f"Detail fading: Clearing content for memory {memory_id_str} due to low salience ({current_salience:.3f}) and summary presence.")
            memory['content'] = ""
            memory.setdefault('metadata', {})['detail_faded_timestamp'] = datetime.now(timezone.utc).isoformat()
            made_changes = True
        return made_changes

    async def apply_archival(self, memory: MemoryEntry) -> bool:
        """
        (Conceptual) Applies archival strategy. Sets 'is_archived = True'.
        Returns True if changes were made.
        """
        made_changes = False
        current_salience = memory.get('salience', 0.5)
        memory_id_str = str(memory.get('id', 'UnknownID'))

        if not memory.get('is_archived') and current_salience < self.archival_salience_threshold:
            logger.info(f"Archiving memory {memory_id_str} due to low salience ({current_salience:.3f}).")
            memory['is_archived'] = True
            memory.setdefault('metadata', {})['archived_timestamp'] = datetime.now(timezone.utc).isoformat()
            made_changes = True
        return made_changes

    async def should_delete_memory(self, memory: MemoryEntry) -> bool:
        """
        (Conceptual) Determines if a memory should be deleted.
        """
        current_salience = memory.get('salience', 0.5)
        memory_id_str = str(memory.get('id', 'UnknownID'))
        memory_timestamp_str = memory.get('timestamp')

        if not memory_timestamp_str:
            logger.warning(f"Memory {memory_id_str} missing timestamp, cannot determine age for deletion.")
            return False

        if memory.get('is_archived') and current_salience < self.deletion_salience_threshold:
            try:
                created_time_naive = datetime.fromisoformat(memory_timestamp_str.replace("Z", ""))
                created_time = created_time_naive.replace(tzinfo=timezone.utc) if created_time_naive.tzinfo is None else created_time_naive.astimezone(timezone.utc)
                age_days = (datetime.now(timezone.utc) - created_time).days
                if age_days >= self.deletion_min_age_days:
                    logger.info(f"Memory {memory_id_str} marked for deletion: archived, low salience ({current_salience:.3f}), age {age_days} days.")
                    return True
            except ValueError:
                logger.warning(f"Could not parse timestamp for deletion check on memory {memory_id_str}: '{memory_timestamp_str}'")
        return False

    async def run_cycle(self) -> None:
        """
        Runs a single cycle of the salience and forgetting process.
        """
        logger.info("--- Starting Salience & Forgetting Cycle ---")

        candidate_memories = await self.get_candidate_memories_for_salience_update()
        if not candidate_memories:
            logger.info("No candidate memories fetched for this cycle (placeholder method). Cycle finished.")
            return

        updated_count = 0; faded_count = 0; archived_count = 0; deleted_count = 0

        for memory_dict in candidate_memories: # Process copies to avoid modifying list during iteration if underlying storage changes
            # Make a mutable copy for processing if MemoryEntry is a TypedDict
            memory: MemoryEntry = memory_dict.copy() # type: ignore

            memory_id = memory.get('id')
            if not memory_id:
                logger.warning("Encountered memory entry without an ID. Skipping.")
                continue

            original_content = memory.get('content') # For checking if fading actually cleared it
            needs_db_update = False

            if await self.update_memory_salience(memory): needs_db_update = True
            if await self.apply_detail_fading(memory): needs_db_update = True; faded_count +=1
            if await self.apply_archival(memory): needs_db_update = True; archived_count +=1

            if await self.should_delete_memory(memory):
                try:
                    if self.memory_storage.delete_entry(memory_id):
                        logger.info(f"Successfully deleted memory {memory_id}.")
                        deleted_count += 1; needs_db_update = False
                    else: logger.error(f"Failed to delete memory {memory_id} from storage.")
                except Exception as e_del: logger.error(f"Error deleting memory {memory_id}: {e_del}", exc_info=True)

            if needs_db_update:
                update_payload: Dict[str, Any] = {
                    'salience': memory.get('salience'),
                    'timestamp_last_salience_update': memory.get('timestamp_last_salience_update'),
                    'is_archived': memory.get('is_archived'),
                    'metadata': memory.get('metadata')
                }
                # Only include content in payload if it was intentionally modified (e.g., faded)
                if memory.get('content') != original_content:
                    update_payload['content'] = memory.get('content')

                try:
                    if self.memory_storage.update_entry(memory_id, update_payload): updated_count += 1
                    else: logger.error(f"Failed to update memory {memory_id} in storage after processing.")
                except Exception as e_upd: logger.error(f"Error updating memory {memory_id}: {e_upd}", exc_info=True)

        logger.info(f"--- Salience & Forgetting Cycle Finished ---")
        logger.info(f"Processed: {len(candidate_memories)}, Updated in DB: {updated_count}, Faded: {faded_count}, Archived: {archived_count}, Deleted: {deleted_count}")

# Example Usage (conceptual)
if __name__ == '__main__':
    import asyncio

    class MockEthosConfig(dict):
        def get(self, key, default=None): # Implement get for EthosConfig compatibility
            return super().get(key, default)

    class MockMemoryStorage: # More detailed mock for testing
        def __init__(self, config): self.memories: Dict[str, MemoryEntry] = {}
        def add_entry(self, entry: MemoryEntry): self.memories[entry['id']] = entry.copy()
        def get_entry(self, entry_id: str) -> Optional[MemoryEntry]: return self.memories.get(entry_id, None) # type: ignore
        def update_entry(self, entry_id: str, updates: Dict) -> bool:
            if entry_id in self.memories: self.memories[entry_id].update(updates); return True
            return False
        def delete_entry(self, entry_id: str) -> bool:
            if entry_id in self.memories: del self.memories[entry_id]; return True
            return False
        def close_connection(self): logger.info("MockMemoryStorage closed.")


    async def main():
        mock_ethos_cfg = MockEthosConfig({ # Using the mock that has .get()
            "memory_db_path": ":memory:",
            "salience_decay_rate_per_day": 0.1, "min_salience_for_decay": 0.05,
            "archival_salience_threshold": 0.2, "deletion_salience_threshold": 0.1,
            "deletion_min_age_days": 10, "detail_fading_salience_threshold": 0.3,
            "salience_max_memories_per_cycle": 5
        })
        memory_storage_instance = MockMemoryStorage(config=mock_ethos_cfg)

        now_iso = datetime.now(timezone.utc).isoformat()
        old_ts_decay_eligible = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat() # For testing decay
        very_old_ts_delete_eligible = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()

        mem1_id = str(uuid.uuid4()); mem2_id = str(uuid.uuid4()); mem3_id = str(uuid.uuid4()); mem4_id = str(uuid.uuid4())

        memory_storage_instance.add_entry(MemoryEntry(id=mem1_id, type="interaction", content="Old memory, eligible for decay", timestamp=old_ts_decay_eligible, salience=0.5, metadata={}, summary_llm="Summary here"))
        memory_storage_instance.add_entry(MemoryEntry(id=mem2_id, type="interaction", content="Recent memory, high salience, no decay expected", timestamp=now_iso, salience=0.9, metadata={}))
        memory_storage_instance.add_entry(MemoryEntry(id=mem3_id, type="interaction", content="Very old, very low salience, for deletion", timestamp=very_old_ts_delete_eligible, salience=0.03, metadata={}, is_archived=True)) # Already archived
        memory_storage_instance.add_entry(MemoryEntry(id=mem4_id, type="interaction", content="Memory for archival test", timestamp=old_ts_decay_eligible, salience=0.1, metadata={}, summary_llm="Summary for archival test"))


        service = SalienceForgettingService(memory_storage_instance, ethos_config=mock_ethos_cfg) # type: ignore

        async def mock_get_candidates() -> List[MemoryEntry]: # Ensure return type matches
            return [
                memory_storage_instance.get_entry(mem1_id), memory_storage_instance.get_entry(mem2_id),
                memory_storage_instance.get_entry(mem3_id), memory_storage_instance.get_entry(mem4_id)
            ] # type: ignore # Bypassing None checks for mock simplicity
        service.get_candidate_memories_for_salience_update = mock_get_candidates

        await service.run_cycle()

        print("\n--- Memory States After Cycle ---")
        for mem_id_str in [mem1_id, mem2_id, mem3_id, mem4_id]:
            entry = memory_storage_instance.get_entry(mem_id_str)
            if entry:
                print(f"ID: {entry.get('id')}, Salience: {entry.get('salience')}, Archived: {entry.get('is_archived')}, Content: '{entry.get('content', '')[:30]}...'")
            else:
                print(f"ID: {mem_id_str} - DELETED")

        memory_storage_instance.close_connection()

    asyncio.run(main())
