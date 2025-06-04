import json
import uuid
import logging
import sqlite3
from datetime import datetime, timezone, date, time
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any, Tuple, Union # Added Union
from typing_extensions import TypedDict
from sentence_transformers import SentenceTransformer
import numpy as np

from eidos_agent.core.config import Config, EthosConfig
from eidos_agent.utils.logger import get_logger
# Updated import for Chronos models
from eidos_agent.persona_logic.chronos_engine.models import ActivitySlot, PathosEvent, ActivitySlotDetails, PathosEventDetails
from eidos_agent.persona_logic.social_graph.models import NPCProfile # Added NPCProfile import

logger = get_logger(__name__)

class MemoryEntry(TypedDict, total=False):
    id: str
    timestamp: str
    type: Literal[
        'interaction', 'context_summary', 'ambient_log', 'presence',
        'dream', 'reflection', 'feedback', 'system', 'task_outcome',
        'ha_interaction', 'info_query_time', 'info_query_math',
        'info_query_weather', 'info_query_wolfram_query', 'info_query_other',
        'task_failure', 'task_fallback_wa', 'document_chunk', 'vision_analysis',
        'sensor_reading', 'motion_event', 'daily_briefing',
        'pending_context_document', 'chat_storage', # chat_storage type
        'user_fact', 'world_knowledge', 'learned_correction',
        'proactive_action_record', 'queued_discussion_point',
        'learned_feedback_insight', 'suggestion_reflection',
        'aspiration', # Added from broken EthosCore
        'dream_narrative_from_node',
        'firmament_activity_log',
        'received_subconscious_intention',
        'npc_dialogue_event' # New type added
    ]
    content: str
    embedding: Optional[list[float]]
    metadata: Dict[str, Any]
    salience: Optional[float]

class MemoryStorage:
    def __init__(self, config: Config):
        self.config = config
        self.ethos_config: EthosConfig = config.get_ethos_config()
        self.memory_db_path = Path(self.ethos_config['memory_db_path'])
        self.embedder_name = self.ethos_config['embedding_model_name']
        self.embedder_dimension = 0
        self.embedder: Optional[SentenceTransformer] = None
        self._load_embedder()
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db_exists()
        logger.info(f"MemoryStorage initialized. DB: {self.memory_db_path}")

    def _load_embedder(self):
        try:
            self.embedder = SentenceTransformer(self.embedder_name)
            if hasattr(self.embedder, 'encode'):
                dummy_embedding = self.embedder.encode("test")
                self.embedder_dimension = len(dummy_embedding)
                logger.info(f"Embedder '{self.embedder_name}' loaded (dim: {self.embedder_dimension}).")
            else: raise ValueError("Loaded object no 'encode' method.")
        except Exception as e: logger.error(f"Failed to load embedder '{self.embedder_name}': {e}", exc_info=True); self.embedder = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            try:
                self.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.memory_db_path, check_same_thread=False, timeout=10)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA busy_timeout = 5000;")
            except sqlite3.Error as e: logger.error(f"Error connecting to SQLite DB: {e}", exc_info=True); raise
        return self._conn

    def close_connection(self):
        if self._conn: self._conn.close(); self._conn = None; logger.debug("SQLite connection closed.")

    def _ensure_db_exists(self):
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, type TEXT NOT NULL, content TEXT NOT NULL,
                    embedding BLOB, metadata TEXT, salience REAL
                )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_ts ON memories (timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memories (type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_salience ON memories (salience)")
            try: cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_user_id ON memories (json_extract(metadata, '$.user_id'))")
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" not in str(oe).lower(): raise
                logger.warning("json_extract not available for memories.user_id index.")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_schedule_items (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, date TEXT NOT NULL, start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL, slot_name TEXT, activity_title TEXT NOT NULL, activity_type TEXT,
                    activity_details TEXT, generated_at TEXT NOT NULL )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_sched_user_date ON daily_schedule_items (user_id, date)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pathos_events (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL, event_type TEXT NOT NULL, description TEXT, location TEXT,
                    details TEXT, created_at TEXT NOT NULL )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pathos_events_user_dates ON pathos_events (user_id, start_date, end_date)")

            # Create npc_profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS npc_profiles (
                    npc_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role_description TEXT,
                    persona_summary_prompt TEXT,
                    relationship_strength REAL DEFAULT 0.0,
                    known_facts_by_pathos TEXT,
                    pathos_notes_on_npc TEXT,
                    interaction_history_summary TEXT,
                    last_interaction_ts TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_npc_name ON npc_profiles (name COLLATE NOCASE)")

            conn.commit(); logger.info("DB tables (memories, schedules, events, npc_profiles) ensured.")
        except sqlite3.Error as e: logger.error(f"Error ensuring DB tables: {e}", exc_info=True); raise

    def _row_to_npc_profile(self, row: Union[sqlite3.Row, Dict[str, Any]]) -> Optional[NPCProfile]:
        if not row:
            return None
        try:
            data = dict(row)
            if 'known_facts_by_pathos' in data and isinstance(data['known_facts_by_pathos'], str):
                data['known_facts_by_pathos'] = json.loads(data['known_facts_by_pathos'])
            else:
                data['known_facts_by_pathos'] = data.get('known_facts_by_pathos', [])

            for field_name in ["last_interaction_ts", "created_at", "updated_at"]:
                if data.get(field_name) and isinstance(data[field_name], str):
                    dt_obj = datetime.fromisoformat(data[field_name].replace("Z", "+00:00"))
                    data[field_name] = dt_obj.replace(tzinfo=timezone.utc) if dt_obj.tzinfo is None else dt_obj.astimezone(timezone.utc)
                else:
                    data[field_name] = None # Ensure it's None if missing or not a string
            return NPCProfile(**data)
        except (json.JSONDecodeError, ValueError, TypeError, Exception) as e: # Broader exception for Pydantic validation too
            logger.error(f"Error converting row to NPCProfile for npc_id {row.get('npc_id', 'UNKNOWN')}: {e}", exc_info=True)
            return None

    def _serialize_embedding(self, embedding: Optional[List[float]]) -> Optional[bytes]:
        if embedding is None: return None
        return np.array(embedding, dtype=np.float32).tobytes()

    def _deserialize_embedding(self, blob: Optional[bytes]) -> Optional[List[float]]:
        if blob is None: return None
        if self.embedder_dimension > 0 and len(blob) != self.embedder_dimension * 4:
            logger.warning(f"Embedding blob size mismatch. Expected {self.embedder_dimension*4}, got {len(blob)}."); return None
        try: return np.frombuffer(blob, dtype=np.float32).tolist()
        except ValueError as e: logger.warning(f"Could not deserialize embedding blob: {e}"); return None

    def _row_to_entry(self, row: Union[sqlite3.Row, Dict[str, Any]]) -> MemoryEntry:
        data = dict(row) if isinstance(row, sqlite3.Row) else row
        metadata = {}
        if meta_str := data.get('metadata'):
            try: metadata = json.loads(meta_str)
            except json.JSONDecodeError: logger.warning(f"Could not decode metadata for entry {data.get('id', 'N/A')}")
        return MemoryEntry(
            id=str(data.get('id', uuid.uuid4())), timestamp=str(data.get('timestamp', datetime.now(timezone.utc).isoformat())),
            type=data.get('type'), content=str(data.get('content', "")), # type: ignore
            embedding=self._deserialize_embedding(data.get('embedding')), metadata=metadata, salience=data.get('salience')
        )

    def add_entry(self, entry_data: Dict) -> MemoryEntry:
        if 'content' not in entry_data or 'type' not in entry_data: raise ValueError("Entry needs 'content' and 'type'")
        entry_id = str(entry_data.get('id', uuid.uuid4())); content = str(entry_data['content'])
        entry_type = str(entry_data['type']); timestamp = entry_data.get('timestamp', datetime.now(timezone.utc).isoformat())
        metadata = entry_data.get('metadata', {}); salience = entry_data.get('salience')
        embedding_blob = None
        if self.embedder and isinstance(content, str) and content.strip() and entry_type not in ['pending_context_document', 'proactive_action_record', 'chat_storage']:
            try:
                max_len = self.ethos_config.get('embedding_max_text_length', 2560)
                embedding = self.embedder.encode(content[:max_len]).tolist()
                embedding_blob = self._serialize_embedding(embedding)
            except Exception as e: logger.error(f"Failed to embed content: {content[:50]}... Error: {e}")
        new_entry = MemoryEntry(id=entry_id, timestamp=timestamp, type=entry_type, content=content, embedding=(embedding if embedding_blob else None), metadata=metadata, salience=salience) # type: ignore
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("INSERT INTO memories (id, timestamp, type, content, embedding, metadata, salience) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET timestamp=excluded.timestamp, type=excluded.type, content=excluded.content, embedding=excluded.embedding, metadata=excluded.metadata, salience=excluded.salience", (entry_id, timestamp, entry_type, content, embedding_blob, json.dumps(metadata), salience))
            conn.commit(); return new_entry
        except sqlite3.Error as e: logger.error(f"Error adding/updating entry {entry_id}: {e}", exc_info=True); raise

    def get_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT * FROM memories WHERE id = ?", (entry_id,)); row = cursor.fetchone()
            return self._row_to_entry(row) if row else None
        except sqlite3.Error as e: logger.error(f"Error getting entry {entry_id}: {e}", exc_info=True); return None

    def update_entry(self, entry_id: str, updates: Dict) -> bool:
        allowed = {'content', 'metadata', 'salience', 'type', 'timestamp'}; fields, values = [], []
        for k, v in updates.items():
            if k in allowed:
                fields.append(f"{k} = ?"); values.append(json.dumps(v) if k == 'metadata' else v)
        if 'content' in updates and self.embedder and (entry := self.get_entry(entry_id)) and entry.get('type') not in ['pending_context_document', 'proactive_action_record', 'chat_storage']:
            try:
                max_len = self.ethos_config.get('embedding_max_text_length', 2560)
                emb_blob = self._serialize_embedding(self.embedder.encode(str(updates['content'])[:max_len]).tolist())
                fields.append("embedding = ?"); values.append(emb_blob)
            except Exception as e: logger.error(f"Failed to re-embed content for {entry_id}: {e}")
        if not fields: return False
        values.append(entry_id); sql = f"UPDATE memories SET {', '.join(fields)} WHERE id = ?"
        try:
            conn = self._get_connection(); cursor = conn.cursor(); cursor.execute(sql, tuple(values)); conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e: logger.error(f"Error updating entry {entry_id}: {e}", exc_info=True); return False

    def delete_entry(self, entry_id: str) -> bool:
        try:
            conn = self._get_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM memories WHERE id = ?", (entry_id,)); conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e: logger.error(f"Error deleting entry {entry_id}: {e}", exc_info=True); return False

    def find_similar(self, query_text: str, top_k: int = 5, allowed_types: Optional[List[str]] = None, threshold: float = 0.5) -> List[Tuple[float, MemoryEntry]]:
        if not self.embedder or self.embedder_dimension == 0 or not query_text: return []
        try: max_len = self.ethos_config.get('embedding_max_text_length', 2560); query_emb = np.array(self.embedder.encode(query_text[:max_len]), dtype=np.float32)
        except Exception as e: logger.error(f"Failed to embed query '{query_text[:50]}...': {e}"); return []
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            sql = "SELECT * FROM memories WHERE embedding IS NOT NULL AND type != 'pending_context_document' AND type != 'chat_storage'"
            params: List[Any] = []
            if allowed_types:
                valid_types = [t for t in allowed_types if t not in ['pending_context_document', 'chat_storage']]
                if valid_types: sql += f" AND type IN ({','.join('?'*len(valid_types))})"; params.extend(valid_types)
                else: return []
            sql += " ORDER BY timestamp DESC LIMIT 500"; cursor.execute(sql, tuple(params)); rows = cursor.fetchall()
        except sqlite3.Error as e: logger.error(f"Error retrieving for similarity search: {e}", exc_info=True); return []
        sims = []
        for row in rows:
            entry = self._row_to_entry(row)
            if entry['embedding'] is None or len(entry['embedding']) != self.embedder_dimension: continue
            try:
                entry_emb = np.array(entry['embedding'], dtype=np.float32); norm_q, norm_e = np.linalg.norm(query_emb), np.linalg.norm(entry_emb)
                sim = np.dot(query_emb, entry_emb) / (norm_q * norm_e) if norm_q > 1e-6 and norm_e > 1e-6 else 0.0
                if sim >= threshold: sims.append((float(sim), entry))
            except Exception as e: logger.warning(f"Could not calc similarity for entry {entry['id']}: {e}")
        return sorted(sims, key=lambda item: item[0], reverse=True)[:top_k]

    def clear_all_memory(self) -> bool:
        logger.warning("Attempting to clear all memory tables (memories, schedules, events).")
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories"); logger.info("Cleared 'memories' table.")
            cursor.execute("DELETE FROM daily_schedule_items"); logger.info("Cleared 'daily_schedule_items' table.")
            cursor.execute("DELETE FROM pathos_events"); logger.info("Cleared 'pathos_events' table.")
            conn.commit(); return True
        except sqlite3.Error as e: logger.error(f"Error clearing memory tables: {e}", exc_info=True); conn.rollback(); return False

    def delete_entries_by_user_id(self, user_id: str) -> bool:
        if not user_id or not user_id.strip(): return False
        logger.warning(f"Deleting ALL entries for user_id: '{user_id}'.")
        conn = self._get_connection(); cursor = conn.cursor(); total_deleted = 0
        try:
            try: cursor.execute("DELETE FROM memories WHERE json_extract(metadata, '$.user_id') = ?", (user_id,))
            except sqlite3.OperationalError as oe:
                if "no such function: json_extract" not in str(oe).lower(): raise
                logger.warning(f"json_extract not available for deleting 'memories' for user '{user_id}'. This may leave some entries.")
            total_deleted += cursor.rowcount
            cursor.execute("DELETE FROM daily_schedule_items WHERE user_id = ?", (user_id,)); total_deleted += cursor.rowcount
            cursor.execute("DELETE FROM pathos_events WHERE user_id = ?", (user_id,)); total_deleted += cursor.rowcount
            conn.commit(); logger.info(f"Total {total_deleted} entries processed for deletion for user '{user_id}'."); return True
        except sqlite3.Error as e: logger.error(f"SQLite Error deleting for user '{user_id}': {e}", exc_info=True); conn.rollback(); return False

    async def save_schedule_to_db(self, schedule: List[ActivitySlot], user_id: str):
        if not schedule: return
        conn = self._get_connection(); cursor = conn.cursor()
        try:
            date_str = schedule[0].date.isoformat()
            cursor.execute("DELETE FROM daily_schedule_items WHERE user_id = ? AND date = ?", (user_id, date_str))
            items = [(item.id, item.user_id, item.date.isoformat(), item.start_time.isoformat(timespec='minutes'), item.end_time.isoformat(timespec='minutes'), item.slot_name, item.activity_title, item.activity_type, item.activity_details.model_dump_json(), item.generated_at.isoformat()) for item in schedule]
            cursor.executemany("INSERT INTO daily_schedule_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", items)
            conn.commit(); logger.info(f"Saved {len(schedule)} schedule items for user '{user_id}' on {date_str}.")
        except sqlite3.Error as e: logger.error(f"Error saving schedule for user '{user_id}': {e}", exc_info=True); conn.rollback()

    async def load_schedule_from_db(self, target_date: date, user_id: str) -> List[ActivitySlot]:
        conn = self._get_connection(); cursor = conn.cursor(); items: List[ActivitySlot] = []
        try:
            cursor.execute("SELECT * FROM daily_schedule_items WHERE user_id = ? AND date = ? ORDER BY start_time ASC", (user_id, target_date.isoformat()))
            for row_data in map(dict, cursor.fetchall()):
                try:
                    details_dict = json.loads(row_data['activity_details']) if row_data['activity_details'] else {}
                    data_model = {**row_data, 'activity_details': ActivitySlotDetails(**details_dict)}
                    # Convert date/time strings back to objects
                    data_model['date'] = date.fromisoformat(data_model['date'])
                    data_model['start_time'] = time.fromisoformat(data_model['start_time'])
                    data_model['end_time'] = time.fromisoformat(data_model['end_time'])
                    data_model['generated_at'] = datetime.fromisoformat(data_model['generated_at'].replace("Z", "+00:00"))
                    items.append(ActivitySlot(**data_model))
                except (json.JSONDecodeError, ValueError, TypeError) as e: logger.error(f"Error parsing schedule item ID {row_data.get('id')}: {e}", exc_info=True)
        except sqlite3.Error as e: logger.error(f"Error loading schedule for user '{user_id}': {e}", exc_info=True)
        return items

    async def add_event_to_db(self, event: PathosEvent) -> bool:
        conn = self._get_connection(); cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO pathos_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, start_date=excluded.start_date, end_date=excluded.end_date, event_type=excluded.event_type, description=excluded.description, location=excluded.location, details=excluded.details",
                           (event.id, event.user_id, event.title, event.start_date.isoformat(), event.end_date.isoformat(), event.event_type, event.description, event.location, event.details.model_dump_json(), event.created_at.isoformat()))
            conn.commit(); logger.info(f"Added/Updated event '{event.title}' (ID: {event.id})."); return True
        except sqlite3.Error as e: logger.error(f"Error adding event '{event.title}': {e}", exc_info=True); conn.rollback(); return False

    async def get_events_for_date_range(self, user_id: str, range_start_date: date, range_end_date: date) -> List[PathosEvent]:
        conn = self._get_connection(); cursor = conn.cursor(); events: List[PathosEvent] = []
        try:
            cursor.execute("SELECT * FROM pathos_events WHERE user_id = ? AND start_date <= ? AND end_date >= ? ORDER BY start_date ASC", (user_id, range_end_date.isoformat(), range_start_date.isoformat()))
            for row_data in map(dict, cursor.fetchall()):
                try:
                    details_dict = json.loads(row_data['details']) if row_data['details'] else {}
                    data_model = {**row_data, 'details': PathosEventDetails(**details_dict)}
                    data_model['start_date'] = date.fromisoformat(data_model['start_date'])
                    data_model['end_date'] = date.fromisoformat(data_model['end_date'])
                    data_model['created_at'] = datetime.fromisoformat(data_model['created_at'].replace("Z", "+00:00"))
                    events.append(PathosEvent(**data_model))
                except (json.JSONDecodeError, ValueError, TypeError) as e: logger.error(f"Error parsing event ID {row_data.get('id')}: {e}", exc_info=True)
        except sqlite3.Error as e: logger.error(f"Error fetching events for user '{user_id}': {e}", exc_info=True)
        return events

    async def get(self, key: str) -> Optional[Any]:
        entry = self.get_entry(key) # This is synchronous but should be fine for this use case
        if entry and entry.get('type') == 'chat_storage' and 'content' in entry:
            content_str = entry['content']
            try: return json.loads(content_str) # Chat states are stored as JSON strings
            except json.JSONDecodeError: logger.error(f"Failed to parse chat_storage content for key '{key}' as JSON."); return content_str # Fallback to raw string
        return None

    async def set(self, key: str, value: Any) -> bool:
        try:
            content_to_store = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            entry_data = {'id': key, 'type': 'chat_storage', 'content': content_to_store, 'timestamp': datetime.now(timezone.utc).isoformat(), 'metadata': {'storage_type': 'key_value_chat'}, 'salience': None}
            self.add_entry(entry_data) # Synchronous add_entry
            return True
        except Exception as e: logger.error(f"Error in async set for key '{key}': {e}", exc_info=True); return False

    async def delete(self, key: str) -> bool:
        try: return self.delete_entry(key) # Synchronous delete_entry
        except Exception as e: logger.error(f"Error in async delete for key '{key}': {e}", exc_info=True); return False

    async def get_entries_by_type_and_user(self, entry_type: str, user_id: str, limit: int = 20) -> List[MemoryEntry]:
        """
        Retrieve memory entries of a specific type for a specific user, limited by the given number.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower():
                can_use_json_extract = False
            else:
                logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True)
                can_use_json_extract = False

        sql_query = ""
        params: List[Any] = []

        if can_use_json_extract:
            sql_query = """
                SELECT * FROM memories
                WHERE type = ?
                  AND json_extract(metadata, '$.user_id') = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = [entry_type, user_id, limit]
        else:
            logger.warning(f"json_extract not available for get_entries_by_type_and_user (type: {entry_type}, user: {user_id}). Falling back to Python filter.")
            sql_query = "SELECT * FROM memories WHERE type = ? ORDER BY timestamp DESC LIMIT ?"
            params = [entry_type, limit * 5] # Fetch more to allow for Python filtering

        try:
            cursor.execute(sql_query, tuple(params))
            rows = cursor.fetchall()
            
            entries: List[MemoryEntry] = []
            for row_data_raw in rows:
                entry = self._row_to_entry(dict(row_data_raw)) # Ensure row_data_raw is dict for _row_to_entry
                if not can_use_json_extract:
                    metadata = entry.get('metadata', {})
                    if metadata.get('user_id') != user_id:
                        continue
                entries.append(entry)
            
            if not can_use_json_extract:
                entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                entries = entries[:limit]
            return entries
        except Exception as e:
            logger.error(f"Error retrieving entries by type '{entry_type}' and user '{user_id}': {e}", exc_info=True)
            return []

    # --- NPC Profile CRUD ---

    def save_npc_profile(self, profile: NPCProfile) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        profile.updated_at = datetime.now(timezone.utc) # Always update 'updated_at'

        sql = """
            INSERT INTO npc_profiles (
                npc_id, name, role_description, persona_summary_prompt,
                relationship_strength, known_facts_by_pathos, pathos_notes_on_npc,
                interaction_history_summary, last_interaction_ts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(npc_id) DO UPDATE SET
                name=excluded.name, role_description=excluded.role_description,
                persona_summary_prompt=excluded.persona_summary_prompt,
                relationship_strength=excluded.relationship_strength,
                known_facts_by_pathos=excluded.known_facts_by_pathos,
                pathos_notes_on_npc=excluded.pathos_notes_on_npc,
                interaction_history_summary=excluded.interaction_history_summary,
                last_interaction_ts=excluded.last_interaction_ts,
                updated_at=excluded.updated_at
        """
        try:
            cursor.execute(sql, (
                profile.npc_id, profile.name, profile.role_description, profile.persona_summary_prompt,
                profile.relationship_strength, json.dumps(profile.known_facts_by_pathos), profile.pathos_notes_on_npc,
                profile.interaction_history_summary,
                profile.last_interaction_ts.isoformat() if profile.last_interaction_ts else None,
                profile.created_at.isoformat(), profile.updated_at.isoformat()
            ))
            conn.commit()
            logger.info(f"Saved/Updated NPC profile: {profile.name} (ID: {profile.npc_id})")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving NPC profile {profile.name} (ID: {profile.npc_id}): {e}", exc_info=True)
            conn.rollback()
            return False

    def get_npc_profile_by_id(self, npc_id: str) -> Optional[NPCProfile]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM npc_profiles WHERE npc_id = ?", (npc_id,))
            row = cursor.fetchone()
            return self._row_to_npc_profile(row)
        except sqlite3.Error as e:
            logger.error(f"Error getting NPC profile by ID {npc_id}: {e}", exc_info=True)
            return None

    def get_npc_profile_by_name(self, name: str) -> Optional[NPCProfile]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM npc_profiles WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            return self._row_to_npc_profile(row)
        except sqlite3.Error as e:
            logger.error(f"Error getting NPC profile by name '{name}': {e}", exc_info=True)
            return None

    def update_npc_profile_fields(self, npc_id: str, updates: Dict[str, Any]) -> bool:
        if not updates: return False

        valid_fields = getattr(NPCProfile, '__annotations__', {}).keys()
        for key in updates.keys():
            if key not in valid_fields:
                logger.error(f"Invalid field '{key}' for NPCProfile update.")
                return False

        set_clauses = [f"{field_name} = ?" for field_name in updates.keys()]
        values = []
        for field_name, value in updates.items():
            if field_name == "known_facts_by_pathos": values.append(json.dumps(value))
            elif isinstance(value, datetime): values.append(value.isoformat())
            else: values.append(value)

        set_clauses.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(npc_id)

        sql = f"UPDATE npc_profiles SET {', '.join(set_clauses)} WHERE npc_id = ?"
        conn = self._get_connection(); cursor = conn.cursor()
        try:
            cursor.execute(sql, tuple(values))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error updating NPC fields for ID {npc_id}: {e}", exc_info=True)
            conn.rollback()
            return False

    def delete_npc_profile(self, npc_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM npc_profiles WHERE npc_id = ?", (npc_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Deleted NPC profile with ID: {npc_id}")
                return True
            logger.warning(f"No NPC profile found with ID: {npc_id} to delete.")
            return False
        except sqlite3.Error as e:
            logger.error(f"Error deleting NPC profile with ID {npc_id}: {e}", exc_info=True)
            conn.rollback()
            return False

    # Placeholder for list_npc_profiles
    def list_npc_profiles(self, limit: int = 100, offset: int = 0) -> List[NPCProfile]:
        logger.warning("list_npc_profiles is a placeholder and not fully implemented.")
        # This would typically fetch from DB, order, limit, offset
        # For now, returns empty or a dummy example if you have one.
        return []

    # Placeholder for add_fact_to_npc_profile
    def add_fact_to_npc_profile(self, npc_id: str, fact: str) -> bool:
        logger.warning(f"add_fact_to_npc_profile is a placeholder for {npc_id} with fact '{fact}'. Not fully implemented.")
        # This would typically fetch profile, append to known_facts_by_pathos, then save.
        # For now, simulates success.
        # Example sketch:
        # profile = self.get_npc_profile_by_id(npc_id)
        # if profile:
        #     if fact not in profile.known_facts_by_pathos:
        #         profile.known_facts_by_pathos.append(fact)
        #         return self.save_npc_profile(profile)
        # return False
        return True # Simulate success for now