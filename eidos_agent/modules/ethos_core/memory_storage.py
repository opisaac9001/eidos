import json
import uuid
import logging
import sqlite3
from datetime import datetime, timezone 
from pathlib import Path
from typing import Literal, Optional, Self, List, Dict, Any, Tuple 
from typing_extensions import TypedDict 
from sentence_transformers import SentenceTransformer
import numpy as np

# Adjust import path as necessary
from eidos_agent.core.config import Config, EthosConfig
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

# Expanded MemoryEntry to include potential new fields managed by EthosCore
class MemoryEntry(TypedDict):
    id: str
    timestamp: str # ISO 8601 format
    type: Literal[
        'interaction', 'context_summary', 'ambient_log', 'presence',
        'dream', 'reflection', 'feedback', 'system', 'task_outcome',
        'ha_interaction', 'info_query_time', 'info_query_math',
        'info_query_weather', 'info_query_wolfram_query', 'info_query_other',
        'task_failure', 'task_fallback_wa', 'document_chunk', 'vision_analysis',
        'sensor_reading', 'motion_event', 'daily_briefing',
        'pending_context_document', # Added new type for temporary document context
        'user_fact', 'world_knowledge', 'learned_correction', # Added from EthosCore
        'proactive_action_record', 'queued_discussion_point' # Added from EthosCore
    ]
    content: str # The main textual content or structured data as JSON string
    embedding: Optional[list[float]] # Embedding of 'content' or key parts
    metadata: Dict[str, Any] # Flexible metadata (e.g., source, confidence, user_id, source_document_id, chunk_index, location, unit)
    salience: Optional[float]

class MemoryStorage:
    """
    Handles the low-level storage, retrieval, and embedding
    of memory entries for the Ethos Core using SQLite.
    """
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
        logger.info(f"MemoryStorage initialized. Using DB: {self.memory_db_path}")

    def _load_embedder(self):
        """Loads the SentenceTransformer model."""
        try:
            self.embedder = SentenceTransformer(self.embedder_name)
            # Check if model loading actually worked and provides an encode method
            if hasattr(self.embedder, 'encode'):
                dummy_embedding = self.embedder.encode("test")
                self.embedder_dimension = len(dummy_embedding)
                logger.info(f"SentenceTransformer model '{self.embedder_name}' loaded (dimension: {self.embedder_dimension}).")
            else:
                raise ValueError("Loaded object does not have an 'encode' method.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model '{self.embedder_name}': {e}", exc_info=True)
            self.embedder = None
            self.embedder_dimension = 0

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes and returns a database connection."""
        if self._conn is None:
            try:
                self.memory_db_path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.memory_db_path, check_same_thread=False, timeout=10)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA busy_timeout = 5000;")
                logger.debug("SQLite connection established.")
            except sqlite3.Error as e:
                logger.error(f"Error connecting to SQLite DB at {self.memory_db_path}: {e}", exc_info=True)
                raise
        return self._conn

    def close_connection(self):
        """Closes the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("SQLite connection closed.")

    def _ensure_db_exists(self):
        """Creates the memory table if it doesn't exist."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    metadata TEXT,
                    salience REAL
                )
            """)
            # Add indexes for faster querying
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memories (timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories (type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_salience ON memories (salience)")
            # Add index for date extraction if using SQLite date functions frequently
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_date ON memories (date(timestamp))")
            # Add index for user_id in metadata for faster user-specific queries
            # This requires json_extract support or might be less efficient on older SQLite
            try:
                 cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_user_id ON memories (json_extract(metadata, '$.user_id'))")
            except sqlite3.OperationalError as oe:
                 if "no such function: json_extract" in str(oe).lower():
                      logger.warning("SQLite json_extract not available, cannot create index on user_id in metadata.")
                 else:
                      logger.error(f"Error creating index on user_id: {oe}", exc_info=True)

            conn.commit()
            logger.debug("Memory table ensured in SQLite DB.")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring memory table exists: {e}", exc_info=True)
            raise

    def _serialize_embedding(self, embedding: Optional[List[float]]) -> Optional[bytes]:
        """Converts embedding list to bytes for storage."""
        if embedding is None: return None
        return np.array(embedding, dtype=np.float32).tobytes()

    def _deserialize_embedding(self, embedding_blob: Optional[bytes]) -> Optional[List[float]]:
        """Converts bytes back to embedding list."""
        if embedding_blob is None: return None
        # Check dimension only if embedder was loaded successfully
        if self.embedder_dimension > 0:
            expected_bytes = self.embedder_dimension * 4
            if len(embedding_blob) != expected_bytes:
                 logger.warning(f"Embedding blob size mismatch. Expected {expected_bytes}, got {len(embedding_blob)}. Cannot deserialize.")
                 return None
        try:
            # Use float32 as it's common for embeddings
            return np.frombuffer(embedding_blob, dtype=np.float32).tolist()
        except ValueError as e:
             logger.warning(f"Could not deserialize embedding blob (length {len(embedding_blob)}): {e}")
             return None

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Converts a database row to a MemoryEntry dictionary."""
        metadata = {}
        # Use bracket notation with check for existence
        metadata_str = row['metadata'] if 'metadata' in row.keys() else None
        if metadata_str:
            try: metadata = json.loads(metadata_str)
            except json.JSONDecodeError: logger.warning(f"Could not decode metadata JSON for entry {row.get('id', 'UNKNOWN')}: {metadata_str}") # Use .get() here as fallback

        # Use bracket notation for required fields, assuming they exist based on schema
        # Use .keys() check for optional fields like embedding/salience if they might be NULL
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
            embedding=self._deserialize_embedding(embedding_blob),
            metadata=metadata,
            salience=salience
        )


    def add_entry(self, entry_data: Dict) -> MemoryEntry:
        """Adds a new memory entry to the database."""
        if 'content' not in entry_data or 'type' not in entry_data:
            raise ValueError("Memory entry must contain 'content' and 'type'")

        entry_id = str(entry_data.get('id', uuid.uuid4()))
        content = str(entry_data['content'])
        entry_type = str(entry_data['type'])
        timestamp = entry_data.get('timestamp', datetime.now(timezone.utc).isoformat()) # Ensure timezone aware
        metadata = entry_data.get('metadata', {})
        salience = entry_data.get('salience') # Can be None

        embedding = None
        embedding_blob = None
        # Generate embedding only if embedder is loaded, content is suitable,
        # AND it's not a temporary type that doesn't need embedding for RAG
        if self.embedder and isinstance(content, str) and content.strip() and entry_type not in ['pending_context_document', 'proactive_action_record']:
            try:
                # Ensure content isn't excessively long for embedding model
                max_embed_len = self.ethos_config.get('embedding_max_text_length', 2560) # Use config
                embedding = self.embedder.encode(content[:max_embed_len]).tolist()
                embedding_blob = self._serialize_embedding(embedding)
            except Exception as e:
                logger.error(f"Failed to generate embedding for content: {content[:50]}... Error: {e}")

        # Create the full entry dict before insertion
        new_entry = MemoryEntry(
            id=entry_id, timestamp=timestamp, type=entry_type, content=content,
            embedding=embedding, metadata=metadata, salience=salience
        )

        try:
            conn = self._get_connection()
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
            return new_entry # Return the potentially updated entry dict
        except sqlite3.Error as e:
            logger.error(f"Error adding/updating memory entry {entry_id} in DB: {e}", exc_info=True)
            raise # Re-raise after logging

    def get_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a specific memory entry by ID."""
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT * FROM memories WHERE id = ?", (entry_id,))
            row = cursor.fetchone()
            return self._row_to_entry(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting entry {entry_id} from DB: {e}", exc_info=True)
            return None

    def get_all_entries(self) -> List[MemoryEntry]:
        """Return all current memory entries."""
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("SELECT * FROM memories ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting all entries from DB: {e}", exc_info=True)
            return []

    def update_entry(self, entry_id: str, updates: Dict) -> bool:
        """Update specific fields of an existing memory entry."""
        allowed_updates = {'content', 'metadata', 'salience', 'type', 'timestamp'}
        update_fields = []
        update_values = []

        for key, value in updates.items():
            if key in allowed_updates:
                update_fields.append(f"{key} = ?")
                # Serialize metadata, handle None for salience
                if key == 'metadata':
                    update_values.append(json.dumps(value))
                elif key == 'salience' and value is None:
                     update_values.append(None) # Explicitly set NULL
                else:
                    update_values.append(value)
            else:
                logger.warning(f"Attempted to update disallowed field '{key}' on entry {entry_id}")

        # Re-embed if content changed and embedder exists, AND it's not a temporary type
        # Need to fetch the existing entry to check its type
        existing_entry = self.get_entry(entry_id)
        if 'content' in updates and self.embedder and existing_entry and existing_entry.get('type') not in ['pending_context_document', 'proactive_action_record']:
            try:
                max_embed_len = self.ethos_config.get('embedding_max_text_length', 2560)
                new_embedding = self.embedder.encode(str(updates['content'])[:max_embed_len]).tolist()
                embedding_blob = self._serialize_embedding(new_embedding)
                update_fields.append("embedding = ?")
                update_values.append(embedding_blob)
            except Exception as e:
                logger.error(f"Failed to re-embed updated content for {entry_id}: {e}")

        if not update_fields:
            logger.debug(f"No valid fields to update for entry {entry_id}")
            return False

        update_values.append(entry_id) # Add entry_id for WHERE clause
        sql = f"UPDATE memories SET {', '.join(update_fields)} WHERE id = ?"

        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute(sql, tuple(update_values))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.debug(f"Updated memory entry {entry_id} with fields: {list(updates.keys())}")
            else:
                logger.warning(f"Update command executed but no rows affected for entry {entry_id} (might not exist).")
            return updated
        except sqlite3.Error as e:
            logger.error(f"Error updating entry {entry_id} in DB: {e}", exc_info=True)
            return False

    def delete_entry(self, entry_id: str) -> bool:
        """Remove a memory entry by ID."""
        try:
            conn = self._get_connection(); cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted memory entry {entry_id} from DB.")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting entry {entry_id} from DB: {e}", exc_info=True)
            return False

    def find_similar(
        self,
        query_text: str,
        top_k: int = 5,
        threshold: float = 0.5,
        allowed_types: Optional[List[str]] = None
    ) -> List[Tuple[float, MemoryEntry]]:
        """Finds similar entries using embeddings stored in the DB."""
        if not self.embedder or self.embedder_dimension == 0:
            logger.warning("Embedder not available or dimension unknown, cannot perform similarity search.")
            return []
        if not query_text:
            logger.warning("Similarity search query is empty.")
            return []

        try:
            # Ensure query isn't too long for embedder
            max_embed_len = self.ethos_config.get('embedding_max_text_length', 2560)
            query_embedding_np = np.array(self.embedder.encode(query_text[:max_embed_len]), dtype=np.float32)
        except Exception as e:
            logger.error(f"Failed to generate embedding for query '{query_text[:50]}...': {e}")
            return []

        try:
            conn = self._get_connection(); cursor = conn.cursor()
            # Base query selects entries with non-null embeddings AND are NOT pending_context_document
            sql = "SELECT * FROM memories WHERE embedding IS NOT NULL AND type != 'pending_context_document'"
            params = []
            # Add type filtering if specified
            if allowed_types:
                # Ensure 'pending_context_document' is not included if allowed_types is specified
                filtered_allowed_types = [t for t in allowed_types if t != 'pending_context_document']
                if filtered_allowed_types:
                    placeholders = ','.join('?' * len(filtered_allowed_types))
                    sql += f" AND type IN ({placeholders})"
                    params.extend(filtered_allowed_types)
                else:
                    # If allowed_types was specified but only contained 'pending_context_document',
                    # or became empty after filtering, the RAG query should return nothing.
                    logger.debug("Allowed types for RAG resulted in no valid types after excluding pending_context_document.")
                    return []


            # Order by timestamp descending to potentially retrieve more recent candidates first
            # Note: This doesn't guarantee finding the *most* similar, just candidates.
            # A real vector index (FAISS, ChromaDB) would be much faster and more accurate for large DBs.
            sql += " ORDER BY timestamp DESC LIMIT 500" # Limit candidates retrieved for performance

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            logger.debug(f"Retrieved {len(rows)} candidate entries from DB for similarity search (Allowed types: {allowed_types}).")
        except sqlite3.Error as e:
            logger.error(f"Error retrieving entries for similarity search: {e}", exc_info=True)
            return []

        similarities = []
        for row in rows:
            entry = self._row_to_entry(row)
            # Ensure embedding exists and has the correct dimension
            if entry['embedding'] is None or len(entry['embedding']) != self.embedder_dimension:
                if entry['embedding'] is not None:
                    logger.warning(f"Skipping entry {entry['id']} with embedding dimension mismatch.")
                continue

            try:
                entry_embedding_np = np.array(entry['embedding'], dtype=np.float32)
                # Calculate cosine similarity
                norm_query = np.linalg.norm(query_embedding_np)
                norm_entry = np.linalg.norm(entry_embedding_np)
                # Avoid division by zero if norms are zero
                if norm_query > 1e-6 and norm_entry > 1e-6:
                    sim = np.dot(query_embedding_np, entry_embedding_np) / (norm_query * norm_entry)
                else:
                    sim = 0.0
                # Add to list if similarity meets threshold
                if sim >= threshold:
                    similarities.append((float(sim), entry))
            except Exception as e:
                logger.warning(f"Could not calculate similarity for entry {entry['id']}: {e}")

        # Sort results by similarity score (descending) and take top_k
        results = sorted(similarities, key=lambda item: item[0], reverse=True)[:top_k]
        logger.debug(f"Found {len(results)} similar entries above threshold {threshold}.")
        return results

    def clear_all_memory(self) -> bool:
        """
        Deletes all entries from the memory table.
        Returns True on success, False on failure.
        """
        logger.warning("Attempting to clear all memory entries from DB.")
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories")
            # VACUUM removed due to transaction error
            # cursor.execute("VACUUM")
            conn.commit()
            logger.info("All memory entries successfully deleted.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error clearing memory table: {e}", exc_info=True)
            conn.rollback()
            return False
        except Exception as e:
             logger.error(f"Unexpected error during memory clearing: {e}", exc_info=True)
             conn.rollback()
             return False

    # --- New Methods for Pending Document Context ---

    def add_pending_document_context(self, user_id: str, filename: str, content: str):
        """Stores document content temporarily for the next user interaction."""
        if not user_id or not content:
            logger.warning("Attempted to add pending document context with missing user_id or content.")
            return

        # Use a consistent ID pattern for easy retrieval/deletion
        entry_id = f"pending_doc_{user_id}"
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = {"user_id": user_id, "filename": filename}

        # Use add_entry which handles ON CONFLICT (replaces previous pending doc for this user)
        self.add_entry({
            "id": entry_id,
            "timestamp": timestamp,
            "type": "pending_context_document",
            "content": content,
            "metadata": metadata,
            "salience": 0.0 # Temporary, not for RAG search
        })
        logger.debug(f"Stored pending document context for user '{user_id}' (filename: {filename}).")

    def get_and_clear_pending_document_context(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Retrieves the pending document context for a user and deletes the entry.
        Returns {'filename': str, 'content': str} or None.
        """
        if not user_id: return None

        entry_id = f"pending_doc_{user_id}"
        entry = self.get_entry(entry_id) # Use existing get_entry

        if entry and entry.get('type') == 'pending_context_document':
            filename = entry.get('metadata', {}).get('filename', 'uploaded_document')
            content = entry.get('content')

            # Delete the temporary entry immediately after retrieval
            self.delete_entry(entry_id)
            logger.debug(f"Retrieved and cleared pending document context for user '{user_id}'.")

            if content:
                return {"filename": filename, "content": content}
            else:
                logger.warning(f"Pending document context for user '{user_id}' found but content was empty.")
                return None
        else:
            logger.debug(f"No pending document context found for user '{user_id}'.")
            return None

    # --- END New Methods ---

    # --- NEW: Method to delete entries by user_id ---
    def delete_entries_by_user_id(self, user_id: str) -> bool:
        """
        Deletes all memory entries associated with a specific user_id from the database.
        This relies on the metadata field containing a 'user_id' key.
        Returns True if the operation was successful (even if no rows were deleted),
        False if an error occurred.
        """
        if not user_id or not user_id.strip():
            logger.warning("Attempted to delete entries for an empty or invalid user_id.")
            return False

        logger.warning(f"MemoryStorage: Attempting to delete ALL entries for user_id: '{user_id}'.")
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Use json_extract to target the user_id within the metadata JSON
            # This is more robust than LIKE '%"user_id": "user_id_value"%'
            sql = "DELETE FROM memories WHERE json_extract(metadata, '$.user_id') = ?"
            cursor.execute(sql, (user_id,))
            conn.commit()
            deleted_count = cursor.rowcount
            logger.info(f"MemoryStorage: Deleted {deleted_count} entries for user_id '{user_id}'.")
            return True
        except sqlite3.OperationalError as oe:
            if "no such function: json_extract" in str(oe).lower():
                logger.error(
                    f"MemoryStorage: Cannot delete entries by user_id ('{user_id}') because "
                    "SQLite json_extract function is not available. "
                    "Manual deletion or database upgrade might be required. No entries were deleted by this operation."
                )
                # IMPORTANT: Do not proceed with a less safe fallback here as it could delete wrong data.
                # The operation is considered failed if json_extract is not available.
                return False
            else:
                logger.error(f"MemoryStorage: SQLite OperationalError deleting entries for user_id '{user_id}': {oe}", exc_info=True)
                conn.rollback()
                return False
        except sqlite3.Error as e:
            logger.error(f"MemoryStorage: SQLite Error deleting entries for user_id '{user_id}': {e}", exc_info=True)
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"MemoryStorage: Unexpected error deleting entries for user_id '{user_id}': {e}", exc_info=True)
            conn.rollback()
            return False