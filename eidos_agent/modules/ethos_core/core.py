import asyncio
import logging
from datetime import datetime, timedelta, timezone 
from typing import Dict, List, Any, Optional
import re 
import math
import json
from pathlib import Path
import uuid
import sqlite3
import random
import httpx

from eidos_agent.core.config import Config, EthosConfig, PROJECT_ROOT, LLMConfig
from .memory_storage import MemoryStorage, MemoryEntry
from eidos_agent.utils.logger import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.modules.oneiros_module import OneirosModule
    from eidos_agent.core.connection_manager import ConnectionManager 
    from eidos_agent.modules.pathos_interface import PathosInterface 
    from eidos_agent.modules.logos_core.handler import LogosCore 


try:
    from zoneinfo import ZoneInfo 
except ImportError:
    logger_init = get_logger(__name__) 
    logger_init.warning("zoneinfo module not found. Timezone features relying on IANA names might be limited.")
    ZoneInfo = None # type: ignore


logger = get_logger(__name__)

PERSONA_FILE_PATH = PROJECT_ROOT / "persona" / "pathos_directives.txt"
HEXUS_STATE_FILENAME = "hexus_state.json"

# --- Constants ---
MOOD_VALENCE_BASELINE = 0.0
MOOD_AROUSAL_BASELINE = 0.0
MOOD_MIN = -1.0
MOOD_MAX = 1.0
MOOD_SHIFT_VALENCE_SUCCESS = 0.15
MOOD_SHIFT_AROUSAL_SUCCESS = 0.05
MOOD_SHIFT_VALENCE_FAILURE = -0.2
MOOD_SHIFT_AROUSAL_FAILURE = 0.1
MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE = 0.1
MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE = 0.05
MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE = -0.15
MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE = 0.05

HEXUS_MIN = -1.0
HEXUS_MAX = 1.0

DEFAULT_HEXUS_SCORES = {
    "general_caution": 0.0,
    "user_engagement_proactivity": 0.0,
    "brevity_preference": 0.0,
}

class EthosCore:

    async def get_recent_knowledge_verifications(self, limit: int = 20) -> List[MemoryEntry]:
        """
        Retrieves recent world_knowledge entries that have undergone verification.
        Orders by the last verification attempt timestamp.
        If a fact was updated, attempts to include the content of the new fact.
        """
        logger.debug(f"Fetching recent knowledge verifications. Limit: {limit}")
        
        if limit <= 0:
            return []

        # Store oe_message to check if json_extract failed later
        oe_message_capture = "" 

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            sql_query = """
                SELECT * FROM memories 
                WHERE type = 'world_knowledge' 
                  AND (
                        json_extract(metadata, '$.last_verified_timestamp') IS NOT NULL OR
                        json_extract(metadata, '$.verification_attempt_failed') = 1 OR 
                        json_extract(metadata, '$.verification_attempt_failed') = 'true' OR
                        json_extract(metadata, '$.status') = 'outdated_by_upkeep' 
                      )
                ORDER BY COALESCE(json_extract(metadata, '$.last_verified_timestamp'), timestamp) DESC
                LIMIT ?
            """
            # Added 'outdated_by_upkeep' to the main filter to ensure these are always considered.
            
            params: List[Any] = [limit]
            
            try:
                cursor.execute(sql_query, tuple(params))
            except sqlite3.OperationalError as oe:
                oe_message_capture = str(oe) # Capture the error message
                if "no such function: json_extract" in oe_message_capture.lower():
                    logger.warning("json_extract not available for get_recent_knowledge_verifications query. Fetching more and filtering in Python.")
                    sql_query_fallback = """
                        SELECT * FROM memories 
                        WHERE type = 'world_knowledge'
                        ORDER BY timestamp DESC 
                        LIMIT ? 
                    """
                    cursor.execute(sql_query_fallback, (limit * 5,)) 
                else:
                    raise 

            rows = cursor.fetchall()
            
            verifications: List[MemoryEntry] = []
            for row_data in rows: # Renamed 'row' to 'row_data' to avoid conflict with MemoryEntry key
                entry = self._row_to_entry(row_data) 
                metadata = entry.get('metadata', {}).copy() # Work with a copy
                
                has_verification_timestamp = metadata.get('last_verified_timestamp') is not None
                attempt_failed = metadata.get('verification_attempt_failed') in [True, 'true', 1]
                is_outdated = metadata.get('status') == 'outdated_by_upkeep'

                if "no such function: json_extract" in oe_message_capture.lower():
                    if not (has_verification_timestamp or attempt_failed or is_outdated):
                        continue 

                # If the fact is outdated and superseded, try to fetch the new fact's content
                if is_outdated and metadata.get('superseded_by_fact_id'):
                    superseded_id = metadata['superseded_by_fact_id']
                    logger.debug(f"Fact ID {entry.get('id')} is outdated, superseded by {superseded_id}. Fetching new fact content.")
                    new_fact_entry = self.memory_storage.get_entry(superseded_id) # Synchronous call
                    if new_fact_entry and new_fact_entry.get('content'):
                        metadata['superseding_fact_content'] = new_fact_entry['content']
                        logger.debug(f"Successfully fetched content for superseding fact {superseded_id}.")
                    else:
                        logger.warning(f"Could not fetch content for superseding fact ID {superseded_id}.")
                        metadata['superseding_fact_content'] = "[Content of new fact not found]"
                
                entry['metadata'] = metadata # Update the entry's metadata with the potentially new key
                verifications.append(entry)
            
            if "no such function: json_extract" in oe_message_capture.lower():
                verifications.sort(
                    key=lambda x: (
                        x.get('metadata', {}).get('last_verified_timestamp') or x.get('timestamp', '')
                    ), 
                    reverse=True
                )
            
            logger.info(f"Retrieved {len(verifications[:limit])} knowledge verification entries.")
            return verifications[:limit]

        except Exception as e:
            logger.error(f"Error retrieving recent knowledge verifications: {e}", exc_info=True)
            return []
    
    
    async def get_local_datetime_for_user(self, user_id: str, location_override: Optional[str] = None) -> datetime:
        system_user_ids = ["unknown_user", "default_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "world_knowledge_store", "system_reflection", "system_knowledge_upkeep", "system_curiosity"]
        if not user_id or user_id in system_user_ids:
            return datetime.now(timezone.utc)

        iana_timezone_str: Optional[str] = None

        derived_tz_fact = await self.get_user_fact('derived_iana_timezone', user_id)
        if derived_tz_fact and derived_tz_fact.get('content'):
            try:
                fact_content = json.loads(derived_tz_fact['content'])
                iana_timezone_str = fact_content.get('value')
                if iana_timezone_str:
                    logger.debug(f"Using 'derived_iana_timezone': '{iana_timezone_str}' for user '{user_id}'.")
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON for 'derived_iana_timezone' fact for user '{user_id}'.")

        if not iana_timezone_str:
            location_input_str = location_override
            if not location_input_str:
                location_fact = await self.get_user_fact('preferred_location', user_id)
                if location_fact and location_fact.get('content'):
                    try:
                        fact_content = json.loads(location_fact['content'])
                        location_input_str = fact_content.get('value')
                        logger.debug(f"Retrieved preferred_location '{location_input_str}' for user '{user_id}' to attempt as IANA timezone.")
                    except json.JSONDecodeError:
                        location_input_str = None
            if location_input_str:
                iana_timezone_str = location_input_str 

        if iana_timezone_str and ZoneInfo:
            try:
                target_tz = ZoneInfo(iana_timezone_str)
                logger.info(f"Successfully resolved '{iana_timezone_str}' as IANA timezone for user '{user_id}'.")
                return datetime.now(target_tz)
            except Exception as e:
                logger.warning(
                    f"Could not resolve '{iana_timezone_str}' (from derived_iana_timezone or preferred_location) as an IANA timezone name for user '{user_id}' (Error: {e}). "
                    f"Falling back to UTC for timestamp."
                )
                return datetime.now(timezone.utc)
        elif not ZoneInfo:
            logger.warning("ZoneInfo module not available. Falling back to UTC for timestamp.")
            return datetime.now(timezone.utc)
        else: 
            logger.debug(f"No IANA timezone string available for user '{user_id}'. Falling back to UTC for timestamp.")
            return datetime.now(timezone.utc)
        
    def __init__(self, config: Config):
        self.config = config
        self.ethos_config: EthosConfig = config.get_ethos_config()
        self.memory_storage = MemoryStorage(config)
        self.hexus_state_file_path = self.memory_storage.memory_db_path.parent / HEXUS_STATE_FILENAME

        self.current_mood: Dict[str, float] = {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE}
        self.last_mood_update_time: datetime = datetime.now(timezone.utc)

        self.persona_directives: List[str] = self._load_persona_from_file()
        self.hexus_scores: Dict[str, float] = self._load_hexus_scores()

        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400)
        forgetting_interval_seconds = self.ethos_config.get('forgetting_interval_seconds', reflection_interval * 0.5 if reflection_interval > 0 else 0)
        hexus_decay_interval_seconds = self.ethos_config.get('hexus_decay_interval_seconds', 3600)
        knowledge_upkeep_interval_seconds = self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400) 

        now_utc_init = datetime.now(timezone.utc) 
        self.last_reflection_time = now_utc_init - timedelta(seconds=reflection_interval + 60) if reflection_interval > 0 else now_utc_init
        self.last_forgetting_time = now_utc_init - timedelta(seconds=forgetting_interval_seconds + 60) if forgetting_interval_seconds > 0 else now_utc_init
        self.last_hexus_decay_time: datetime = now_utc_init - timedelta(seconds=hexus_decay_interval_seconds + 60) if hexus_decay_interval_seconds > 0 else now_utc_init
        self.last_knowledge_upkeep_time: datetime = now_utc_init - timedelta(seconds=knowledge_upkeep_interval_seconds + 60) if knowledge_upkeep_interval_seconds > 0 else now_utc_init

        self.oneiros_module: Optional['OneirosModule'] = None
        self.connection_manager: Optional['ConnectionManager'] = None 
        self.pathos_interface: Optional['PathosInterface'] = None 
        self.logos_core: Optional['LogosCore'] = None 

        self.hexus_scores_changed_during_reflection = False 
        logger.info("EthosCore initialized.")

    def set_connection_manager(self, manager: 'ConnectionManager'):
        self.connection_manager = manager
        logger.info("EthosCore received ConnectionManager instance.")

    def set_pathos_interface(self, pathos_interface: 'PathosInterface'):
        self.pathos_interface = pathos_interface
        logger.info("EthosCore received PathosInterface instance.")

    async def close_memory_connection(self):
        logger.info("Attempting to save Hexus scores before closing memory...")
        self._save_hexus_scores()
        logger.info("Closing memory storage connection...")
        self.memory_storage.close_connection() 
        logger.info("EthosCore closed memory connection.")

    async def record_proactive_action(self, user_id: str, action_type: str, details: Optional[Dict[str, Any]] = None):
        if not user_id or not action_type:
            logger.warning(f"Attempted to record proactive action with missing user_id ('{user_id}') or action_type ('{action_type}'). Skipping.")
            return
        logger.info(f"Recording proactive action '{action_type}' for user '{user_id}'. Details: {details}")
        timestamp_now_iso = datetime.now(timezone.utc).isoformat()
        metadata = {
            "user_id": user_id, "action_type": action_type,
            "action_timestamp": timestamp_now_iso, "action_details": details or {}
        }
        await self.add_memory_entry({
            "type": "proactive_action_record",
            "content": f"Proactive action '{action_type}' for user '{user_id}' at {timestamp_now_iso}. Details: {json.dumps(details or {})}",
            "metadata": metadata, "salience": 0.05 
        }, user_id_context=user_id)

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]:
        if not user_id or not action_type: return None
        logger.debug(f"Checking last proactive action time for user '{user_id}', type '{action_type}'.")
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql_query = "SELECT timestamp FROM memories WHERE type = 'proactive_action_record' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.action_type') = ? ORDER BY timestamp DESC LIMIT 1"
            try:
                cursor.execute(sql_query, (user_id, action_type))
                row = cursor.fetchone()
                if row and row["timestamp"]:
                    dt_obj = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                    return dt_obj.replace(tzinfo=timezone.utc)
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" in str(oe).lower():
                    logger.warning("json_extract not available. Proactive action time check less efficient (full scan).")
                    cursor.execute("SELECT timestamp, metadata FROM memories WHERE type = 'proactive_action_record' ORDER BY timestamp DESC")
                    for r_row in cursor.fetchall():
                        try:
                            meta = json.loads(r_row["metadata"])
                            if meta.get('user_id') == user_id and meta.get('action_type') == action_type:
                                dt_obj = datetime.fromisoformat(r_row["timestamp"].replace("Z", "+00:00"))
                                return dt_obj.replace(tzinfo=timezone.utc)
                        except (json.JSONDecodeError, TypeError): continue 
                else:
                    logger.error(f"SQLite OperationalError in get_last_proactive_action_time: {oe}", exc_info=True)
                    raise
            return None 
        except Exception as e:
            logger.error(f"Error in get_last_proactive_action_time for user '{user_id}', action '{action_type}': {e}", exc_info=True)
            return None

    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        logger.debug(f"Fetching queued discussion points for user '{user_id}', limit {limit}.")
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = """
                SELECT * FROM memories
                WHERE type = 'queued_discussion_point'
                  AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = 'system_oneiros')
                  AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending')
                ORDER BY salience DESC, timestamp DESC LIMIT ?
            """
            try:
                cursor.execute(sql, (user_id, limit * 5)) 
            except sqlite3.OperationalError:
                 logger.warning("json_extract not available for queued_discussion_points. Fetching all and filtering.")
                 cursor.execute("SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY salience DESC, timestamp DESC LIMIT 100") 

            rows = cursor.fetchall()
            points = []
            for row in rows:
                entry = self._row_to_entry(row) 
                meta = entry.get('metadata', {})
                meta_user_id = meta.get('user_id')
                status = meta.get('status', 'pending') 

                if status == 'pending' and (meta_user_id == user_id or meta_user_id == 'system_oneiros'):
                    points.append(entry)
                if len(points) >= limit: break 

            logger.debug(f"Found {len(points)} queued discussion points for user '{user_id}'.")
            return points
        except Exception as e:
            logger.error(f"Error fetching queued discussion points: {e}", exc_info=True)
            return []

    async def mark_queued_point_offered(self, memory_id: str, user_id: Optional[str] = None):
        if not memory_id: return
        logger.info(f"Marking queued discussion point '{memory_id}' as offered for user '{user_id}'.")
        entry = self.memory_storage.get_entry(memory_id) 
        if entry and entry.get('type') == 'queued_discussion_point':
            metadata = entry.get('metadata', {}).copy() 
            metadata['status'] = 'offered' 
            metadata['last_offered_timestamp'] = datetime.now(timezone.utc).isoformat()
            if user_id: metadata['last_offered_to_user_id'] = user_id
            self.memory_storage.update_entry(memory_id, {"metadata": metadata}) 
        else:
            logger.warning(f"Could not find queued_discussion_point with ID '{memory_id}' to mark as offered.")

    async def get_recent_interaction_topics(self, user_id: str, num_interactions: int = 1) -> List[str]:
        system_user_ids = ["unknown_user", "default_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "world_knowledge_store", "system_reflection", "system_knowledge_upkeep", "system_curiosity"]
        if not user_id or user_id in system_user_ids:
            return []
        if num_interactions <= 0:
             return []

        logger.debug(f"EthosCore retrieving {num_interactions} most recent interaction topics for user '{user_id}'.")
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = """
                SELECT content, timestamp FROM memories
                WHERE type = 'interaction' AND json_extract(metadata, '$.user_id') = ?
                ORDER BY timestamp DESC LIMIT ?
            """
            try:
                cursor.execute(sql, (user_id, num_interactions))
                rows = cursor.fetchall()
            except sqlite3.OperationalError as oe:
                 if "no such function: json_extract" in str(oe).lower():
                     logger.warning("json_extract not available for recent interaction topics query. Falling back to Python filter.")
                     fallback_sql = "SELECT content, timestamp, metadata FROM memories WHERE type = 'interaction' ORDER BY timestamp DESC LIMIT 100" 
                     cursor.execute(fallback_sql)
                     rows = []
                     filtered_count = 0
                     for r_row in cursor.fetchall():
                          try:
                              meta = json.loads(r_row["metadata"])
                              if meta.get('user_id') == user_id:
                                   rows.append(r_row)
                                   filtered_count += 1
                                   if filtered_count >= num_interactions: break 
                          except (json.JSONDecodeError, TypeError): continue 
                 else:
                     logger.error(f"SQLite OperationalError in get_recent_interaction_topics: {oe}", exc_info=True)
                     return [] 

            topics = []
            for row in rows:
                 content = row['content']
                 if content and isinstance(content, str):
                      cleaned_content = re.sub(r"\[System note: .*?\]\s*", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
                      cleaned_content = re.sub(r"Tools Used: .*", "", cleaned_content, flags=re.DOTALL).strip()
                      user_part_match = re.search(r"^User \(.*?\):\s*(.*?)(?:\s*\[Image Included\]|\s*\[Vision System Output:.*?\]|\s*\[Document content included in input\.\])?(?:\s*Pathos:|$)", cleaned_content, re.DOTALL)
                      if user_part_match:
                          topic_text = user_part_match.group(1).strip()
                          if topic_text: topics.append(topic_text)
                      elif cleaned_content:
                          topics.append(cleaned_content.split('\n')[0][:100].strip() + '...')
            logger.debug(f"Retrieved {len(topics)} recent interaction topics for user '{user_id}'.")
            return topics
        except Exception as e:
            logger.error(f"Error in get_recent_interaction_topics for user '{user_id}': {e}", exc_info=True)
            return []

    def _load_persona_from_file(self) -> List[str]:
        logger.info(f"Loading persona directives from: {PERSONA_FILE_PATH}")
        default_content = "# --- Pathos Persona Directives ---\nYour name is Pathos.\n..."
        try:
            if not PERSONA_FILE_PATH.is_file():
                logger.warning(f"Persona file not found at {PERSONA_FILE_PATH}. Creating with default content.")
                PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f: f.write(default_content)
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]

            with open(PERSONA_FILE_PATH, 'r', encoding='utf-8') as f:
                directives = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            if not directives:
                logger.warning(f"Persona file {PERSONA_FILE_PATH} is empty or only comments. Using default content.")
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]
            logger.info(f"Successfully loaded {len(directives)} persona directives.")
            return directives
        except Exception as e:
            logger.error(f"Error loading persona file {PERSONA_FILE_PATH}: {e}", exc_info=True)
            logger.warning("Using default persona content due to error.")
            return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]

    def _load_hexus_scores(self) -> Dict[str, float]:
        defaults = DEFAULT_HEXUS_SCORES.copy()
        if self.hexus_state_file_path.is_file():
            try:
                with open(self.hexus_state_file_path, 'r', encoding='utf-8') as f:
                    loaded_scores = json.load(f)
                if isinstance(loaded_scores, dict) and \
                   all(key in defaults.keys() for key in loaded_scores.keys()) and \
                   all(isinstance(value, (int, float)) for value in loaded_scores.values()):
                    for key, value in loaded_scores.items():
                        if key in defaults:
                            defaults[key] = value
                    logger.info(f"Successfully loaded Hexus scores from {self.hexus_state_file_path}")
                    return defaults
                else:
                    logger.warning(f"Hexus state file {self.hexus_state_file_path} has invalid format, unexpected keys, or invalid value types. Using defaults for missing keys and current values for valid ones.")
            except (json.JSONDecodeError, IOError, Exception) as e:
                logger.error(f"Error loading Hexus state from {self.hexus_state_file_path}: {e}. Using defaults.", exc_info=True)
        else:
            logger.info(f"Hexus state file not found at {self.hexus_state_file_path}. Using default scores and creating file.")
        try:
            self._save_hexus_scores(defaults)
        except Exception as e_save:
            logger.error(f"Failed to save initial/default Hexus scores: {e_save}", exc_info=True)
        return defaults 

    def _save_hexus_scores(self, scores_to_save: Optional[Dict[str, float]] = None):
        scores = scores_to_save if scores_to_save is not None else self.hexus_scores
        try:
            self.hexus_state_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.hexus_state_file_path, 'w', encoding='utf-8') as f:
                float_scores = {k: float(v) for k, v in scores.items()}
                json.dump(float_scores, f, indent=4)
            logger.info(f"Hexus scores saved successfully to {self.hexus_state_file_path}")
        except (IOError, TypeError, Exception) as e:
            logger.error(f"Failed to save Hexus scores to {self.hexus_state_file_path}: {e}", exc_info=True)

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        metadata = {}
        metadata_str = row['metadata'] if 'metadata' in row.keys() else None
        if metadata_str:
            try: metadata = json.loads(metadata_str)
            except json.JSONDecodeError: logger.warning(f"Could not decode metadata JSON for entry {row.get('id', 'UNKNOWN')}: {metadata_str}") 

        entry_id = row['id']
        timestamp = row['timestamp']
        entry_type = row['type']
        content = row['content']
        embedding_blob = row['embedding'] if 'embedding' in row.keys() else None
        salience = row['salience'] if 'salience' in row.keys() else None

        return MemoryEntry(
            id=entry_id,
            timestamp=timestamp,
            type=entry_type,
            content=content,
            embedding=self.memory_storage._deserialize_embedding(embedding_blob), 
            metadata=metadata,
            salience=salience
        )


    async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry: 
        if 'content' not in entry_data or 'type' not in entry_data:
            raise ValueError("Memory entry must contain 'content' and 'type'")

        entry_id = str(entry_data.get('id', uuid.uuid4()))
        content = str(entry_data['content'])
        entry_type = str(entry_data['type'])
        timestamp = entry_data.get('timestamp', datetime.now(timezone.utc).isoformat()) 
        metadata = entry_data.get('metadata', {}).copy() 
        salience = entry_data.get('salience') 

        system_user_ids_for_metadata = ["system_document", "system_briefing", "world_knowledge_store", "system_oneiros", "system_reflection", "api_guest_user", "unknown_user", "system_knowledge_upkeep", "system_curiosity"]

        if user_id_context is not None:
             if 'user_id' not in metadata or \
                (user_id_context in system_user_ids_for_metadata) or \
                (metadata.get('user_id') is None and user_id_context not in system_user_ids_for_metadata) or \
                (user_id_context not in system_user_ids_for_metadata and \
                 metadata.get('user_id') in system_user_ids_for_metadata and \
                 user_id_context != metadata.get('user_id')):
                metadata['user_id'] = user_id_context
             elif user_id_context not in system_user_ids_for_metadata and \
                  metadata.get('user_id') not in system_user_ids_for_metadata and \
                  user_id_context != metadata.get('user_id'):
                 logger.debug(f"Overriding metadata user_id '{metadata.get('user_id')}' with user_id_context '{user_id_context}' for entry {entry_id}.")
                 metadata['user_id'] = user_id_context


        embedding = None
        embedding_blob = None
        if self.memory_storage.embedder and isinstance(content, str) and content.strip() and entry_type not in ['pending_context_document', 'proactive_action_record']: 
            try:
                max_embed_len = self.ethos_config.get('embedding_max_text_length', 2560) 
                embedding = self.memory_storage.embedder.encode(content[:max_embed_len]).tolist() 
                embedding_blob = self.memory_storage._serialize_embedding(embedding) 
            except Exception as e:
                logger.error(f"Failed to generate embedding for content: {content[:50]}... Error: {e}")

        new_entry = MemoryEntry(
            id=entry_id, timestamp=timestamp, type=entry_type, content=content,
            embedding=embedding, metadata=metadata, salience=salience
        )

        try:
            conn = self.memory_storage._get_connection() 
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memories (id, timestamp, type, content, embedding, metadata, salience)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    timestamp=excluded.timestamp, type=excluded.type, content=excluded.content,
                    embedding=excluded.embedding, metadata=excluded.metadata, salience=excluded.salience
            """, (entry_id, timestamp, entry_type, content, embedding_blob, json.dumps(metadata), salience))
            conn.commit()
            logger.debug(f"Added/Updated memory entry {entry_id} of type {entry_type} in DB.")
            return new_entry 
        except sqlite3.Error as e:
            logger.error(f"Error adding/updating memory entry {entry_id} in DB: {e}", exc_info=True)
            raise 


    async def retrieve_relevant_memories(
        self, query: str, top_k: int = 5, min_salience: float = 0.1,
        allowed_types: Optional[List[str]] = None, user_id_context: Optional[str] = None
    ) -> List[MemoryEntry]:
        logger.debug(f"Retrieving memories for query: '{query[:50]}...', User: {user_id_context}, Types: {allowed_types}, TopK: {top_k}")
        if not query.strip() and not allowed_types:
            logger.warning("Attempted RAG with empty query and no type filter. Returning empty list.")
            return []
        try:
            similar_results_tuples = self.memory_storage.find_similar(
                query_text=query, top_k=top_k * 5, 
                allowed_types=allowed_types, threshold=0.3 
            )
            all_candidate_entries = [entry for score, entry in similar_results_tuples]
            system_user_ids = ["system_document", "system_briefing", "world_knowledge_store", "system_oneiros", "system_reflection", "system_knowledge_upkeep", "system_curiosity", "api_guest_user", "unknown_user", None]


            if user_id_context and user_id_context not in ["default_user"] + system_user_ids: # Simplified check
                current_user_candidates = []
                other_candidates = []
                for entry in all_candidate_entries:
                    entry_user_id = entry.get('metadata', {}).get('user_id')
                    if entry_user_id == user_id_context or entry_user_id in system_user_ids: 
                        current_user_candidates.append(entry)
                    else:
                        other_candidates.append(entry)
                combined_candidates = current_user_candidates + other_candidates
            else:
                combined_candidates = all_candidate_entries

            filtered_by_salience = [e for e in combined_candidates if (e.get('salience') if e.get('salience') is not None else 0) >= min_salience]

            def sort_key(entry: MemoryEntry):
                entry_type = entry.get('type')
                entry_user_id = entry.get('metadata', {}).get('user_id')
                is_current_user_fact = (entry_type == 'user_fact' and entry_user_id == user_id_context)
                is_world_knowledge = (entry_type == 'world_knowledge')
                is_context_summary = (entry_type == 'context_summary' and (entry_user_id == user_id_context or entry_user_id in ["system_oneiros", "system_reflection"])) 
                is_current_user_interaction = (entry_user_id == user_id_context and entry_type != 'user_fact')
                is_document_chunk = (entry_type == 'document_chunk')
                is_learned_correction = (entry_type == 'learned_correction' or entry_type == 'learned_feedback_insight' or entry_type == 'suggestion_reflection') # Include new learning types
                is_feedback = (entry_type == 'feedback') 

                priority_score = 0
                if is_current_user_fact: priority_score = 7 
                elif is_learned_correction: priority_score = 6 
                elif is_feedback: priority_score = 5 
                elif is_context_summary: priority_score = 4
                elif is_world_knowledge: priority_score = 3
                elif is_document_chunk: priority_score = 2
                elif is_current_user_interaction: priority_score = 1
                
                salience_for_sort = entry.get('salience') if entry.get('salience') is not None else 0.0
                return (priority_score, salience_for_sort, entry.get('timestamp', ''))

            ranked_memories = sorted(filtered_by_salience, key=sort_key, reverse=True)[:top_k]
            logger.debug(f"Retrieved {len(ranked_memories)} relevant memories for user '{user_id_context}'.")
            return ranked_memories
        except Exception as e:
            logger.error(f"Error retrieving relevant memories: {e}", exc_info=True)
            return []


    async def get_user_fact(self, attribute_key: str, user_id: str) -> Optional[MemoryEntry]:
        normalized_key = attribute_key.lower().replace(" ", "_").strip()
        system_user_ids = ["unknown_user", "default_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "world_knowledge_store", "system_reflection", "system_knowledge_upkeep", "system_curiosity"]
        if not user_id or user_id in system_user_ids: 
            return None
        if not normalized_key:
             logger.warning(f"Attempted to retrieve user_fact with empty key for user '{user_id}'.")
             return None

        logger.debug(f"EthosCore retrieving user_fact: key='{normalized_key}', user_id='{user_id}'")
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') = ? ORDER BY timestamp DESC LIMIT 1"
            try:
                cursor.execute(sql, (user_id, normalized_key))
                row = cursor.fetchone()
                if row: return self._row_to_entry(row)
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" in str(oe).lower():
                    logger.warning("json_extract not available. Falling back to Python filter for get_user_fact.")
                    cursor.execute("SELECT * FROM memories WHERE type = 'user_fact' ORDER BY timestamp DESC")
                    for r_row in cursor.fetchall():
                        entry = self._row_to_entry(r_row) 
                        meta = entry.get('metadata', {})
                        if meta.get('user_id') == user_id and meta.get('fact_attribute_key') == normalized_key:
                            return entry
                else:
                    logger.error(f"SQLite OperationalError in get_user_fact (query part): {oe}", exc_info=True)
                    return None
            return None
        except Exception as e:
            logger.error(f"Error in get_user_fact: {e}", exc_info=True)
            return None

    async def add_document_chunks(self, doc_id: str, filename: str, chunks: List[str]):
        if not chunks: logger.warning(f"No chunks provided for document '{filename}'."); return
        logger.info(f"Adding {len(chunks)} chunks for document '{filename}' (ID: {doc_id})...")
        user_id_context_for_docs = "system_document"
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip(): continue
            await self.add_memory_entry(
                entry_data={
                    "type": "document_chunk", "content": chunk_text, "id": f"{doc_id}_chunk_{i}",
                    "metadata": {"source_document_id": doc_id, "source_document_name": filename, "chunk_index": i, "total_chunks": len(chunks), "user_id": user_id_context_for_docs}, 
                    "salience": 0.4
                },
                user_id_context=user_id_context_for_docs 
            )
        logger.info(f"Finished adding chunks for document '{filename}'.")

    async def _call_summarization_llm(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        llm_role_str = self.ethos_config.get('summarization_llm_role', 'LOGOS_TECHNE') 
        llm_config = self.config.get_llm_config(llm_role_str) # type: ignore

        if not llm_config or not llm_config.get('url'):
            logger.error(f"Utility LLM call (role: {llm_role_str}): URL not configured.")
            return f"[LLM URL for role '{llm_role_str}' not configured]" 

        try:
            timeout_s = llm_config.get('timeout', 120) 
            async with httpx.AsyncClient(timeout=float(timeout_s)) as client:
                api_url = f"{llm_config['url']}/chat/completions"
                headers = {"Content-Type": "application/json"}
                api_key = llm_config.get('api_key')
                if api_key and api_key.lower() not in ['lm-studio', 'ollama', '']:
                    headers["Authorization"] = f"Bearer {api_key}"

                try: 
                    default_max_tokens = 512 if "summarize" in messages[0].get("content","").lower() else 256 
                    max_tokens_val = int(llm_config.get('max_tokens', default_max_tokens))
                except (ValueError, TypeError): 
                    max_tokens_val = default_max_tokens
                    logger.warning(f"Invalid max_tokens for utility LLM, using {max_tokens_val}.")

                payload: Dict[str, Any] = {
                    "model": llm_config.get('model'), 
                    "messages": messages, 
                    "temperature": llm_config.get('temperature', 0.3), 
                    "max_tokens": max_tokens_val
                }
                for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
                    if param_val := llm_config.get(param): # type: ignore
                        payload[param] = param_val
                if not payload.get('model'):
                    del payload['model']

                llm_name_for_log = llm_config.get('model', f'Utility LLM ({llm_role_str})')
                sys_prompt_log = messages[0]['content'][:100] + "..." if len(messages) > 0 and messages[0].get('content') and len(messages[0]['content']) > 100 else messages[0].get('content','') if len(messages) > 0 else "N/A"
                user_prompt_log = messages[1]['content'][:100] + "..." if len(messages) > 1 and messages[1].get('content') and len(messages[1]['content']) > 100 else messages[1].get('content','') if len(messages) > 1 else "N/A"
                logger.debug(f"Calling LLM '{llm_name_for_log}' at {api_url} for internal task. System Prompt: {sys_prompt_log} User Prompt: {user_prompt_log}")


                response = await client.post(api_url, headers=headers, json=payload)
                response.raise_for_status() 
                result_json = response.json()

                if result_json.get("choices") and len(result_json["choices"]) > 0:
                     if message_data := result_json["choices"][0].get("message"): 
                         if llm_response_content := message_data.get("content"): 
                             if isinstance(llm_response_content, str):
                                 logger.debug(f"LLM '{llm_name_for_log}' raw response: {llm_response_content[:100]}...")
                                 return llm_response_content.strip()

                logger.warning(f"Unexpected LLM response format from '{llm_name_for_log}': {result_json}")
                return f"[Received unexpected response format from {llm_name_for_log}]"
        except httpx.TimeoutException as e:
            logger.error(f"Timeout calling LLM '{llm_name_for_log}' for internal task: {e}")
            return f"[Timeout connecting to LLM '{llm_name_for_log}': {e}]"
        except httpx.RequestError as e:
            logger.error(f"HTTP request failed calling LLM '{llm_name_for_log}' for internal task: {e}")
            return f"[Failed to connect to LLM '{llm_name_for_log}': {e}]"
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM '{llm_name_for_log}' error ({e.response.status_code}) for internal task: {e.response.text[:500]}")
            return f"[LLM '{llm_name_for_log}' API error ({e.response.status_code}): {e.response.text[:200]}]"
        except json.JSONDecodeError as e:
            response_text_for_log = response.text[:500] if 'response' in locals() and hasattr(response, 'text') else 'N/A'
            logger.error(f"Failed to decode JSON response from LLM '{llm_name_for_log}'. Response: {response_text_for_log}. Error: {e}")
            return f"[Invalid JSON response from LLM '{llm_name_for_log}': {e}]"
        except Exception as e:
            logger.error(f"Error processing response from LLM '{llm_name_for_log}' for internal task: {e}", exc_info=True)
            return f"[Failed to process response from LLM '{llm_name_for_log}': {e}]"


    async def _run_memory_summarization(self):
        if not self.ethos_config.get('enable_memory_summarization', False):
            logger.debug("Memory summarization disabled in config.")
            return
        logger.info("Reflection: Starting memory summarization...")
        try:
            min_mem_cluster = self.ethos_config.get('summarization_cluster_min_memories', 5)
            max_mem_cluster = self.ethos_config.get('summarization_max_memories_per_cluster', 15)
            max_text_len = self.ethos_config.get('summarization_max_text_length_for_prompt', 10000)
            max_days = self.ethos_config.get('summarization_max_days_to_consider', 30)

            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            since_timestamp = (datetime.now(timezone.utc) - timedelta(days=max_days)).isoformat()

            summarizable_types = ['interaction', 'world_knowledge', 'document_chunk', 'user_fact', 'learned_correction', 'feedback', 'learned_feedback_insight', 'suggestion_reflection'] # Added new learning types

            sql_memories = f"SELECT * FROM memories WHERE type IN ({','.join('?' for _ in summarizable_types)}) AND timestamp >= ? AND (json_extract(metadata, '$.summarized_by_reflection') IS NULL OR json_extract(metadata, '$.summarized_by_reflection') = 0) ORDER BY json_extract(metadata, '$.user_id'), timestamp ASC" 
            try:
                cursor.execute(sql_memories, tuple(summarizable_types + [since_timestamp]))
            except sqlite3.OperationalError:
                 logger.warning("json_extract not available for summarization query. Fetching more and filtering.")
                 sql_fallback = f"SELECT * FROM memories WHERE type IN ({','.join('?' for _ in summarizable_types)}) AND timestamp >= ? ORDER BY timestamp ASC LIMIT 1000" 
                 cursor.execute(sql_fallback, tuple(summarizable_types + [since_timestamp]))


            all_relevant_rows = cursor.fetchall()
            memories_by_key: Dict[str, List[MemoryEntry]] = {} 

            for row in all_relevant_rows:
                entry = self._row_to_entry(row) 
                if entry.get('metadata',{}).get('summarized_by_reflection'): continue

                key = "general_knowledge" 
                entry_type = entry.get('type')
                if entry_type in ['interaction', 'user_fact', 'feedback', 'learned_correction', 'learned_feedback_insight', 'suggestion_reflection']: 
                    user_id = entry.get('metadata', {}).get('user_id')
                    if user_id and user_id not in ["unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing", "system_reflection", "world_knowledge_store", "system_knowledge_upkeep", "system_curiosity", None]: 
                        key = f"user_{user_id}"
                    elif user_id in ["system_document", "system_briefing", "world_knowledge_store", "system_reflection", "system_knowledge_upkeep", "system_curiosity", None]: 
                         key = "general_knowledge"
                    
                if key not in memories_by_key: memories_by_key[key] = []
                memories_by_key[key].append(entry)

            for key, memories_list in memories_by_key.items():
                if len(memories_list) < min_mem_cluster:
                    logger.debug(f"Skipping summarization for key '{key}': only {len(memories_list)} memories found (min required: {min_mem_cluster}).")
                    continue

                logger.info(f"Attempting to summarize {len(memories_list)} memories for key '{key}'.")
                memories_list.sort(key=lambda x: x.get('timestamp', '')) 

                for i in range(0, len(memories_list), max_mem_cluster):
                    chunk_to_summarize = memories_list[i:i+max_mem_cluster]
                    if len(chunk_to_summarize) < min_mem_cluster :
                         logger.debug(f"Skipping small trailing chunk ({len(chunk_to_summarize)} memories) for key '{key}'.")
                         continue 

                    summarization_prompt_content = ""
                    source_memory_ids_chunk = []
                    current_len = 0
                    for mem in chunk_to_summarize:
                        content_to_add = mem.get('content', '')
                        # For feedback types, try to get a more descriptive summary if content is JSON
                        if mem.get('type') in ['feedback', 'learned_correction', 'learned_feedback_insight', 'suggestion_reflection']:
                            try:
                                fb_payload_summ = json.loads(content_to_add)
                                if isinstance(fb_payload_summ, dict): # Ensure it's a dict
                                    fb_text_prev = fb_payload_summ.get('feedback_text', fb_payload_summ.get('user_suggestion_or_feedback_text', 'N/A'))[:100]
                                    fb_type_prev = fb_payload_summ.get('feedback_type', fb_payload_summ.get('original_feedback_type', 'N/A'))
                                    rating_prev = fb_payload_summ.get('rating', fb_payload_summ.get('original_feedback_rating', 'N/A'))
                                    content_to_add = f"Feedback Type: {fb_type_prev}, Rating: {rating_prev}, Text: '{fb_text_prev}'"
                                # If it's not a dict (e.g. already a summary string), use as is
                            except json.JSONDecodeError:
                                pass # Use content_to_add as is if not JSON or parse error
                        
                        content_part = f"Type: {mem.get('type')}, Time: {mem.get('timestamp')}, User: {mem.get('metadata',{}).get('user_id','unknown')}\nContent: {content_to_add}\n---\n"


                        if current_len + len(content_part) > max_text_len:
                             logger.debug(f"Truncating memory chunk for key '{key}' due to max_text_len ({max_text_len}).")
                             break 
                        summarization_prompt_content += content_part
                        current_len += len(content_part)
                        if mem_id := mem.get('id'): source_memory_ids_chunk.append(mem_id)

                    if not summarization_prompt_content:
                         logger.warning(f"No content generated for summarization prompt for key '{key}', chunk starting at index {i}.")
                         continue

                    system_s_prompt = (
                        "You are a summarization assistant. Based on the following collection of memories (interactions, facts, document excerpts, feedback, learned lessons), "
                        "provide a concise summary of the main themes, key information, significant feedback points, or important topics. "
                        "The summary should be factual and brief. This summary will be used as a condensed memory for an AI agent."
                    )
                    user_s_prompt = f"Please summarize these memories related to '{key}':\n\n{summarization_prompt_content}"
                    summary_messages = [{"role": "system", "content": system_s_prompt}, {"role": "user", "content": user_s_prompt}]
                    generated_summary = await self._call_summarization_llm(summary_messages)

                    if generated_summary and not generated_summary.startswith("["): 
                        logger.info(f"Generated summary for key '{key}': {generated_summary[:100]}...")
                        summary_user_id = key.split("user_")[-1] if key.startswith("user_") else "system_reflection"
                        await self.add_memory_entry({ 
                            "type": "context_summary", "content": generated_summary,
                            "metadata": {
                                "user_id": summary_user_id, "source": "ethos_reflection_summarization",
                                "summarized_memory_ids": source_memory_ids_chunk,
                                "summarization_key": key,
                                "summarization_timestamp": datetime.now(timezone.utc).isoformat()
                            }, "salience": 0.85
                        }, user_id_context=summary_user_id) 
                        for mem_id_to_mark in source_memory_ids_chunk:
                            original_entry = self.memory_storage.get_entry(mem_id_to_mark)
                            if original_entry:
                                meta_to_update = original_entry.get('metadata', {}).copy() 
                                meta_to_update['summarized_by_reflection'] = True
                                self.memory_storage.update_entry(mem_id_to_mark, {'metadata': meta_to_update})

                    elif generated_summary: 
                         logger.warning(f"Summarization LLM returned error for key '{key}': {generated_summary}")
                    else: logger.warning(f"Failed to generate summary (empty response) for key '{key}', chunk starting with ID {source_memory_ids_chunk[0] if source_memory_ids_chunk else 'N/A'}.")
        except Exception as e:
            logger.error(f"Error during memory summarization: {e}", exc_info=True)


    async def get_recent_dreams(self, user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        """
        Retrieves recent dream entries.
        If user_id_context is provided and is a specific user, it fetches dreams
        associated with that user (if any) AND system-generated dreams.
        Otherwise, it fetches system-generated dreams.
        """
        logger.debug(f"Fetching recent dreams. User context: {user_id_context}, Limit: {limit}")
        
        # Define what constitutes a "dream" entry for querying
        # Based on OneirosModule, these are 'queued_discussion_point' with a specific source.
        dream_type = "queued_discussion_point"
        dream_source = "oneiros_dream_cycle"

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            # Build the query dynamically based on user_id_context
            # We want to fetch more than the limit initially if we need to do Python-side filtering for user context
            # because json_extract for 'OR' conditions on different metadata user_ids can be complex or inefficient.
            
            # Fetch candidates, then filter. This is simpler than a very complex SQL.
            # Order by timestamp to get recent ones first.
            sql_query = """
                SELECT * FROM memories 
                WHERE type = ? 
                  AND json_extract(metadata, '$.source') = ?
                ORDER BY timestamp DESC 
                LIMIT ? 
            """
            # Fetch a bit more to allow for filtering if a specific user context is given,
            # as some might be system_oneiros and some for the user.
            fetch_limit = limit * 3 if user_id_context and user_id_context not in ["system_oneiros", None] else limit

            try:
                cursor.execute(sql_query, (dream_type, dream_source, fetch_limit))
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" in str(oe).lower():
                    logger.warning("json_extract not available for get_recent_dreams query. Fetching more and filtering in Python.")
                    # Fallback query without json_extract for 'source'
                    sql_query_fallback = """
                        SELECT * FROM memories 
                        WHERE type = ? 
                        ORDER BY timestamp DESC 
                        LIMIT ?
                    """
                    cursor.execute(sql_query_fallback, (dream_type, fetch_limit * 2)) # Fetch even more for Python filtering
                else:
                    raise # Re-raise other operational errors

            rows = cursor.fetchall()
            
            processed_dreams: List[MemoryEntry] = []
            for row in rows:
                entry = self._row_to_entry(row)
                metadata = entry.get('metadata', {})

                # Python-side filter if json_extract for source failed
                if 'source' not in metadata or metadata.get('source') != dream_source:
                    if "no such function: json_extract" in str(getattr(oe, 'message', '')).lower(): # Check if fallback was used
                        continue # Skip if source doesn't match during fallback

                entry_user_id = metadata.get('user_id')

                if user_id_context and user_id_context not in ["system_oneiros", "unknown_user", "api_guest_user", None]:
                    # If specific user, include their dreams AND system_oneiros dreams
                    if entry_user_id == user_id_context or entry_user_id == "system_oneiros":
                        processed_dreams.append(entry)
                else:
                    # If no specific user context, or context is system_oneiros, only include system_oneiros dreams
                    if entry_user_id == "system_oneiros":
                        processed_dreams.append(entry)
            
            # Ensure final list is sorted by timestamp (already done by SQL but good for Python filtered list)
            # and respects the original limit
            processed_dreams.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            logger.info(f"Retrieved {len(processed_dreams[:limit])} dream entries for context '{user_id_context}'.")
            return processed_dreams[:limit]

        except Exception as e:
            logger.error(f"Error retrieving recent dreams: {e}", exc_info=True)
            return []
    
    async def run_reflection_cycle(self):
        if not any([self.config.ENABLE_LEARNING_FROM_FEEDBACK,
                    self.config.ENABLE_CURIOUSITY, 
                    self.ethos_config.get('enable_memory_summarization', False)]):
            logger.debug("Reflection cycle skipped: relevant features (feedback, curiosity, summarization) disabled.")
            return

        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400)
        if reflection_interval <= 0:
            logger.debug("Reflection cycle skipped: interval is zero or negative.")
            return

        now = datetime.now(timezone.utc)
        if now - self.last_reflection_time < timedelta(seconds=reflection_interval):
            logger.debug("Reflection cycle skipped: not enough time passed since last run.")
            return

        logger.info("--- Ethos: Starting Reflection Cycle ---")
        self.last_reflection_time = now
        self.hexus_scores_changed_during_reflection = False 

        # 1. Process User Feedback
        if self.config.ENABLE_LEARNING_FROM_FEEDBACK:
            logger.info("Reflection: Processing user feedback...")
            try:
                conn = self.memory_storage._get_connection(); cursor = conn.cursor()
                sql_feedback = "SELECT * FROM memories WHERE type = 'feedback' AND (json_extract(metadata, '$.processed_by_reflection') IS NULL OR json_extract(metadata, '$.processed_by_reflection') = 0) ORDER BY timestamp DESC LIMIT 100"
                try: cursor.execute(sql_feedback)
                except sqlite3.OperationalError:
                    logger.warning("json_extract not available for feedback query. Fetching all feedback and filtering.")
                    sql_fallback = "SELECT * FROM memories WHERE type = 'feedback' ORDER BY timestamp DESC LIMIT 500" 
                    cursor.execute(sql_fallback)

                feedback_rows = cursor.fetchall()
                feedback_entries_to_process = [self._row_to_entry(row) for row in feedback_rows if not row['metadata'] or not json.loads(row['metadata']).get('processed_by_reflection')]

                logger.debug(f"Found {len(feedback_entries_to_process)} unprocessed feedback entries for reflection.")
                HEXUS_ADJUST_STEP = self.ethos_config.get('hexus_feedback_adjustment_step', 0.05) 
                
                keywords = {
                    'brevity_inc': [r'\btoo\s+long\b', r'\btoo\s+wordy\b', r'\bshorter\b', r'\bconcise\b', r'\bto\s+the\s+point\b'],
                    'brevity_dec': [r'\btoo\s+short\b', r'\bmore\s+detail\b', r'\belaborate\b'],
                    'caution_inc': [r'\bincorrect\b', r'\bwrong\b', r'\bunsure\b', r'\bnot\s+accurate\b', r'\bverify\b'],
                    'caution_dec': [r'\bconfident\b', r'\bdirect\b', r'\bassertive\b', r'\baccurate\b', r'\bcorrect\b'],
                    'proactivity_inc': [r'\bgood\s+idea\b', r'\bthanks\s+for\s+asking\b', r'\bcontinue\b', r'\bproactive\b', r'\bgood\s+follow\s+up\b'],
                    'proactivity_dec': [r'\bstop\s+asking\b', r'\bannoying\b', r'\binterrupt\b', r'\bleave\s+me\s+alone\b'],
                    'positive_sentiment': [r'\bhelpful\b', r'\bgood\s+job\b', r'\bnice\b', r'\bthank\s+you\b'],
                    'negative_sentiment': [r'\bfail(ed)?\b', r'\berror\b', r'\bbad\b'],
                }

                for fb_entry in feedback_entries_to_process:
                    fb_id = fb_entry['id']; metadata_update = fb_entry.get('metadata', {}).copy()
                    try:
                        fb_payload = json.loads(fb_entry['content'])
                        fb_user_id = metadata_update.get('user_id', fb_payload.get('user_id', 'unknown_user'))
                        fb_text = fb_payload.get('feedback_text', '').strip() 
                        sugg_resp = fb_payload.get('suggested_response', '').strip()
                        fb_type = fb_payload.get('feedback_type'); fb_rating = fb_payload.get('rating')
                        analysis_text = (fb_text + " " + sugg_resp).lower() if fb_text or sugg_resp else None
                        adj_brevity = 0; adj_caution = 0; adj_proactivity = 0

                        if fb_type == 'positive' or (fb_rating is not None and fb_rating > 0):
                             adj_caution -= HEXUS_ADJUST_STEP * 0.5 
                             adj_proactivity += HEXUS_ADJUST_STEP * 0.5 
                        elif fb_type == 'negative' or (fb_rating is not None and fb_rating < 0):
                             adj_caution += HEXUS_ADJUST_STEP * 0.7 
                             adj_proactivity -= HEXUS_ADJUST_STEP * 0.5 
                        elif fb_type == 'correction':
                             adj_caution += HEXUS_ADJUST_STEP * 1.0

                        if analysis_text:
                            if any(re.search(pattern, analysis_text) for pattern in keywords['brevity_inc']): adj_brevity += HEXUS_ADJUST_STEP * 1.5 
                            elif any(re.search(pattern, analysis_text) for pattern in keywords['brevity_dec']): adj_brevity -= HEXUS_ADJUST_STEP * 1.5
                            if any(re.search(pattern, analysis_text) for pattern in keywords['caution_inc']): adj_caution += HEXUS_ADJUST_STEP * 1.5
                            elif any(re.search(pattern, analysis_text) for pattern in keywords['caution_dec']): adj_caution -= HEXUS_ADJUST_STEP * 1.0 
                            if any(re.search(pattern, analysis_text) for pattern in keywords['proactivity_inc']): adj_proactivity += HEXUS_ADJUST_STEP * 1.0
                            elif any(re.search(pattern, analysis_text) for pattern in keywords['proactivity_dec']): adj_proactivity -= HEXUS_ADJUST_STEP * 2.0 
                            if adj_brevity == 0 and adj_caution == 0 and adj_proactivity == 0:
                                if any(re.search(pattern, analysis_text) for pattern in keywords['positive_sentiment']):
                                     adj_caution -= HEXUS_ADJUST_STEP * 0.3; adj_proactivity += HEXUS_ADJUST_STEP * 0.3
                                elif any(re.search(pattern, analysis_text) for pattern in keywords['negative_sentiment']):
                                     adj_caution += HEXUS_ADJUST_STEP * 0.5; adj_proactivity -= HEXUS_ADJUST_STEP * 0.3

                        initial_hexus = self.hexus_scores.copy() 
                        self.hexus_scores['brevity_preference'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('brevity_preference', 0.0) + adj_brevity))
                        self.hexus_scores['general_caution'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('general_caution', 0.0) + adj_caution))
                        self.hexus_scores['user_engagement_proactivity'] = max(HEXUS_MIN, min(HEXUS_MAX, self.hexus_scores.get('user_engagement_proactivity', 0.0) + adj_proactivity))

                        if any(abs(self.hexus_scores[k] - initial_hexus[k]) > 1e-5 for k in initial_hexus.keys()):
                             self.hexus_scores_changed_during_reflection = True
                             logger.info(f"Hexus adjusted by feedback {fb_id} (Type: {fb_type}, Rating: {fb_rating}, Text: '{fb_text[:50]}...'). Initial: {initial_hexus}, New: {self.hexus_scores}")
                        
                        should_generate_monologue = False
                        monologue_prompt_context = ""
                        monologue_system_prompt = "You are Pathos, reflecting on user feedback to improve."
                        memory_type_for_reflection = "learned_feedback_insight" 

                        if fb_type == 'correction':
                            should_generate_monologue = True
                            memory_type_for_reflection = "learned_correction"
                            monologue_prompt_context = f"""Original User Input: "{fb_payload.get('last_user_input','N/A')}"\nYour Previous Response: "{fb_payload.get('last_pathos_response','N/A')}"\nUser's Stated Correction: "{sugg_resp if sugg_resp else fb_text}"\n\nBased on this correction, formulate a concise "lesson learned" or "note to self" from your perspective. Focus on the core mistake and how to avoid it. Aim for 1-2 sentences."""
                        elif fb_type == 'negative' and fb_text:
                            should_generate_monologue = True
                            monologue_prompt_context = f"""Original User Input: "{fb_payload.get('last_user_input','N/A')}"\nYour Previous Response: "{fb_payload.get('last_pathos_response','N/A')}"\nUser's Negative Feedback: "{fb_text}"\n\nBased on this negative feedback, formulate a concise "note to self". What might have gone wrong? What could you try differently? Aim for 1-2 sentences."""
                        elif fb_type == 'suggestion' and (fb_text or sugg_resp):
                            should_generate_monologue = True
                            memory_type_for_reflection = "suggestion_reflection"
                            monologue_prompt_context = f"""User's Suggestion: "{sugg_resp if sugg_resp else fb_text}"\n\nBased on this suggestion, formulate a concise "note to self". Is this a good idea? How might you consider incorporating it? Aim for 1-2 sentences."""
                        
                        if should_generate_monologue:
                            monologue_user_prompt = f"User Feedback Context:\n{monologue_prompt_context}\n\nYour concise reflection/note to self:"
                            monologue_messages = [{"role": "system", "content": monologue_system_prompt}, {"role": "user", "content": monologue_user_prompt}]
                            llm_generated_reflection = await self._call_summarization_llm(monologue_messages)
                            final_reflection_content = ""
                            if llm_generated_reflection and not llm_generated_reflection.startswith("["):
                                final_reflection_content = llm_generated_reflection
                                logger.info(f"LLM generated reflection for feedback {fb_id} (type: {fb_type}): {final_reflection_content}")
                            else:
                                logger.warning(f"Failed to generate LLM reflection for feedback {fb_id} (type: {fb_type}). Using raw details. LLM response: {llm_generated_reflection}")
                                final_reflection_content = f"Reflection on feedback (type: {fb_type}): User provided feedback: '{fb_text}'. Suggestion: '{sugg_resp}'. Regarding interaction about: '{fb_payload.get('last_user_input','N/A')[:50]}...' where I said: '{fb_payload.get('last_pathos_response','N/A')[:50]}...'."
                            
                            reflection_metadata = {
                                "source_feedback_id": fb_id, "user_id": fb_user_id,
                                "reflection_timestamp": now.isoformat(), "original_feedback_type": fb_type,
                                "original_feedback_rating": fb_rating, "original_user_input": fb_payload.get('last_user_input','N/A'),
                                "original_pathos_response": fb_payload.get('last_pathos_response','N/A'),
                                "user_suggestion_or_feedback_text": sugg_resp if sugg_resp else fb_text,
                                "llm_generated_reflection_attempted": bool(llm_generated_reflection and not llm_generated_reflection.startswith("["))
                            }
                            await self.add_memory_entry(
                                {"type": memory_type_for_reflection, "content": final_reflection_content, 
                                 "salience": 1.25, "metadata": reflection_metadata},
                                user_id_context=fb_user_id
                            )
                            logger.info(f"Stored '{memory_type_for_reflection}' from feedback {fb_id} (Content: '{final_reflection_content[:100]}...').")

                        metadata_update['processed_by_reflection'] = True
                        metadata_update['reflection_processing_timestamp'] = now.isoformat()
                        self.memory_storage.update_entry(fb_id, {'metadata': metadata_update})

                    except json.JSONDecodeError:
                        logger.error(f"Could not parse JSON content for feedback entry {fb_id}. Content: {fb_entry.get('content','')[:100]}")
                        metadata_update['processed_by_reflection'] = True; metadata_update['reflection_error'] = "JSONDecodeError"
                        self.memory_storage.update_entry(fb_id, {'metadata': metadata_update})
                    except Exception as e_fb_proc: logger.error(f"Error processing feedback entry {fb_id}: {e_fb_proc}", exc_info=True)
            except Exception as e_cycle_fb: 
                logger.error(f"Error during feedback processing part of reflection cycle: {e_cycle_fb}", exc_info=True)

        # 2. Memory Summarization
        if self.ethos_config.get('enable_memory_summarization', False):
            await self._run_memory_summarization()

        # 3. Pathos Reflects on Dreams for Curiosity
        if self.config.ENABLE_CURIOUSITY and self.config.ENABLE_ONEIROS:
            logger.info("Reflection: Pathos reflecting on recent dreams for curiosity...")
            try:
                conn = self.memory_storage._get_connection(); cursor = conn.cursor()
                sql_dreams = """
                    SELECT * FROM memories 
                    WHERE type = 'queued_discussion_point' 
                      AND json_extract(metadata, '$.source') = 'oneiros_dream_cycle'
                      AND (json_extract(metadata, '$.reflected_for_curiosity') IS NULL OR json_extract(metadata, '$.reflected_for_curiosity') = 0)
                    ORDER BY timestamp DESC 
                    LIMIT 5 
                """
                try: cursor.execute(sql_dreams)
                except sqlite3.OperationalError as oe_dream_query:
                    if "no such function: json_extract" in str(oe_dream_query).lower():
                        logger.warning("json_extract not available for dream reflection query. This part of reflection might be skipped or less efficient.")
                        sql_dreams_fallback = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT 20"
                        cursor.execute(sql_dreams_fallback)
                    else:
                        raise # Re-raise other operational errors

                dream_rows = cursor.fetchall()
                dreams_to_reflect_on: List[MemoryEntry] = []
                for row in dream_rows:
                    entry = self._row_to_entry(row)
                    meta = entry.get('metadata', {})
                    if meta.get('source') == 'oneiros_dream_cycle' and not meta.get('reflected_for_curiosity'):
                        dreams_to_reflect_on.append(entry)
                
                if not dreams_to_reflect_on:
                    logger.info("Reflection: No new dreams from Oneiros to reflect on for curiosity.")
                
                # Ensure we only process up to the intended limit if fallback query fetched more
                dreams_to_process_this_cycle = dreams_to_reflect_on[:5]


                for dream_entry in dreams_to_process_this_cycle:
                    dream_id = dream_entry.get('id')
                    dream_content = dream_entry.get('content', "An abstract dream fragment.")
                    dream_image_path = dream_entry.get('metadata', {}).get('dream_image_path')
                    
                    logger.info(f"Reflection: Pathos considering dream ID {dream_id} for curiosity: '{dream_content[:100]}...'")

                    curiosity_system_prompt = ("You are Pathos, an AI with a curious and reflective nature. You've had an 'insight' or 'dream fragment' generated by your Oneiros module. Consider it thoughtfully.")
                    curiosity_user_prompt_parts = [f"Here is a recent dream/insight you had:\nDream Content: \"{dream_content}\""]
                    if dream_image_path: curiosity_user_prompt_parts.append(f"(An image was also generated for this dream at: {dream_image_path})")
                    curiosity_user_prompt_parts.append("\n\nBased on this, does it spark any genuine curiosity in you? Does it make you want to understand something better about the world, a concept, or how it might relate to your experiences or users? If yes, formulate a specific research question or a topic you'd like to explore further using research tools. Make the question clear and investigable. If no strong curiosity or actionable research question arises, respond with ONLY the exact phrase: 'No further inquiry needed for this insight.'\n\nYour research question/topic (or 'No further inquiry needed for this insight.'):")
                    curiosity_user_prompt = "\n".join(curiosity_user_prompt_parts)
                    curiosity_messages = [{"role": "system", "content": curiosity_system_prompt}, {"role": "user", "content": curiosity_user_prompt}]
                    
                    llm_response_for_curiosity = await self._call_summarization_llm(curiosity_messages)

                    if llm_response_for_curiosity and not llm_response_for_curiosity.startswith("[") and llm_response_for_curiosity.strip().lower() != "no further inquiry needed for this insight.":
                        research_query = llm_response_for_curiosity.strip()
                        logger.info(f"Pathos generated research query from dream ID {dream_id}: '{research_query}'")
                        if self.logos_core and self.config.ENABLE_WEB_SEARCH:
                            try:
                                # CORRECTED METHOD NAME
                                research_result_content = await self.logos_core.execute_deep_research(research_query) 
                                
                                if research_result_content and not research_result_content.startswith('{"error":'):
                                    knowledge_id = str(uuid.uuid4())
                                    original_dream_user_id = dream_entry.get('metadata', {}).get('user_id', 'system_oneiros')
                                    new_knowledge_content = f"Following a train of thought (from dream ID: {dream_id[:8]}...), I looked into: '{research_query}'.\n\nHere's a summary of what I found:\n{research_result_content}"
                                    
                                    await self.add_memory_entry({
                                        "id": knowledge_id, "type": "world_knowledge",
                                        "content": new_knowledge_content, 
                                        "metadata": {"user_id": "system_curiosity", "source": "curiosity_driven_research",
                                                     "original_dream_id": dream_id, "original_dream_user_id_context": original_dream_user_id, 
                                                     "dream_content_seed": dream_entry.get('content', '')[:200] + "...",
                                                     "research_query_by_pathos": research_query, "timestamp": datetime.now(timezone.utc).isoformat()},
                                        "salience": 0.8 }, user_id_context="world_knowledge_store")
                                    logger.info(f"Stored new world knowledge (ID: {knowledge_id}) from curiosity-driven research on '{research_query[:50]}...'.")

                                    if self.connection_manager and self.pathos_interface:
                                        user_to_notify = None
                                        if original_dream_user_id and original_dream_user_id not in ["system_oneiros", "system_reflection", "system_curiosity", "unknown_user", "api_guest_user", "system_document", "system_briefing", "world_knowledge_store"]: # Added more system IDs
                                            user_to_notify = original_dream_user_id
                                        
                                        if user_to_notify:
                                            notification_prompt_system = "You are Pathos. You've just learned something new based on a previous reflection or 'dream'. Formulate a very brief and casual message to share this new insight or piece of knowledge with the user who might find it interesting."
                                            notification_prompt_user = f"You just learned the following after researching '{research_query}':\n\nSummary: \"{research_result_content[:300]}...\"\n\nCraft a short, proactive message for user '{user_to_notify}' to share this, perhaps mentioning it stemmed from a thought you had. Example: 'Hey, I was thinking about [related topic from dream] and ended up learning that [brief new knowledge]! Thought you might find that interesting.'"
                                            notification_messages = [{"role": "system", "content": notification_prompt_system}, {"role": "user", "content": notification_prompt_user}]
                                            formatted_notification_content = await self._call_summarization_llm(notification_messages)

                                            if formatted_notification_content and not formatted_notification_content.startswith("["):
                                                ws_message_payload = {
                                                    "type": "unsolicited_message", 
                                                    "payload": {
                                                        "content": formatted_notification_content,
                                                        "metadata": {
                                                            "proactive_type": "newly_learned_knowledge", 
                                                            "source_dream_id": dream_id,
                                                            "research_query": research_query,
                                                            "knowledge_snippet": research_result_content[:150] + "...", 
                                                            "timestamp": datetime.now(timezone.utc).isoformat(),
                                                            "mood_at_generation": self.get_current_mood(),
                                                            "hexus_at_generation": self.get_hexus_scores()
                                                        }
                                                    }
                                                }
                                                await self.connection_manager.send_personal_message(ws_message_payload, user_to_notify)
                                                logger.info(f"Sent WebSocket notification to user '{user_to_notify}' about new knowledge from dream ID {dream_id}.")
                                                await self.record_proactive_action(user_to_notify, "shared_newly_learned_knowledge", {"dream_id": dream_id, "query": research_query})
                                            else:
                                                logger.warning(f"Failed to generate formatted notification content for new knowledge (dream ID {dream_id}). LLM response: {formatted_notification_content}")
                                        else:
                                            logger.info(f"New knowledge from dream ID {dream_id} was system-generated or original user unknown; no specific user notification sent via WebSocket.")
                                else:
                                    logger.warning(f"Deep research for query '{research_query}' (from dream {dream_id}) did not yield usable results or had an error: {research_result_content}")
                            except Exception as e_research: 
                                logger.error(f"Error during curiosity-driven deep research for query '{research_query}': {e_research}", exc_info=True)
                        else:
                            logger.warning(f"Cannot perform curiosity-driven research for dream {dream_id}: LogosCore or WebSearch not available.")
                    
                    elif llm_response_for_curiosity and llm_response_for_curiosity.strip().lower() == "no further inquiry needed for this insight.":
                        logger.info(f"Pathos indicated no further inquiry needed for dream ID {dream_id}.")
                    else: 
                        logger.warning(f"Could not determine research query from Pathos's reflection on dream ID {dream_id}. LLM response: {llm_response_for_curiosity}")

                    dream_meta_update = dream_entry.get('metadata', {}).copy()
                    dream_meta_update['reflected_for_curiosity'] = True
                    dream_meta_update['curiosity_reflection_timestamp'] = now.isoformat()
                    self.memory_storage.update_entry(dream_id, {'metadata': dream_meta_update})
                    await asyncio.sleep(random.uniform(2,5)) 
            except Exception as e_curiosity_cycle:
                logger.error(f"Error during Pathos reflects on dreams (curiosity) part of reflection cycle: {e_curiosity_cycle}", exc_info=True)

        if self.hexus_scores_changed_during_reflection: 
            self._save_hexus_scores()

        logger.info("--- Ethos: Reflection Cycle Finished ---")
        if self.config.ENABLE_PROACTIVE_BEHAVIOR:
             logger.debug("Reflection cycle finished, triggering proactive check.")
             task_name = f"ProactiveCheckTriggeredByReflection_{uuid.uuid4().hex[:8]}"
             asyncio.create_task(self.run_proactive_check(trigger_source="Reflection"), name=task_name)
             logger.debug(f"Proactive check task '{task_name}' created.")



    async def run_managed_forgetting(self):
        if not self.config.ENABLE_MANAGED_FORGETTING: return
        forgetting_interval = self.ethos_config.get('forgetting_interval_seconds', 0)
        if forgetting_interval <= 0: logger.debug("Managed forgetting disabled."); return
        now = datetime.now(timezone.utc)
        if now - self.last_forgetting_time < timedelta(seconds=forgetting_interval): logger.debug("Managed forgetting skipped."); return
        logger.info("Starting Managed Forgetting..."); self.last_forgetting_time = now
        try:
            decay_rate_per_day = self.ethos_config.get('salience_decay_rate_per_day', 0.01)
            min_salience_threshold = self.ethos_config.get('min_salience_for_decay', 0.01)
            user_fact_floor = self.ethos_config.get('user_fact_salience_floor', 1.0)
            if not (0 < decay_rate_per_day < 1): decay_rate_per_day = 0.0
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql_select_decay_candidates = """
                SELECT id, timestamp, salience, type FROM memories
                WHERE salience IS NOT NULL AND salience > ? AND type != 'user_fact'
            """
            cursor.execute(sql_select_decay_candidates, (min_salience_threshold,))
            entries_to_check = cursor.fetchall()

            sql_select_user_facts = """
                SELECT id, timestamp, salience, type FROM memories
                WHERE type = 'user_fact' AND salience IS NOT NULL AND salience > ?
            """
            cursor.execute(sql_select_user_facts, (user_fact_floor,)) 
            user_facts_above_floor = cursor.fetchall()


            if not entries_to_check and not user_facts_above_floor: logger.info("Managed Forgetting: No entries requiring decay or user fact floor adjustment."); return

            updates_to_make = []

            for row_data in entries_to_check:
                entry_id, ts_str, current_salience, entry_type = row_data['id'], row_data['timestamp'], row_data['salience'], row_data['type']
                try: entry_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                except ValueError: continue 
                days_elapsed = (now - entry_time).total_seconds() / (24 * 3600.0)
                if days_elapsed <= 0: continue 

                new_salience = current_salience * (math.pow(1.0 - decay_rate_per_day, days_elapsed)) if decay_rate_per_day > 0 else current_salience
                new_salience = max(min_salience_threshold, new_salience)

                if new_salience < current_salience and not math.isclose(new_salience, current_salience, rel_tol=1e-5):
                    updates_to_make.append((new_salience, entry_id))

            for row_data in user_facts_above_floor:
                entry_id, ts_str, current_salience, entry_type = row_data['id'], row_data['timestamp'], row_data['salience'], row_data['type']
                if current_salience > user_fact_floor and not math.isclose(current_salience, user_fact_floor, rel_tol=1e-5):
                     updates_to_make.append((user_fact_floor, entry_id))
                     logger.debug(f"Adjusting user_fact {entry_id} salience from {current_salience:.2f} down to floor {user_fact_floor:.2f}.")


            if updates_to_make:
                cursor.executemany("UPDATE memories SET salience = ? WHERE id = ?", updates_to_make)
                conn.commit()
                logger.info(f"Managed Forgetting: Updated salience for {len(updates_to_make)} entries.")
            else: logger.info("Managed Forgetting: No entries required salience updates.")
        except Exception as e: logger.error(f"Error during Managed Forgetting: {e}", exc_info=True)
        logger.info("Managed Forgetting process finished.")

    async def run_hexus_decay(self):
        if not self.hexus_scores: logger.debug("Hexus decay: scores not available."); return
        decay_interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600)
        if decay_interval <=0: logger.debug("Hexus decay disabled."); return
        now = datetime.now(timezone.utc)
        if now - self.last_hexus_decay_time < timedelta(seconds=decay_interval): logger.debug("Hexus decay skipped."); return
        logger.info("Running Hexus Score Decay..."); self.last_hexus_decay_time = now
        decay_rate = self.ethos_config.get('hexus_decay_rate_per_cycle', 0.005) 
        if not isinstance(decay_rate, (int, float)) or decay_rate < 0 or decay_rate >= 1:
             logger.warning(f"Invalid or non-positive hexus_decay_rate {decay_rate}. Using default 0.005.")
             decay_rate = 0.005

        updated = False
        initial_hexus = self.hexus_scores.copy() 

        for key in DEFAULT_HEXUS_SCORES.keys(): 
             current_val = self.hexus_scores.get(key, 0.0) 
             distance_to_baseline = current_val - 0.0
             decay_amount = distance_to_baseline * decay_rate
             new_val = current_val - decay_amount
             new_val = max(HEXUS_MIN, min(HEXUS_MAX, new_val))
             if not math.isclose(new_val, current_val, rel_tol=1e-5):
                  self.hexus_scores[key] = new_val
                  updated = True

        if updated:
            self._save_hexus_scores();
            logger.info(f"Hexus scores decayed and saved. Initial: {initial_hexus}, New: {self.hexus_scores}")
        else: logger.debug("No significant Hexus score decay.")


    async def update_mood_state(self, event_type: str, data: Any):
        if not self.config.ENABLE_MOOD_SIMULATION: return
        logger.debug(f"Updating mood: event={event_type}, data={str(data)[:100]}")

        current_mood_decayed = self.get_current_mood() 
        self.current_mood['valence'] = current_mood_decayed['valence'] 
        self.current_mood['arousal'] = current_mood_decayed['arousal'] 

        v_change, a_change = 0.0, 0.0

        if event_type == 'task_outcome':
            success = data.get('success', False) if isinstance(data, dict) else bool(data)
            task_type = data.get('type') if isinstance(data, dict) else None 
            v_change, a_change = (MOOD_SHIFT_VALENCE_SUCCESS, MOOD_SHIFT_AROUSAL_SUCCESS) if success else (MOOD_SHIFT_VALENCE_FAILURE, MOOD_SHIFT_AROUSAL_FAILURE)

        elif event_type == 'feedback' and isinstance(data, dict):
            fb_type, rating = data.get('feedback_type'), data.get('rating')
            if fb_type == 'positive' or (rating is not None and rating > 0):
                 v_change, a_change = MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE, MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE
            elif fb_type == 'negative' or (rating is not None and rating < 0):
                 v_change, a_change = MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE, MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE
            elif fb_type in ['correction', 'suggestion']:
                 v_change, a_change = -0.05, 0.1
        
        if v_change != 0.0 or a_change != 0.0:
            self.current_mood['valence'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['valence'] + v_change))
            self.current_mood['arousal'] = max(MOOD_MIN, min(MOOD_MAX, self.current_mood['arousal'] + a_change))
            self.last_mood_update_time = datetime.now(timezone.utc)
            logger.info(f"Mood updated by event '{event_type}'. New: V={self.current_mood['valence']:.2f}, A={self.current_mood['arousal']:.2f}")
        else:
             logger.debug(f"Mood update for event '{event_type}' resulted in no change.")

    def get_current_mood(self) -> Dict[str, float]:
        if not self.config.ENABLE_MOOD_SIMULATION: return {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE}.copy()
        now = datetime.now(timezone.utc); hours_elapsed = (now - self.last_mood_update_time).total_seconds() / 3600.0
        decay_rate = self.ethos_config.get('mood_decay_rate_per_hour', 0.05)
        if not isinstance(decay_rate, (int, float)) or decay_rate < 0 or decay_rate >= 1:
             logger.warning(f"Invalid or non-positive mood_decay_rate {decay_rate}. Using default 0.05.")
             decay_rate = 0.05

        multiplier = math.pow(1.0 - decay_rate, max(0, hours_elapsed)) 
        v_offset = self.current_mood['valence'] - MOOD_VALENCE_BASELINE
        a_offset = self.current_mood['arousal'] - MOOD_AROUSAL_BASELINE
        decayed_valence = MOOD_VALENCE_BASELINE + (v_offset * multiplier)
        decayed_arousal = MOOD_AROUSAL_BASELINE + (a_offset * multiplier)
        decayed_valence = max(MOOD_MIN, min(MOOD_MAX, decayed_valence))
        decayed_arousal = max(MOOD_MIN, min(MOOD_MAX, decayed_arousal))
        return {"valence": decayed_valence, "arousal": decayed_arousal}

    def get_persona_directives(self) -> List[str]: return self.persona_directives[:]
    def get_hexus_scores(self) -> Dict[str, float]: return self.hexus_scores.copy()

    async def get_todays_briefing(self) -> Optional[str]:
        today_date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        logger.debug(f"Ethos searching for daily briefing for: {today_date_str}")
        try:
            conn = self.memory_storage._get_connection(); cursor = conn.cursor()
            sql_briefing = "SELECT content, timestamp FROM memories WHERE type = 'daily_briefing' AND date(timestamp) = date(?) ORDER BY timestamp DESC LIMIT 1"
            cursor.execute(sql_briefing, (today_date_str,))
            row = cursor.fetchone()
            if row:
                 logger.info(f"Found existing daily briefing from {row['timestamp'][:16]}.")
                 return row['content']
            logger.debug("No existing daily briefing found for today.")
            return None
        except Exception as e: logger.error(f"Error retrieving daily briefing: {e}", exc_info=True); return None

    async def update_persona_directives(self, new_directives: List[str]):
        logger.info(f"Updating persona directives with {len(new_directives)} new directives.")
        self.persona_directives = new_directives
        try:
            PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f:
                f.write("\n".join(new_directives))
            logger.info(f"Saved updated persona directives to {PERSONA_FILE_PATH}")
        except Exception as e: logger.error(f"Failed to save updated persona directives: {e}", exc_info=True)

    async def run_knowledge_upkeep_cycle(self): 
        if not self.config.ENABLE_KNOWLEDGE_UPKEEP:
            logger.debug("Knowledge Upkeep cycle skipped: Disabled in config.")
            return
        
        upkeep_interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 0)
        if upkeep_interval <= 0:
            logger.debug("Knowledge Upkeep cycle skipped: Interval is zero or negative.")
            return

        now = datetime.now(timezone.utc)
        if now - self.last_knowledge_upkeep_time < timedelta(seconds=upkeep_interval):
            logger.debug("Knowledge Upkeep cycle skipped: Not enough time passed since last run.")
            return

        logger.info("--- Ethos: Starting Knowledge Upkeep Cycle ---")
        self.last_knowledge_upkeep_time = now

        volatile_tags = self.ethos_config.get('knowledge_upkeep_volatile_tags', [])
        if not volatile_tags:
            logger.warning("Knowledge Upkeep: No volatile tags configured. Skipping fact verification.")
            logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No tags) ---")
            return

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            sql_select_candidates = "SELECT * FROM memories WHERE type = 'world_knowledge' AND metadata IS NOT NULL ORDER BY RANDOM() LIMIT 50" 
            cursor.execute(sql_select_candidates)
            candidate_rows = cursor.fetchall()

            facts_to_verify: List[MemoryEntry] = []
            volatile_tags_lower = [tag.lower() for tag in volatile_tags]

            for row in candidate_rows:
                entry = self._row_to_entry(row)
                entry_tags_raw = entry.get('metadata', {}).get('topic_tags', [])
                entry_tags_lower = [str(tag).lower() for tag in entry_tags_raw if isinstance(tag, str)]
                
                if any(tag_l in volatile_tags_lower for tag_l in entry_tags_lower):
                    facts_to_verify.append(entry)
                    if len(facts_to_verify) >= 5: 
                        break
            
            if not facts_to_verify:
                logger.info("Knowledge Upkeep: No world_knowledge facts with volatile tags found for verification in this cycle.")
                logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (No facts to verify) ---")
                return

            logger.info(f"Knowledge Upkeep: Found {len(facts_to_verify)} facts to potentially verify.")

            if not self.logos_core:
                logger.error("Knowledge Upkeep: LogosCore is not available. Cannot verify facts.")
                logger.info("--- Ethos: Knowledge Upkeep Cycle Finished (LogosCore missing) ---")
                return

            for fact_entry in facts_to_verify:
                fact_id = fact_entry.get('id')
                fact_content = fact_entry.get('content')
                logger.info(f"Knowledge Upkeep: Attempting to verify fact ID {fact_id}: '{fact_content[:100]}...'")
                
                verification_result = await self.logos_core.verify_world_fact(fact_entry)

                current_fact_meta = fact_entry.get('metadata', {}).copy()
                current_fact_meta['last_verified_timestamp'] = datetime.now(timezone.utc).isoformat()
                current_fact_meta['verification_reason'] = verification_result.get('reason', 'No specific reason provided.')

                if verification_result.get("status") == "updated":
                    new_fact_content = verification_result.get("new_fact_statement")
                    new_fact_confidence = verification_result.get("confidence", 0.85) 
                    logger.info(f"Fact ID {fact_id} was updated. New content: '{new_fact_content[:100]}...' Confidence: {new_fact_confidence}")
                    
                    new_fact_id = str(uuid.uuid4())

                    await self.add_memory_entry({
                        "id": new_fact_id, 
                        "type": "world_knowledge",
                        "content": new_fact_content,
                        "metadata": {
                            "user_id": "system_knowledge_upkeep", 
                            "source_description": f"Auto-updated from fact ID {fact_id} via knowledge upkeep ({datetime.now(timezone.utc).isoformat()}). Original source: {fact_entry.get('metadata',{}).get('source_description','unknown')}",
                            "topic_tags": fact_entry.get('metadata',{}).get('topic_tags',[]), 
                            "confidence_level": new_fact_confidence, 
                            "original_fact_id_verified": fact_id,
                            "last_verified_timestamp": datetime.now(timezone.utc).isoformat()
                        },
                        "salience": (fact_entry.get('salience') or 0.7) + 0.1 
                    }, user_id_context="world_knowledge_store")

                    current_fact_meta['status'] = 'outdated_by_upkeep'
                    current_fact_meta['superseded_by_fact_id'] = new_fact_id 
                    self.memory_storage.update_entry(fact_id, {"metadata": current_fact_meta, "salience": (fact_entry.get('salience') or 0.5) * 0.5})

                elif verification_result.get("status") == "accurate":
                    logger.info(f"Fact ID {fact_id} confirmed accurate. Reason: {verification_result.get('reason')}")
                    current_fact_meta.pop('verification_attempt_failed', None) 
                    # verification_reason and last_verified_timestamp are already in current_fact_meta
                    self.memory_storage.update_entry(fact_id, {"metadata": current_fact_meta})
                
                elif verification_result.get("status") == "unverifiable": 
                    logger.warning(f"Fact ID {fact_id} could not be verified: {verification_result.get('reason')}")
                    current_fact_meta['verification_attempt_failed'] = True
                    # verification_reason and last_verified_timestamp are already in current_fact_meta
                    self.memory_storage.update_entry(fact_id, {"metadata": current_fact_meta})
                
                await asyncio.sleep(random.uniform(5, 10)) 

        except Exception as e:
            logger.error(f"Error during Knowledge Upkeep cycle: {e}", exc_info=True)
        
        logger.info("--- Ethos: Knowledge Upkeep Cycle Finished ---")


    async def get_background_tasks(self) -> List[asyncio.Task]:
        tasks = []
        async def _run_periodically(coro_func: Any, interval_seconds: float, task_name: str):
            if interval_seconds <= 0: logger.warning(f"Interval for '{task_name}' is {interval_seconds}s. Task disabled."); return
            await asyncio.sleep(random.uniform(5, 15))
            logger.info(f"Starting periodic task '{task_name}' (interval {interval_seconds}s)...")
            while True:
                try:
                    logger.debug(f"Executing periodic task: {task_name}")
                    await coro_func()
                except asyncio.CancelledError: logger.info(f"Periodic task '{task_name}' cancelled."); break
                except Exception as e: logger.error(f"Error in background task {task_name}: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)

        reflection_interval = float(self.ethos_config.get('reflection_interval_seconds', 86400.0))
        forgetting_interval = float(self.ethos_config.get('forgetting_interval_seconds', 43200.0))
        hexus_decay_interval = float(self.ethos_config.get('hexus_decay_interval_seconds', 3600.0))
        oneiros_interval = float(self.config.ONEIROS.get('dream_interval_seconds', 21600.0))
        knowledge_upkeep_interval = float(self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0))

        if any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False)]):
             if reflection_interval > 0:
                tasks.append(asyncio.create_task(_run_periodically(self.run_reflection_cycle, reflection_interval, "EthosReflection"), name="EthosReflection"))
             else:
                 logger.warning(f"Reflection features are enabled but ETHOS_REFLECTION_INTERVAL_SECONDS is {reflection_interval}s. Reflection task disabled.")

        if self.config.ENABLE_MANAGED_FORGETTING:
             if forgetting_interval > 0:
                tasks.append(asyncio.create_task(_run_periodically(self.run_managed_forgetting, forgetting_interval, "EthosForgetting"), name="EthosForgetting"))
             else:
                 logger.warning(f"Managed forgetting is enabled but ETHOS_FORGETTING_INTERVAL_SECONDS is {forgetting_interval}s. Forgetting task disabled.")

        if hexus_decay_interval > 0:
            tasks.append(asyncio.create_task(_run_periodically(self.run_hexus_decay, hexus_decay_interval, "HexusDecay"), name="HexusDecay"))
        elif hexus_decay_interval <= 0: 
             logger.warning(f"ETHOS_HEXUS_DECAY_INTERVAL_SECONDS is {hexus_decay_interval}s. Hexus decay task disabled.")


        if self.config.ENABLE_ONEIROS and self.oneiros_module:
             if oneiros_interval > 0:
                tasks.append(asyncio.create_task(_run_periodically(self.oneiros_module.run_dream_cycle, oneiros_interval, "OneirosDreamCycle"), name="OneirosDreamCycle"))
             else:
                 logger.warning(f"Oneiros is enabled but ONEIROS_DREAM_INTERVAL_SECONDS is {oneiros_interval}s. Dream cycle task disabled.")
        elif self.config.ENABLE_ONEIROS and not self.oneiros_module:
            logger.warning("Oneiros is enabled but module instance not set in EthosCore. Dream cycle won't run.")
        
        if self.config.ENABLE_KNOWLEDGE_UPKEEP: 
            if knowledge_upkeep_interval > 0:
                tasks.append(asyncio.create_task(_run_periodically(self.run_knowledge_upkeep_cycle, knowledge_upkeep_interval, "KnowledgeUpkeep"), name="KnowledgeUpkeep"))
            else:
                logger.warning(f"Knowledge Upkeep is enabled but ETHOS_KNOWLEDGE_UPKEEP_INTERVAL_SECONDS is {knowledge_upkeep_interval}s. Task disabled.")
        
        logger.info(f"EthosCore providing {len(tasks)} background tasks.")
        return tasks

    async def run_proactive_check(self, trigger_source: str = "Manual"):
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR or not self.connection_manager or not self.pathos_interface:
            if not self.config.ENABLE_PROACTIVE_BEHAVIOR:
                 logger.debug("Proactive check skipped: ENABLE_PROACTIVE_BEHAVIOR is False.")
            elif not self.connection_manager:
                 logger.debug("Proactive check skipped: ConnectionManager not set in EthosCore.")
            elif not self.pathos_interface:
                 logger.debug("Proactive check skipped: PathosInterface not set in EthosCore.")
            else:
                 logger.debug("Proactive check skipped: Unknown reason.") 
            return

        logger.debug(f"Ethos: Running proactive check (Triggered by: {trigger_source})...")
        now_utc = datetime.now(timezone.utc)
        users_to_check = list(self.connection_manager.active_connections.keys())
        if not users_to_check:
             logger.debug("Proactive check: No active users with WebSocket connections.")
             return

        for user_id in users_to_check:
            logger.debug(f"Proactive check for user: {user_id}")
            now_local = await self.get_local_datetime_for_user(user_id)
            current_hour_local = now_local.hour
            current_time_of_day = "morning" if 5 <= current_hour_local < 12 else "afternoon" if 12 <= current_hour_local < 18 else "evening"
            logger.debug(f"Proactive check for user {user_id}: Current local time is {now_local.isoformat()}, Time of day: {current_time_of_day}")
            
            proactive_opportunity_type: Optional[str] = None
            selected_opportunity_details: Optional[Dict[str, Any]] = None 

            queued_points = await self.get_queued_discussion_points(user_id, limit=1)
            if queued_points:
                point = queued_points[0]
                point_id = point.get('id')
                point_content = point.get('content')
                point_reason = point.get('metadata', {}).get('reason_for_queueing', 'some earlier thoughts')
                action_type_queued = f"offered_queued_discussion_{point_id}"
                last_offer_time = await self.get_last_proactive_action_time(user_id, action_type_queued)
                queued_point_offer_interval_hours = self.ethos_config.get('proactive_queued_point_offer_interval_hours', 24)
                queued_point_chance = float(self.ethos_config.get('proactive_queued_point_chance', 0.5)) # type: ignore

                if (not last_offer_time or (now_utc - last_offer_time > timedelta(hours=queued_point_offer_interval_hours))) and random.random() < queued_point_chance:
                    proactive_opportunity_type = "queued_discussion"
                    selected_opportunity_details = {"point_id": point_id, "topic_content": point_content, "reason": point_reason}
                    logger.debug(f"Proactive opportunity found for user {user_id}: Queued Discussion Point '{point_id[:8]}'")
                    
            if not proactive_opportunity_type:
                last_greeting_time = await self.get_last_proactive_action_time(user_id, "greeting")
                greeting_interval_hours = self.ethos_config.get('proactive_greeting_interval_hours', 4)
                significant_time_for_greeting = timedelta(hours=greeting_interval_hours)
                last_greeting_hour = last_greeting_time.hour if last_greeting_time else -1
                last_time_of_day = "morning" if 5 <= last_greeting_hour < 12 else "afternoon" if 12 <= last_greeting_hour < 18 else "evening" if last_greeting_time else "none"

                needs_greeting = False
                if not last_greeting_time:
                     needs_greeting = True
                     logger.debug(f"User {user_id}: Needs greeting - No last greeting found.")
                else:
                     is_new_time_of_day_period = (last_time_of_day != current_time_of_day)
                     interval_passed = (now_utc - last_greeting_time > significant_time_for_greeting)

                     if is_new_time_of_day_period:
                          needs_greeting = True
                          logger.debug(f"User {user_id}: Needs greeting - New time of day period ({current_time_of_day}).")
                     elif interval_passed:
                          needs_greeting = True
                          logger.debug(f"User {user_id}: Needs greeting - Interval ({greeting_interval_hours}h) passed since last greeting.")
                     else:
                          logger.debug(f"User {user_id}: Does not need greeting - Same time of day period ({current_time_of_day}) and interval not passed.")

                greeting_chance = float(self.ethos_config.get('proactive_greeting_chance', 0.3)) # type: ignore
                if needs_greeting and random.random() < greeting_chance:
                    proactive_opportunity_type = "greeting"
                    selected_opportunity_details = {"time_of_day": current_time_of_day}
                    logger.debug(f"Proactive opportunity found for user {user_id}: Greeting")
                    
            if not proactive_opportunity_type and self.config.ENABLE_DAILY_CONTEXT:
                briefing_content_for_panel = await self.get_todays_briefing() 

                if briefing_content_for_panel is None: 
                    logger.info(f"Proactive check for user {user_id}: Daily briefing missing. Triggering generation.")
                    if hasattr(self, 'logos_core') and self.logos_core:
                         asyncio.create_task(
                             self.logos_core.generate_daily_briefing(user_id_context=user_id), 
                             name=f"GenerateDailyBriefing_{now_utc.strftime('%Y%m%d')}_{user_id}"
                         )
                    else:
                         logger.error("LogosCore not accessible in EthosCore to trigger briefing generation.")
                else: 
                    last_briefing_discussion_offer_time = await self.get_last_proactive_action_time(user_id, "offer_briefing_discussion") 
                    briefing_is_stale_for_offer = not last_briefing_discussion_offer_time or last_briefing_discussion_offer_time.date() < now_utc.date()
                    briefing_offer_chance = float(self.ethos_config.get('proactive_briefing_chance', 0.4)) # type: ignore

                    if briefing_is_stale_for_offer and random.random() < briefing_offer_chance:
                        proactive_opportunity_type = "offer_briefing_discussion" 
                        selected_opportunity_details = {
                            "briefing_date": now_utc.strftime('%Y%m%d'),
                            "full_briefing_content": briefing_content_for_panel 
                        }
                        logger.debug(f"Proactive opportunity found for user {user_id}: Offer Briefing Discussion")

            if not proactive_opportunity_type:
                 recent_topics = await self.get_recent_interaction_topics(user_id, num_interactions=1)
                 if recent_topics:
                     topic = recent_topics[0]
                     topic_key = re.sub(r'\W+', '_', topic[:50].lower()).strip('_')
                     if not topic_key: topic_key = "generic"
                     action_type_topic = f"offer_topic_continuation_{topic_key}"

                     last_offer_time = await self.get_last_proactive_action_time(user_id, action_type_topic)
                     topic_interval_hours = self.ethos_config.get('proactive_topic_interval_hours', 12)
                     topic_continuation_chance = float(self.ethos_config.get('proactive_topic_chance', 0.2)) # type: ignore

                     if (not last_offer_time or (now_utc - last_offer_time > timedelta(hours=topic_interval_hours))) and random.random() < topic_continuation_chance:
                         proactive_opportunity_type = "offer_topic_continuation"
                         selected_opportunity_details = {"topic": topic}
                         logger.debug(f"Proactive opportunity found for user {user_id}: Topic Continuation ('{topic_key}')")
                     else:
                          logger.debug(f"User {user_id}: Topic continuation opportunity found but conditions not met (offered recently or chance failed).")
            
            if proactive_opportunity_type and self.connection_manager and self.pathos_interface:
                logger.info(f"Generating and sending proactive message for user {user_id}, type: {proactive_opportunity_type}")
                proactive_message_content = await self.pathos_interface._generate_proactive_message(
                    user_id, proactive_opportunity_type, selected_opportunity_details 
                )

                if proactive_message_content:
                    ws_message_payload = {
                        "type": "unsolicited_message",
                        "payload": {
                            "content": proactive_message_content,
                            "metadata": {
                                "proactive_type": proactive_opportunity_type,
                                "timestamp": now_utc.isoformat(), 
                                "mood_at_generation": self.get_current_mood(), 
                                "hexus_at_generation": self.get_hexus_scores() 
                            }
                        }
                    }
                    await self.connection_manager.send_personal_message(ws_message_payload, user_id)
                    action_type_to_record = action_type_queued if proactive_opportunity_type == "queued_discussion" and selected_opportunity_details and "point_id" in selected_opportunity_details else proactive_opportunity_type
                    await self.record_proactive_action(user_id, action_type_to_record, selected_opportunity_details) 
                    if proactive_opportunity_type == "queued_discussion" and selected_opportunity_details and "point_id" in selected_opportunity_details:
                         await self.mark_queued_point_offered(selected_opportunity_details["point_id"], user_id)
                elif not proactive_message_content:
                    logger.warning(f"Failed to generate proactive message content for user {user_id}, type: {proactive_opportunity_type}")
            else:
                 logger.debug(f"User {user_id}: No proactive opportunity selected in this check cycle.")
        logger.debug(f"Ethos: Proactive check finished (Triggered by: {trigger_source}).")

    async def trigger_proactive_check_after_event(self, event_source: str):
        if not self.config.ENABLE_PROACTIVE_BEHAVIOR:
            logger.debug(f"Proactive check trigger ignored from '{event_source}': Proactive behavior disabled.")
            return

        logger.info(f"Proactive check triggered by event source: '{event_source}'.")
        task_name = f"ProactiveCheckTriggeredBy{event_source}_{uuid.uuid4().hex[:8]}"
        asyncio.create_task(self.run_proactive_check(trigger_source=event_source), name=task_name)
        logger.debug(f"Proactive check task '{task_name}' created.")
    
    async def get_and_clear_pending_document_context(self, user_id: str) -> Optional[Dict[str, str]]:
        if not user_id: return None
        if not hasattr(self.memory_storage, 'get_and_clear_pending_document_context'):
             logger.error("MemoryStorage instance does not have the 'get_and_clear_pending_document_context' method.")
             return None
        return self.memory_storage.get_and_clear_pending_document_context(user_id)
    
    async def clear_memory_for_user(self, user_id: str) -> bool:
        if not user_id or not user_id.strip():
            logger.warning("Attempted to clear memory for an empty or invalid user_id.")
            return False
        logger.warning(f"EthosCore: Attempting to clear ALL memory entries for user_id: '{user_id}'.")
        try:
            success = self.memory_storage.delete_entries_by_user_id(user_id)
            if success:
                logger.info(f"Successfully cleared memory entries for user_id: '{user_id}'.")
            else:
                logger.warning(f"Memory clearing for user_id '{user_id}' reported no entries deleted or an issue occurred at storage level.")
            return success
        except Exception as e:
            logger.error(f"Error during clear_memory_for_user (user: '{user_id}'): {e}", exc_info=True)
            return False

    # --- NEW METHOD for GUI to fetch recent learnings ---
    async def get_recent_learnings(self, learning_types: List[str], user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        """
        Retrieves recent memory entries of specified 'learning' types,
        optionally filtered by user_id_context.
        Learnings relevant to "all users" (e.g., system_reflection) are included if user_id_context is provided.
        """
        logger.debug(f"Fetching recent learnings. Types: {learning_types}, User: {user_id_context}, Limit: {limit}")
        if not learning_types:
            return []

        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(learning_types))
            # Base query fetches candidates, Python filters by user context
            sql_query = f"SELECT * FROM memories WHERE type IN ({placeholders})"
            params: List[Any] = list(learning_types)
            sql_query += " ORDER BY timestamp DESC LIMIT ?" 
            params.append(limit * 5) # Fetch more candidates for Python-side filtering

            cursor.execute(sql_query, tuple(params))
            rows = cursor.fetchall()

            learnings: List[MemoryEntry] = []
            # Define system-level user_ids that might generate learnings relevant to all or a specific user
            system_learning_user_ids = ["system_reflection", "system_curiosity", "system_knowledge_upkeep"] 

            for row in rows:
                entry = self._row_to_entry(row)
                entry_user_id = entry.get('metadata', {}).get('user_id')

                if user_id_context and user_id_context not in ["unknown_user", "api_guest_user", "default_user"] + system_learning_user_ids:
                    # If a specific user is asking, include their learnings and general system learnings
                    if entry_user_id == user_id_context or entry_user_id in system_learning_user_ids:
                        learnings.append(entry)
                elif not user_id_context: # If no specific user (e.g., an admin view or general log)
                    # Include all learnings, or decide to only show system ones. For now, let's include all.
                    learnings.append(entry)
                elif user_id_context in ["unknown_user", "api_guest_user", "default_user"]: # For guest/unknown, only show system learnings
                    if entry_user_id in system_learning_user_ids:
                        learnings.append(entry)

            # Final sort and limit after Python-side filtering
            learnings.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            logger.info(f"Retrieved {len(learnings[:limit])} learnings for context '{user_id_context}'.")
            return learnings[:limit]

        except Exception as e:
            logger.error(f"Error retrieving recent learnings: {e}", exc_info=True)
            return []

