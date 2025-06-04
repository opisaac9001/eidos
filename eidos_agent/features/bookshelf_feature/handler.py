import logging
from typing import List, Dict, Optional, Any

from eidos_agent.core.config import Config
from eidos_agent.integrations.ragbits_bookshelf_client import RagbitsBookshelfClient

logger = logging.getLogger(__name__)

class BookshelfHandler:
    """
    Handles operations related to the Eidos Bookshelf, primarily document ingestion.
    """

    def __init__(self):
        """
        Initializes the BookshelfHandler.
        """
        self.bookshelf_client: Optional[RagbitsBookshelfClient] = None
        bookshelf_config = Config.get_bookshelf_config()

        if bookshelf_config:
            try:
                self.bookshelf_client = RagbitsBookshelfClient(
                    qdrant_host=bookshelf_config["qdrant_host"],
                    qdrant_port=bookshelf_config["qdrant_port"],
                    qdrant_api_key=bookshelf_config.get("qdrant_api_key"), # Optional
                    qdrant_collection_name=bookshelf_config["qdrant_collection_name"],
                    embedding_model_name=bookshelf_config["embedding_model_name"],
                    embedding_vector_size=bookshelf_config["embedding_dimension"],
                    # chunk_size and chunk_overlap can be added if made configurable in BookshelfConfig
                )
                logger.info("BookshelfHandler initialized successfully with RagbitsBookshelfClient.")
            except Exception as e:
                logger.error(f"Failed to initialize RagbitsBookshelfClient in BookshelfHandler: {e}", exc_info=True)
                # self.bookshelf_client will remain None, methods should handle this
        else:
            logger.warning("Bookshelf feature configuration not found. BookshelfHandler will not be operational.")

    def add_document_to_bookshelf(
        self,
        document_content: str,
        document_name: str,
        document_source: str,
        topics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Adds a new document to the Eidos Bookshelf.

        Args:
            document_content: The full text content of the document.
            document_name: A unique name or ID for the document.
            document_source: The origin of the document (e.g., filename, URL).
            topics: Optional list of topics associated with the document.

        Returns:
            A dictionary indicating the result of the operation.
        """
        if not self.bookshelf_client:
            logger.error("Bookshelf client not initialized. Cannot add document.")
            return {"status": "error", "message": "Bookshelf client is not configured or failed to initialize."}

        if not document_name or not document_name.strip():
            return {"status": "error", "message": "Document name cannot be empty."}
        if not document_content or not document_content.strip():
            return {"status": "error", "message": "Document content cannot be empty."}
        if not document_source or not document_source.strip():
            # Default source if not provided, or make it mandatory
            logger.warning(f"Document source for '{document_name}' is empty. Using 'unknown_source'.")
            document_source = "unknown_source"


        try:
            logger.info(f"Attempting to add document '{document_name}' from source '{document_source}' to bookshelf.")
            self.bookshelf_client.add_document(
                document_content=document_content,
                document_name=document_name,
                document_source=document_source,
                topics=topics
            )
            logger.info(f"Successfully processed add_document for '{document_name}'.")
            return {"status": "success", "message": f"Document '{document_name}' added to bookshelf."}
        except Exception as e:
            logger.error(f"Error adding document '{document_name}' to bookshelf: {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to add document '{document_name}': {str(e)}"}

    def query_bookshelf(
        self,
        query_text: str,
        document_name: Optional[str] = None,
        topics_filter: Optional[List[str]] = None, # Keep topics_filter from previous version
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Queries documents in the Eidos Bookshelf and provides a simple synthesized context.
        """
        if not self.bookshelf_client:
            logger.error("Bookshelf client not initialized. Cannot query bookshelf.")
            return {"status": "error", "message": "Bookshelf client is not configured or failed to initialize."}

        try:
            logger.info(f"Querying bookshelf for: '{query_text[:100]}...' (top_k={top_k}, doc_filter='{document_name}', topic_filter='{topics_filter}')")
            retrieved_chunks = self.bookshelf_client.query_documents(
                query_text=query_text,
                document_name=document_name,
                topics_filter=topics_filter, # Pass topics_filter to client
                top_k=top_k
            )

            if not retrieved_chunks:
                logger.info(f"No relevant information found on bookshelf for query: '{query_text[:100]}...'")
                return {"status": "success", "query": query_text, "retrieved_context": "No relevant information found on the bookshelf.", "source_documents": []}

            concatenated_text = "\n\n---\n\n".join(
                chunk.get("text_content", "") for chunk in retrieved_chunks if chunk.get("text_content")
            )

            source_document_names = sorted(list(set(
                chunk.get("metadata", {}).get("document_name") for chunk in retrieved_chunks if chunk.get("metadata", {}).get("document_name")
            )))

            logger.info(f"Retrieved {len(retrieved_chunks)} chunks from {len(source_document_names)} documents for query: '{query_text[:100]}...'")
            return {
                "status": "success",
                "query": query_text,
                "retrieved_context": concatenated_text,
                "source_documents": source_document_names,
                "raw_chunks": retrieved_chunks # Optionally include raw chunks for more detailed use
            }
        except Exception as e:
            logger.error(f"Error querying bookshelf with text '{query_text[:50]}...': {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to query bookshelf: {str(e)}"}

    def list_documents_on_bookshelf(self) -> Dict[str, Any]:
        """
        Lists all unique document names available on the bookshelf.
        """
        if not self.bookshelf_client:
            logger.error("Bookshelf client not initialized. Cannot list documents.")
            return {"status": "error", "message": "Bookshelf client is not configured or failed to initialize."}

        try:
            document_names = self.bookshelf_client.list_all_document_names()
            logger.info(f"Successfully listed {len(document_names)} documents from bookshelf.")
            return {"status": "success", "documents": document_names}
        except Exception as e:
            logger.error(f"Error listing documents from bookshelf: {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to list documents: {str(e)}"}

    def get_document_raw_text(self, document_name: str) -> Dict[str, Any]:
        """
        Retrieves and concatenates all text chunks for a specific document.
        """
        if not self.bookshelf_client:
            logger.error("Bookshelf client not initialized. Cannot get document text.")
            return {"status": "error", "message": "Bookshelf client is not configured or failed to initialize."}

        if not document_name or not document_name.strip():
            return {"status": "error", "message": "Document name cannot be empty."}

        try:
            logger.info(f"Retrieving raw text for document: '{document_name}'")
            chunks = self.bookshelf_client.get_document_chunks(document_name)

            if not chunks:
                logger.warning(f"Document '{document_name}' not found or has no content on bookshelf.")
                return {"status": "error", "message": f"Document '{document_name}' not found or has no content."}

            # Assuming chunks are already sorted by chunk_index by the client, or sort here if necessary.
            # If not sorted, and order matters: chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))
            concatenated_text = "".join(chunk.get("text_content", "") for chunk in chunks) # Simple concatenation

            logger.info(f"Successfully retrieved and concatenated {len(chunks)} chunks for document '{document_name}'.")
            return {
                "status": "success",
                "document_name": document_name,
                "raw_text": concatenated_text,
                "num_chunks": len(chunks)
            }
        except Exception as e:
            logger.error(f"Error retrieving raw text for document '{document_name}': {e}", exc_info=True)
            return {"status": "error", "message": f"Failed to retrieve raw text for '{document_name}': {str(e)}"}

    def remove_document_from_bookshelf(self, document_name: str) -> Dict[str, Any]:
        """
        Removes a document and all its associated chunks from the bookshelf.
        """
        if not self.bookshelf_client:
            logger.error("Bookshelf client not initialized. Cannot remove document.")
            return {"status": "error", "message": "Bookshelf client is not configured or failed to initialize."}

        if not document_name or not document_name.strip():
            return {"status": "error", "message": "Document name cannot be empty."}

        try:
            logger.info(f"Attempting to remove document '{document_name}' from bookshelf.")
            deletion_successful = self.bookshelf_client.delete_document(document_name)

            if deletion_successful:
                logger.info(f"Document '{document_name}' successfully removed from bookshelf (or was not found).")
                return {"status": "success", "message": f"Document '{document_name}' removed from bookshelf (or was not found)."}
            else:
                # This case implies the client's delete_document method returned False, indicating a specific failure
                # condition reported by the client (e.g., Qdrant operation status not COMPLETED/ACKNOWLEDGED).
                logger.warning(f"Bookshelf client reported failure to remove document '{document_name}'.")
                return {"status": "error", "message": f"Failed to remove document '{document_name}' from bookshelf."}
        except Exception as e:
            # This case handles unexpected errors during the client call itself (e.g., network issue, client internal error).
            logger.error(f"Exception occurred while trying to remove document '{document_name}': {e}", exc_info=True)
            return {"status": "error", "message": f"An unexpected error occurred while removing document '{document_name}': {str(e)}"}


# Example of how this handler might be used (conceptual)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # --- Setup (Requires .env file or environment variables for QDRANT_HOST etc.) ---
    # Ensure your .env file has:
    # QDRANT_HOST=localhost
    # QDRANT_PORT=6333
    # QDRANT_COLLECTION_NAME=eidos_bookshelf_handler_test
    # BOOKSHELF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
    # BOOKSHELF_EMBEDDING_DIMENSION=384

    # For testing, explicitly set env vars if .env is not convenient for this test script
    import os
    os.environ.setdefault("QDRANT_HOST", "localhost")
    os.environ.setdefault("QDRANT_PORT", "6333")
    os.environ.setdefault("QDRANT_COLLECTION_NAME", "eidos_bookshelf_handler_test")
    os.environ.setdefault("BOOKSHELF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    os.environ.setdefault("BOOKSHELF_EMBEDDING_DIMENSION", "384")

    # Reload Config to pick up any env vars set specifically for this test
    # This is tricky because Config is usually module-level. For a real test,
    # you'd structure it to allow config override or use a dedicated test config.
    # For this __main__ block, we assume the initial Config load might pick them up if set before Config class is fully processed.
    # A better way is to have Config load on demand or be re-initializable for tests.

    logger.info("Attempting to initialize BookshelfHandler for testing...")
    # This will print warnings if QDRANT_HOST is not found by the Config module.
    # The Config class reads .env at import time.

    bookshelf_handler = BookshelfHandler()

    if not bookshelf_handler.bookshelf_client:
        logger.error("Bookshelf client could not be initialized. Test cannot proceed.")
        logger.error("Please ensure QDRANT_HOST and other bookshelf variables are set in your .env file or environment.")
    else:
        logger.info("BookshelfHandler initialized for testing.")

        # Test adding a document
        doc_name = "My Test Document"
        doc_content = "This is the content of my test document. It talks about AI, machine learning, and large language models." * 10
        doc_source = "local_test_script"
        doc_topics = ["ai", "testing"]

        add_result = bookshelf_handler.add_document_to_bookshelf(
            document_content=doc_content,
            document_name=doc_name,
            document_source=doc_source,
            topics=doc_topics
        )
        logger.info(f"Add document result: {add_result}")
        assert add_result["status"] == "success"

        # Test adding another document
        add_result_2 = bookshelf_handler.add_document_to_bookshelf(
            document_content="A brief note on the color of the sky: It is often blue during the day.",
            document_name="SkyColorNote",
            document_source="observations",
            topics=["nature", "sky"]
        )
        logger.info(f"Add document 2 result: {add_result_2}")
        assert add_result_2["status"] == "success"

        # Test querying
        logger.info("\nTesting query_bookshelf...")
        query1 = "What are large language models?"
        query_result1 = bookshelf_handler.query_bookshelf(query_text=query1, top_k=2)
        logger.info(f"Query 1 ('{query1}') result: {query_result1}")
        if query_result1["status"] == "success" and query_result1.get("retrieved_context") != "No relevant information found on the bookshelf.":
            assert "language models" in query_result1['retrieved_context'].lower()
            logger.info(f"Retrieved context for Query 1: {query_result1['retrieved_context'][:200]}...")
            assert "doc_alpha" in query_result1["source_documents"]

        query2 = "Information about the sky"
        query_result2 = bookshelf_handler.query_bookshelf(query_text=query2, document_name="SkyColorNote")
        logger.info(f"Query 2 ('{query2}' in 'SkyColorNote') result: {query_result2}")
        if query_result2["status"] == "success" and query_result2.get("retrieved_context") != "No relevant information found on the bookshelf.":
            assert "sky" in query_result2['retrieved_context'].lower()
            assert "SkyColorNote" in query_result2["source_documents"]

        query3 = "AI and testing" # General query that might hit topics
        query_result3 = bookshelf_handler.query_bookshelf(query_text=query3, topics_filter=["testing"], top_k=1)
        logger.info(f"Query 3 ('{query3}' with topic 'testing') result: {query_result3}")
        if query_result3["status"] == "success" and query_result3.get("retrieved_context") != "No relevant information found on the bookshelf.":
             # Check if any of the raw chunks' metadata contains the topic "testing"
             found_topic_in_chunks = False
             for chunk in query_result3.get("raw_chunks", []):
                 if "testing" in chunk.get("metadata", {}).get("topics", []):
                     found_topic_in_chunks = True
                     break
             assert found_topic_in_chunks

        # Test listing documents
        logger.info("\nTesting list_documents_on_bookshelf...")
        list_result = bookshelf_handler.list_documents_on_bookshelf()
        logger.info(f"List documents result: {list_result}")
        assert list_result["status"] == "success"
        assert doc_name in list_result["documents"]
        assert "SkyColorNote" in list_result["documents"]

        # Test getting raw text
        logger.info(f"\nTesting get_document_raw_text for '{doc_name}'...")
        raw_text_result = bookshelf_handler.get_document_raw_text(doc_name)
        logger.info(f"Get raw text result for '{doc_name}' (first 100 chars): {raw_text_result.get('raw_text', '')[:100]}...")
        assert raw_text_result["status"] == "success"
        assert doc_content == raw_text_result.get("raw_text") # Check if concatenated content matches original

        logger.info(f"\nTesting get_document_raw_text for non_existent_doc...")
        raw_text_not_found_result = bookshelf_handler.get_document_raw_text("non_existent_doc")
        logger.info(f"Get raw text not_found result: {raw_text_not_found_result}")
        assert raw_text_not_found_result["status"] == "error"
        assert "not found" in raw_text_not_found_result["message"]


        # Clean up (optional, but good for tests)
        # Requires RagbitsBookshelfClient to be accessible and have a delete method
        # and for the collection name to be consistent.
        if bookshelf_handler.bookshelf_client:
            logger.info(f"\nAttempting to remove test document '{doc_name}' using handler...")
            remove_result = bookshelf_handler.remove_document_from_bookshelf(doc_name)
            logger.info(f"Remove document result for '{doc_name}': {remove_result}")
            assert remove_result["status"] == "success"

            # Verify it's gone by trying to list or get it
            list_after_delete = bookshelf_handler.list_documents_on_bookshelf()
            assert doc_name not in list_after_delete.get("documents", [])
            logger.info(f"Documents after deleting '{doc_name}': {list_after_delete.get('documents')}")

            # Clean up the other document
            logger.info(f"Attempting to remove test document 'SkyColorNote' using handler...")
            remove_result_sky = bookshelf_handler.remove_document_from_bookshelf("SkyColorNote")
            logger.info(f"Remove document result for 'SkyColorNote': {remove_result_sky}")
            assert remove_result_sky["status"] == "success"

            # Optionally, delete the entire test collection if it was specific to this test
            # This is dangerous if the collection name is not unique for tests.
            # It's better done directly via the client if needed for true test isolation.
             # bookshelf_handler.bookshelf_client.qdrant_client.delete_collection(
             #     collection_name=bookshelf_handler.bookshelf_client.qdrant_collection_name
             # )
             # logger.info(f"Deleted test collection: {bookshelf_handler.bookshelf_client.qdrant_collection_name}")

        logger.info("\nBookshelfHandler conceptual test finished.")
        logger.info("NOTE: Full functionality of this test requires a running Qdrant instance and appropriate .env configuration.")
        logger.info("The dummy Ragbits components are used, so actual embedding and Qdrant interaction might differ with real components.")

```
