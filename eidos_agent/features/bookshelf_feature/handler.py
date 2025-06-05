from typing import Optional, List, Dict, Any, TypedDict
import uuid
import datetime
import re # For cleaning filenames
import json # For storing TypedDict in MemoryEntry content

# Assuming these are the correct import paths based on prior work
from eidos_agent.integrations.ragbits_bookshelf_client import RagbitsBookshelfClient, DocumentChunkInfo # Import DocumentChunkInfo
from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryStorage, MemoryEntry
from eidos_agent.utils.logger import get_logger
# from eidos_agent.utils.document_parser import fetch_and_parse_url # Conceptual

logger = get_logger(__name__)

# --- Placeholder for URL fetching ---
class PlaceholderURLFetcher:
    async def fetch_and_parse_url(self, url: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[PlaceholderURLFetcher] Attempting to fetch URL: {url}")
        if not url.startswith("http://") and not url.startswith("https://"):
            logger.warning(f"[PlaceholderURLFetcher] Invalid URL format: {url}")
            return None
        # Simulate fetching content
        return {
            "url": url,
            "title": f"Content from {url}",
            "text_content": f"This is simulated text content fetched from the URL: {url}. It would normally contain the actual page text.",
            "metadata": {"source_type": "url_fetch_placeholder"}
        }
# --- End Placeholder ---

class BookshelfDocumentIndex(TypedDict): # For MemoryEntry content/metadata
    doc_id: str
    title: str
    original_source: str # file path or URL
    user_id: str
    added_timestamp: str
    # other useful metadata like file_type, original_metadata from client etc.
    client_doc_metadata: Optional[Dict[str, Any]]
    chunk_count: Optional[int]


class BookshelfHandler:
    def __init__(self, bookshelf_client: RagbitsBookshelfClient, memory_storage: MemoryStorage):
        self.bookshelf_client = bookshelf_client
        self.memory_storage = memory_storage
        self.url_fetcher = PlaceholderURLFetcher() # Using placeholder
        logger.info("BookshelfHandler initialized.")

    def _sanitize_filename_to_title(self, filename: str) -> str:
        # Remove path components
        base_name = filename.split('/')[-1].split('\\')[-1] # Handle both path sep
        # Remove extension
        title_part = base_name.rsplit('.', 1)[0] if '.' in base_name else base_name
        # Replace underscores/hyphens with spaces, capitalize
        title_part = re.sub(r'[_-]', ' ', title_part)
        return title_part.strip().title()


    async def add_document_to_bookshelf(
        self,
        user_id: str,
        file_path_or_url: str,
        document_content: Optional[str] = None, # Allow direct content provision
        document_title: Optional[str] = None,
        is_url: bool = False,
        source_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        logger.info(f"Attempting to add document to bookshelf for user '{user_id}'. Source: '{file_path_or_url}'")

        doc_id = str(uuid.uuid4())
        final_title = document_title
        content_to_process: Optional[str] = document_content
        original_source_for_index = file_path_or_url
        client_metadata = source_metadata.copy() if source_metadata else {}
        client_metadata['user_id'] = user_id # Ensure user_id is in client metadata

        if is_url:
            if not content_to_process: # Only fetch if content not already provided
                logger.debug(f"Fetching content from URL: {file_path_or_url}")
                fetched_data = await self.url_fetcher.fetch_and_parse_url(file_path_or_url)
                if not fetched_data or not fetched_data.get("text_content"):
                    logger.error(f"Failed to fetch or parse content from URL: {file_path_or_url}")
                    return None
                content_to_process = fetched_data["text_content"]
                if not final_title:
                    final_title = fetched_data.get("title") or self._sanitize_filename_to_title(file_path_or_url)
                client_metadata.update(fetched_data.get("metadata", {})) # Merge fetched metadata
            original_source_for_index = file_path_or_url # Ensure URL is stored as original source
        elif content_to_process is None: # Not a URL, and no direct content provided
            # This implies file_path_or_url is a local file path.
            # Placeholder for reading local file content
            try:
                # In a real scenario, this would read from file_path_or_url
                # For placeholder, assume content must be provided directly if not URL.
                logger.warning(f"Local file reading not implemented in placeholder. Content for '{file_path_or_url}' must be provided directly if not a URL.")
                # Simulating failure if content not provided for non-URL
                return {"error": "Local file content must be provided directly for this placeholder version."}
            except Exception as e:
                logger.error(f"Placeholder: Error reading local file '{file_path_or_url}': {e}")
                return None # Or return {"error": str(e)}

        if not content_to_process: # Final check after potential fetching/loading
            logger.error(f"No content to process for document: {file_path_or_url}")
            return None

        if not final_title: # Generate title if still not set
            final_title = self._sanitize_filename_to_title(file_path_or_url)

        client_metadata['original_filename_or_url'] = file_path_or_url # Add original source to client meta

        try:
            # Call to RAG client
            processed_chunk_infos = await self.bookshelf_client.add_document( # now async
                doc_id=doc_id,
                content=content_to_process,
                user_id=user_id, # Pass user_id explicitly
                other_metadata=client_metadata # Pass the prepared client_metadata
            )

            chunks_count = len(processed_chunk_infos) if processed_chunk_infos else 0
            if chunks_count == 0: # Check if client returned empty list of chunks
                 logger.warning(f"Document processing for doc_id '{doc_id}' resulted in zero chunks stored in RAG client. Indexing with 0 chunks.")
            # If client.add_document itself had a critical error and returned None or raised, it would be caught by the general except block.

            # Add to MemoryStorage (index record)
            index_entry_content_typed = BookshelfDocumentIndex( # Use TypedDict for structure
                doc_id=doc_id,
                title=final_title,
                original_source=original_source_for_index, # This was file_path_or_url
                user_id=user_id,
                added_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                client_doc_metadata=client_metadata,
                chunk_count=chunks_count
            )

            # Convert TypedDict to JSON string for MemoryEntry.content
            index_entry_content_json = json.dumps(index_entry_content_typed)

            memory_entry_to_add: MemoryEntry = { # Explicitly type for clarity
                "id": f"bs_idx_{doc_id}", # Unique ID for the index entry
                "type": "bookshelf_document_index",
                "content": index_entry_content_json,
                "metadata": {
                    "user_id": user_id,
                    "doc_id": doc_id, # For easier querying of index entries
                    "title": final_title
                },
                "salience": 0.8 # Default salience for bookshelf index entries
            }
            self.memory_storage.add_entry(memory_entry_to_add)
            logger.info(f"Document '{final_title}' (ID: {doc_id}) added to bookshelf for user '{user_id}'. Indexed with {chunks_count} chunks.")
            return {"doc_id": doc_id, "title": final_title, "chunks_count": chunks_count}

        except Exception as e:
            logger.error(f"Error adding document '{final_title}' to bookshelf: {e}", exc_info=True)
            return None

    async def query_bookshelf(self, user_id: str, query_text: str, top_k: int = 3, query_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        logger.info(f"Querying bookshelf for user '{user_id}' with query: '{query_text[:50]}...', filters: {query_filters}")

        # Construct filter for RAG client, ensuring keys are prefixed for metadata querying
        rag_client_filters = {"metadata.user_id": user_id} # Base filter for user ownership
        if query_filters:
            for key, value in query_filters.items():
                if not key.startswith("metadata."): # Add prefix if not present
                    rag_client_filters[f"metadata.{key}"] = value
                else:
                    rag_client_filters[key] = value # Assume already correctly prefixed

        results = await self.bookshelf_client.query_bookshelf( # now async
            query_text=query_text,
            top_k=top_k,
            filter_conditions=rag_client_filters
        )

        logger.info(f"Bookshelf query for user '{user_id}' returned {len(results)} results from client.")
        return results

    async def list_documents_on_bookshelf(self, user_id: str, limit: int = 100) -> List[BookshelfDocumentIndex]:
        logger.info(f"Listing documents on bookshelf for user '{user_id}'.")
        index_memories = await self.memory_storage.get_entries_by_type_and_user(
            entry_type="bookshelf_document_index",
            user_id=user_id,
            limit=limit
        )

        documents: List[BookshelfDocumentIndex] = [] # Ensure type
        for mem_entry in index_memories:
            try:
                content_data = json.loads(mem_entry.get("content", "{}"))
                # Basic validation for expected structure
                if isinstance(content_data, dict) and 'doc_id' in content_data and 'title' in content_data and 'user_id' in content_data:
                    documents.append(content_data) # type: ignore # Assume it matches BookshelfDocumentIndex
            except json.JSONDecodeError:
                logger.warning(f"Could not parse bookshelf_document_index content for memory ID {mem_entry.get('id')}")

        logger.info(f"Found {len(documents)} documents on bookshelf for user '{user_id}'.")
        return documents

    async def get_document_raw_text(self, user_id: str, doc_id: str) -> Optional[str]:
        logger.info(f"Attempting to retrieve raw text for document ID '{doc_id}' for user '{user_id}'.")

        index_entry_mem_id = f"bs_idx_{doc_id}"
        index_entry = self.memory_storage.get_entry(index_entry_mem_id)
        if not index_entry or index_entry.get("metadata", {}).get("user_id") != user_id:
            logger.warning(f"User '{user_id}' does not have access to document ID '{doc_id}' or index not found.")
            return None

        # Retrieve all chunks from the RAG client, now requires user_id
        chunks_data: List[DocumentChunkInfo] = await self.bookshelf_client.get_document_chunks(doc_id=doc_id, user_id=user_id) # now async, pass user_id
        if not chunks_data:
            logger.warning(f"No chunks found for document ID '{doc_id}' in RAG client for this user.")
            return None

        # DocumentChunkInfo from client currently has 'text_preview'.
        # This handler method aims to return full raw text.
        # This highlights a potential mismatch or need for client to provide full text in get_document_chunks.
        # For now, we join what the client gives (previews). This is a known issue.
        full_text_parts = [chunk.get("text_preview", "") for chunk in chunks_data]
        full_text = "".join(full_text_parts)

        logger.info(f"Retrieved and reassembled text (potentially from previews) for document ID '{doc_id}'. Length: {len(full_text)}")
        if "... " in full_text and len(chunks_data) > 0 : # Basic check if previews were likely joined
             logger.warning(f"Reassembled text for doc {doc_id} is based on previews from the client. Full text reconstruction might be lossy.")
        return full_text

    async def remove_document_from_bookshelf(self, user_id: str, doc_id: str) -> bool:
        logger.info(f"Attempting to remove document ID '{doc_id}' from bookshelf for user '{user_id}'.")

        index_entry_mem_id = f"bs_idx_{doc_id}"
        index_entry = self.memory_storage.get_entry(index_entry_mem_id)

        if not index_entry or index_entry.get("metadata", {}).get("user_id") != user_id:
            logger.warning(f"User '{user_id}' cannot remove document ID '{doc_id}': not owner or index not found.")
            return False

        # Delete chunks from RAG client, now requires user_id
        delete_success_rag = await self.bookshelf_client.delete_document_chunks(doc_id=doc_id, user_id=user_id) # now async, pass user_id
        if not delete_success_rag:
            logger.warning(f"Failed to delete document chunks from RAG client for doc_id '{doc_id}'. Aborting full removal.")
            return False

        delete_success_index = self.memory_storage.delete_entry(index_entry_mem_id)
        if not delete_success_index:
            logger.warning(f"RAG chunks deleted for doc_id '{doc_id}', but failed to delete its index entry '{index_entry_mem_id}' from MemoryStorage.")
            return False

        logger.info(f"Successfully removed document ID '{doc_id}' (and its index) from bookshelf for user '{user_id}'.")
        return True

# Example Usage (Conceptual)
if __name__ == '__main__':
    import asyncio
    # Assuming Config is accessible for test setup
    # from eidos_agent.core.config import Config

    # Dummy Config for MemoryStorage and BookshelfClient
    class MockConfigForHandler: # Renamed to avoid conflict with main Config
        def get_ethos_config(self): # For MemoryStorage
            return {"memory_db_path": ":memory:"} # In-memory SQLite for test

        def get_bookshelf_config(self): # For RagbitsBookshelfClient
            return { # This is a BookshelfConfig TypedDict
                "qdrant_host": "localhost", "qdrant_port": 6333,
                "qdrant_collection_name": "handler_test_bs_main", # Unique name
                "embedding_model_name": "test-embedder-handler-main",
                "embedding_dimension": 384, "chunk_size": 150, "chunk_overlap": 20,
                "qdrant_api_key": None # Explicitly None if not used
            }

    mock_config_instance = MockConfigForHandler() # Renamed
    # We need to pass the actual config dictionary to MemoryStorage and RagbitsBookshelfClient
    memory_storage_instance = MemoryStorage(config=mock_config_instance) # type: ignore
    bookshelf_client_instance = RagbitsBookshelfClient(config=mock_config_instance.get_bookshelf_config())

    handler = BookshelfHandler(bookshelf_client_instance, memory_storage_instance)
    test_user_id = "user_handler_test_main_123" # Unique user id

    async def run_handler_tests(): # Ensure main test runner is async
        print("--- Testing BookshelfHandler ---")

        # Test adding a document via direct content
        print("\n1. Adding document via direct content...")
        doc_content = "This is the full text of the first test document. It contains several sentences to ensure chunking can occur. The topic is primarily about testing the bookshelf handler with direct content provision."
        added_doc_1_info = await handler.add_document_to_bookshelf( # await
            user_id=test_user_id,
            file_path_or_url="test_doc_1.txt",
            document_content=doc_content,
            document_title="My First Test Document",
            source_metadata={"category": "testing", "version": "1.0"}
        )
        doc1_id_val = None
        if added_doc_1_info and "doc_id" in added_doc_1_info and "error" not in added_doc_1_info : # Check for error key
            print(f"Added document 1 successfully: {added_doc_1_info}")
            doc1_id_val = added_doc_1_info["doc_id"]

            print("\n2. Listing documents...")
            docs_list = await handler.list_documents_on_bookshelf(test_user_id) # await
            print(f"Found {len(docs_list)} documents:")
            for doc_idx_data in docs_list: print(f"  - {doc_idx_data.get('title')} (ID: {doc_idx_data.get('doc_id')}), Chunks: {doc_idx_data.get('chunk_count')}")

            print("\n3. Querying for 'direct content provision'...")
            # Pass example query_filters to test the new parameter
            query_results = await handler.query_bookshelf(test_user_id, "direct content provision", top_k=2, query_filters={"category": "testing"}) # await
            print(f"Query found {len(query_results)} results:")
            for res in query_results: print(f"  - Chunk: {res.get('chunk_id')}, Doc: {res.get('document_id')}, Score: {res.get('score',0):.2f}, Text: '{res.get('text', '')[:60]}...'")

            print(f"\n4. Getting raw text for document ID: {doc1_id_val}...")
            raw_text = await handler.get_document_raw_text(test_user_id, doc1_id_val) # await
            if raw_text: print(f"  Retrieved raw text (first 100 chars): '{raw_text[:100]}...' (Note: may be from previews)")
            else: print(f"  Failed to retrieve raw text for {doc1_id_val}")

        else:
            print(f"Failed to add document 1. Info: {added_doc_1_info}")

        print("\n5. Adding document via URL (placeholder)...")
        added_doc_2_info = await handler.add_document_to_bookshelf( # await
            user_id=test_user_id,
            file_path_or_url="http://example.com/testpage_for_handler",
            is_url=True,
            source_metadata={"source_type": "web_test"}
        )
        doc2_id_val = None
        if added_doc_2_info and "doc_id" in added_doc_2_info and "error" not in added_doc_2_info: # Check for error key
             print(f"Added document 2 (URL) successfully: {added_doc_2_info}")
             doc2_id_val = added_doc_2_info["doc_id"]
        else:
            print(f"Failed to add document from URL. Info: {added_doc_2_info}")

        if doc1_id_val: # Test removal if doc1 was added
            print(f"\n6. Removing document ID: {doc1_id_val}...")
            remove_success = await handler.remove_document_from_bookshelf(test_user_id, doc1_id_val) # await
            print(f"  Removal successful: {remove_success}")

            docs_list_after_remove = await handler.list_documents_on_bookshelf(test_user_id) # await
            print(f"Documents after removal of doc1: {len(docs_list_after_remove)}")
            for doc_idx_data in docs_list_after_remove: print(f"  - Title: {doc_idx_data.get('title')}")

        if doc2_id_val: # Cleanup doc2 if it was added
            print(f"\n7. Removing document ID: {doc2_id_val} (URL doc)...")
            remove_success_doc2 = await handler.remove_document_from_bookshelf(test_user_id, doc2_id_val) # await
            print(f"  Removal of URL doc successful: {remove_success_doc2}")


    asyncio.run(run_handler_tests()) # Use asyncio.run

    # Close client and memory storage - these are synchronous close methods in this example setup
    # If they were async, they'd need to be awaited, perhaps in an outer async main or similar.
    # The RagbitsBookshelfClient.close() is async.
    async def close_resources():
        await bookshelf_client_instance.close()
    asyncio.run(close_resources()) # Separate run for async close

    memory_storage_instance.close_connection()
