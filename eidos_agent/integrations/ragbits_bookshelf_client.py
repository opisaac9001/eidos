from typing import Optional, List, Dict, Any, TypedDict, Union
from uuid import uuid4, UUID # Add UUID

# Ragbits imports
from ragbits.core.embeddings.litellm import LiteLLMEmbedder
from ragbits.core.vector_stores.qdrant import QdrantVectorStore
from ragbits.core.vector_stores.base import VectorStoreEntry, VectorStoreOptions, VectorStoreResult # For creating entries and querying
# from ragbits.document_search.ingestion.parsers.text import TextParser # Deferred
# from ragbits.document_search.ingestion.chunkers import ChunkOptions # Deferred

# Qdrant client imports
from qdrant_client import AsyncQdrantClient # models are used by QdrantVectorStore internally

from eidos_agent.core.config import BookshelfConfig
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentChunkInfo(TypedDict): # Renamed and updated
    chunk_id: str
    document_id: str
    chunk_index: int
    text_preview: str
    metadata: Dict[str, Any]

class RagbitsBookshelfClient:
    def __init__(self, config: BookshelfConfig):
        self.config = config
        self.embedder_name = config.get("embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
        # embedding_dimension from config is used by QdrantVectorStore's internal collection creation logic
        # if it needs to create the collection, it will use embedder.get_vector_size().
        self.collection_name = config.get("qdrant_collection_name", "eidos_bookshelf")

        logger.info(f"Initializing RagbitsBookshelfClient with embedder: {self.embedder_name}, Qdrant: {config.get('qdrant_host')}:{config.get('qdrant_port')}, Collection: {self.collection_name}")

        self.embedder = LiteLLMEmbedder(model_name=self.embedder_name)

        self.qdrant_http_client = AsyncQdrantClient(
            host=config.get("qdrant_host", "localhost"),
            port=config.get("qdrant_port", 6333),
            api_key=config.get("qdrant_api_key")
        )

        self.qdrant_vector_store = QdrantVectorStore(
            client=self.qdrant_http_client,
            index_name=self.collection_name,
            embedder=self.embedder
            # QdrantVectorStore will use its embedder's get_vector_size() and default Distance.COSINE
            # when creating the collection if it doesn't exist.
        )

        logger.info("RagbitsBookshelfClient initialized with actual ragbits components.")

    # _ensure_collection_exists method is removed.
    # QdrantVectorStore's .store() method handles collection creation.

    async def add_document(
        self,
        doc_id: str, # This is the custom ID for the whole document
        content: str,
        user_id: str, # User ID for ownership/filtering
        other_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunkInfo]: # Return a list of dicts representing processed chunks for confirmation
        logger.info(f"Processing document ID '{doc_id}' for user '{user_id}' for bookshelf.")
        if not content.strip():
            logger.warning(f"Document '{doc_id}' has no content. Skipping.")
            return []

        # Simplified chunking logic (TextParser usage deferred)
        _chunk_size = self.config.get("chunk_size", 512)
        _chunk_overlap = self.config.get("chunk_overlap", 50)
        text_chunks: List[str] = []
        start = 0
        while start < len(content):
            end = start + _chunk_size
            text_chunks.append(content[start:end])
            if end >= len(content):
                break
            start += _chunk_size - _chunk_overlap
            if start >= len(content): break # Avoid infinite loop

        if not text_chunks:
            logger.warning(f"Text chunking produced no chunks for document '{doc_id}'.")
            return []

        logger.info(f"Document '{doc_id}' split into {len(text_chunks)} chunks.")

        vector_store_entries: List[VectorStoreEntry] = []
        processed_chunk_confirmations: List[DocumentChunkInfo] = []

        base_doc_metadata = other_metadata.copy() if other_metadata else {}
        base_doc_metadata["original_document_id"] = doc_id
        base_doc_metadata["user_id"] = user_id

        for i, chunk_text in enumerate(text_chunks):
            chunk_entry_id = uuid4() # Generate UUID for each chunk/entry

            chunk_specific_metadata = base_doc_metadata.copy()
            chunk_specific_metadata["chunk_index"] = i
            chunk_specific_metadata["chunk_id"] = str(chunk_entry_id)

            entry = VectorStoreEntry(
                id=chunk_entry_id,
                text=chunk_text,
                metadata=chunk_specific_metadata
            )
            vector_store_entries.append(entry)
            processed_chunk_confirmations.append(DocumentChunkInfo(
                chunk_id=str(chunk_entry_id),
                document_id=doc_id,
                chunk_index=i,
                text_preview=chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text,
                metadata=chunk_specific_metadata
            ))

        if vector_store_entries:
            try:
                await self.qdrant_vector_store.store(entries=vector_store_entries)
                logger.info(f"Successfully stored {len(vector_store_entries)} chunks for document ID '{doc_id}' in Qdrant.")
            except Exception as e:
                logger.error(f"Failed to store chunks for document ID '{doc_id}' in Qdrant: {e}", exc_info=True)
                return []

        return processed_chunk_confirmations

    # Methods to be refactored in subsequent steps:
    # query_bookshelf, delete_document_chunks, get_document_chunks

    async def query_bookshelf(
        self,
        query_text: str,
        top_k: int = 5,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]: # Returns list of dicts, matching DocumentChunkInfo but with score
        logger.info(f"Querying bookshelf with text: '{query_text[:50]}...', top_k: {top_k}, filters: {filter_conditions}")
        if not query_text.strip():
            return []

        # filter_conditions should have keys like "metadata.user_id", "metadata.original_document_id" etc.
        # as QdrantVectorStore._create_qdrant_filter expects this format for nested metadata fields.
        vs_options = VectorStoreOptions(k=top_k, where=filter_conditions if filter_conditions else None)

        try:
            search_results: List[VectorStoreResult] = await self.qdrant_vector_store.retrieve(
                text=query_text,
                options=vs_options
            )
        except Exception as e:
            logger.error(f"Error querying bookshelf via QdrantVectorStore: {e}", exc_info=True)
            return []

        formatted_results: List[Dict[str, Any]] = []
        for result_item in search_results:
            entry = result_item.entry # This is a VectorStoreEntry
            stored_metadata = entry.metadata if entry.metadata else {}

            formatted_results.append({
                "chunk_id": str(entry.id),
                "document_id": stored_metadata.get("original_document_id"),
                "text": entry.text,
                "score": result_item.score,
                "metadata": stored_metadata
            })

        logger.info(f"Bookshelf query returned {len(formatted_results)} results from QdrantVectorStore.")
        return formatted_results

    # Methods to be refactored in subsequent steps:
    # delete_document_chunks, get_document_chunks

    async def delete_document_chunks(self, doc_id: str, user_id: str) -> bool:
        logger.info(f"Attempting to delete all chunks for document ID '{doc_id}' (user: '{user_id}') from bookshelf.")

        # Construct the 'where' filter for listing chunks.
        # Metadata keys should match what was stored in add_document.
        where_filter = {
            "metadata.original_document_id": doc_id,
            "metadata.user_id": user_id  # Ensure user-specific deletion
        }

        try:
            logger.debug(f"Listing chunks for doc_id '{doc_id}', user_id '{user_id}' with filter: {where_filter}")
            # The .list() method in ragbits QdrantVectorStore returns List[VectorStoreEntry]
            # Setting limit=None should fetch all matching entries based on QdrantVectorStore implementation.
            entries_to_delete: List[VectorStoreEntry] = await self.qdrant_vector_store.list(
                where=where_filter,
                limit=None
            )

            if not entries_to_delete:
                logger.info(f"No chunks found for document ID '{doc_id}' and user '{user_id}' to delete.")
                return True # Document effectively not there for this user, or already deleted.

            ids_to_delete: List[UUID] = [entry.id for entry in entries_to_delete if entry.id]

            if not ids_to_delete:
                logger.warning(f"Found entries for doc_id '{doc_id}' but could not extract valid UUIDs for deletion.")
                return False # Should ideally not happen if entries_to_delete was populated and entries have IDs

            logger.debug(f"Found {len(ids_to_delete)} chunk UUIDs to delete for doc_id '{doc_id}'.")

            await self.qdrant_vector_store.remove(ids=ids_to_delete)
            logger.info(f"Successfully submitted deletion for {len(ids_to_delete)} chunks for document ID '{doc_id}'.")
            return True

        except Exception as e:
            logger.error(f"Error deleting chunks for document ID '{doc_id}': {e}", exc_info=True)
            return False

    # Method to be refactored next:
    # get_document_chunks

    async def get_document_chunks(self, doc_id: str, user_id: str) -> List[DocumentChunkInfo]:
        """Retrieves all chunks and their metadata associated with a given document ID and user ID."""
        logger.info(f"Retrieving all chunks for document ID '{doc_id}' for user '{user_id}'.")

        where_filter = {
            "metadata.original_document_id": doc_id,
            "metadata.user_id": user_id
        }

        retrieved_chunks: List[DocumentChunkInfo] = []

        try:
            # Using limit=None to attempt to fetch all matching entries.
            entries: List[VectorStoreEntry] = await self.qdrant_vector_store.list(
                where=where_filter,
                limit=None
            )

            if not entries:
                logger.info(f"No chunks found for document ID '{doc_id}' and user '{user_id}'.")
                return []

            for entry in entries:
                stored_metadata = entry.metadata if entry.metadata else {}
                # Ensure entry.text is not None before slicing
                text_content = entry.text if entry.text else ""
                retrieved_chunks.append(DocumentChunkInfo(
                    chunk_id=str(entry.id),
                    document_id=stored_metadata.get("original_document_id", doc_id), # Fallback to input doc_id
                    chunk_index=stored_metadata.get("chunk_index", -1), # Fallback for index
                    text_preview=text_content[:200] + "..." if len(text_content) > 200 else text_content,
                    metadata=stored_metadata
                ))

            # Sort by chunk_index to ensure original order
            retrieved_chunks.sort(key=lambda x: x.get("chunk_index", 0))

            logger.info(f"Retrieved {len(retrieved_chunks)} chunks for document ID '{doc_id}'.")
            return retrieved_chunks

        except Exception as e:
            logger.error(f"Error retrieving chunks for document ID '{doc_id}': {e}", exc_info=True)
            return []

    async def close(self): # Add a close method for the qdrant client
        if self.qdrant_http_client:
            await self.qdrant_http_client.close()
            logger.info("Qdrant client closed in RagbitsBookshelfClient.")

# Example Usage (Conceptual) - This will likely break until other methods are refactored
if __name__ == '__main__':
    # Create a dummy BookshelfConfig for testing
    dummy_bs_config_main: BookshelfConfig = {
        "qdrant_host": "localhost", "qdrant_port": 6333,
        "qdrant_collection_name": "test_bookshelf_main_actual_ragbits",
        "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2", # A real model for LiteLLM
        "embedding_dimension": 384, "chunk_size": 100, "chunk_overlap": 10,
        "qdrant_api_key": None
    }

    # This example requires a running Qdrant instance for LiteLLMEmbedder and QdrantVectorStore to fully work.
    # For unit testing without live services, these would need to be mocked.
    # client_main = RagbitsBookshelfClient(config=dummy_bs_config_main)

    # print("Conceptual example - full functionality requires method refactoring and live services/mocks.")
    # # Example calls would go here, but are expected to fail or log warnings until methods are refactored.

    # # Example of how close would be called in an async context
    # # async def main_example():
    # #     client = RagbitsBookshelfClient(config=dummy_bs_config_main)
    # #     # ... operations ...
    # #     await client.close()
    # # import asyncio
    # # asyncio.run(main_example())
    logger.info("RagbitsBookshelfClient __main__ block: Methods like add_document, query_bookshelf need refactoring to work with new components.")
    logger.info("This example will not run full operations until subsequent refactoring steps.")
