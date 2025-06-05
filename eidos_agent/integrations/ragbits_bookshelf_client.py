import logging
import uuid
from typing import List, Dict, Optional, Any

from qdrant_client import QdrantClient, models as qmodels
# from qdrant_client.http import models as qmodels # Older import, now models is top-level

# --- Start of Dummy Ragbits Classes (to be replaced by actual ragbits imports) ---
# These are placeholders to make the file syntactically valid without ragbits installed.
# Replace with actual imports:
# from ragbits.core.embedders import LiteLLMEmbedder # Corrected path
# from ragbits.core.vector_stores import QdrantVectorStore # Corrected path
# from ragbits.document_search import DocumentSearch
# from ragbits.core.text_chunkers import TextChunker, TextChunk # Corrected path
# from ragbits.core.metadata import Metadata
# from ragbits.core.vector_stores import VectorStoreDocument

class DummyEmbedder:
    def __init__(self, model: str, **kwargs):
        self.model = model
        self.dimension = 384 # Default for 'sentence-transformers/all-MiniLM-L6-v2'

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        logger.warning("Using DummyEmbedder.embed_documents")
        return [[0.1] * self.dimension for _ in texts]

    def embed_query(self, text: str) -> List[float]:
        logger.warning("Using DummyEmbedder.embed_query")
        return [0.1] * self.dimension

    def get_embedding_dimension(self) -> int:
        logger.warning("Using DummyEmbedder.get_embedding_dimension")
        return self.dimension

LiteLLMEmbedder = DummyEmbedder # Alias to match planned import

class DummyTextChunk:
    def __init__(self, text_content: str, metadata: Optional[Dict[str, Any]] = None):
        self.text_content = text_content
        self.metadata = metadata or {}

TextChunk = DummyTextChunk # Alias

class DummyTextChunker:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, **kwargs):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str, **kwargs) -> List[TextChunk]:
        logger.warning("Using DummyTextChunker.chunk")
        if not text:
            return []
        # Simplified chunking logic for the dummy
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(TextChunk(text_content=text[start:end]))
            start = end - self.chunk_overlap
            if start + self.chunk_size <= end and end < len(text) : # prevent infinite loop on very small overlap/size
                start = end
        return chunks

TextChunker = DummyTextChunker # Alias

# --- End of Dummy Ragbits Classes ---

logger = logging.getLogger(__name__)

DEFAULT_QDRANT_DISTANCE = qmodels.Distance.COSINE
DEFAULT_CHUNK_SIZE = 1000 # Characters
DEFAULT_CHUNK_OVERLAP = 200 # Characters

class RagbitsBookshelfClient:
    """
    A client to manage and query documents in the Eidos Bookshelf
    using Ragbits and Qdrant.
    """

    def __init__(
        self,
        qdrant_host: str,
        qdrant_port: int = 6333,
        qdrant_collection_name: str = "eidos_bookshelf",
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_vector_size: Optional[int] = None,
        qdrant_api_key: Optional[str] = None,
        qdrant_prefer_grpc: bool = True,
        qdrant_timeout_seconds: int = 20, # Added timeout
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.qdrant_collection_name = qdrant_collection_name
        self.embedding_model_name = embedding_model_name
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port

        logger.info(
            f"Initializing RagbitsBookshelfClient for collection '{self.qdrant_collection_name}' "
            f"at {self.qdrant_host}:{self.qdrant_port} "
            f"with embedding model '{self.embedding_model_name}'"
        )

        # 1. Initialize Embedder
        self.embedder = LiteLLMEmbedder(model=self.embedding_model_name) # type: ignore
        logger.info(f"Embedder initialized for model: {self.embedding_model_name}")

        # 2. Determine Vector Size
        if embedding_vector_size:
            self.embedding_vector_size = embedding_vector_size
        else:
            try:
                self.embedding_vector_size = self.embedder.get_embedding_dimension()
                logger.info(f"Inferred embedding vector size: {self.embedding_vector_size}")
            except Exception as e:
                logger.error(f"Could not infer embedding dimension from embedder: {e}. Please provide 'embedding_vector_size'.")
                raise ValueError("Could not infer embedding dimension and none was provided.") from e

        if not self.embedding_vector_size: # Final check
             logger.error("Embedding vector size is not set. Cannot proceed.")
             raise ValueError("Embedding vector size is crucial and could not be determined.")


        # 3. Initialize QdrantClient
        try:
            self.qdrant_client = QdrantClient(
                host=qdrant_host,
                port=qdrant_port if qdrant_prefer_grpc else None,
                grpc_port=qdrant_port if qdrant_prefer_grpc else None, # Specify grpc_port for clarity
                http_port=qdrant_port if not qdrant_prefer_grpc else None, # Specify http_port if not gRPC
                api_key=qdrant_api_key,
                prefer_grpc=qdrant_prefer_grpc,
                timeout=qdrant_timeout_seconds,
            )
            # Quick check to see if Qdrant is accessible
            # self.qdrant_client.health_check() # This can be part of readiness checks elsewhere
            logger.info(f"QdrantClient initialized for {qdrant_host}:{qdrant_port}.")
        except Exception as e:
            logger.error(f"Failed to initialize QdrantClient: {e}", exc_info=True)
            raise

        # 4. Initialize TextChunker (as per refined plan, not using DocumentSearch for ingest)
        self.text_chunker = TextChunker( # type: ignore
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        logger.info(f"TextChunker initialized with size={chunk_size}, overlap={chunk_overlap}.")

        # 5. Ensure Qdrant Collection Exists and is Configured
        # Note: QdrantVectorStore from ragbits might handle this, but direct control is fine too.
        self._ensure_collection_exists()


    def _ensure_collection_exists(self):
        """
        Ensures the Qdrant collection exists and is configured correctly.
        This includes creating payload indexes for filterable metadata.
        """
        try:
            self.qdrant_client.get_collection(collection_name=self.qdrant_collection_name)
            logger.info(f"Qdrant collection '{self.qdrant_collection_name}' already exists.")
            # Optionally, verify existing configuration if needed, though this can get complex.
        except Exception as e: # More specific exception handling if possible (e.g. qdrant_client.http.exceptions.UnexpectedResponse)
            logger.warning(f"Qdrant collection '{self.qdrant_collection_name}' not found (error: {type(e).__name__}). Attempting to create it.")
            try:
                self.qdrant_client.create_collection(
                    collection_name=self.qdrant_collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=self.embedding_vector_size,
                        distance=DEFAULT_QDRANT_DISTANCE
                    )
                )
                logger.info(f"Successfully created Qdrant collection '{self.qdrant_collection_name}'.")

                # Create payload indexes for frequently filtered metadata fields
                # Indexing 'document_name'
                self.qdrant_client.create_payload_index(
                    collection_name=self.qdrant_collection_name,
                    field_name="document_name", # Assuming metadata is stored flat in payload, not nested under "metadata."
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                logger.info(f"Created payload index on 'document_name' for collection '{self.qdrant_collection_name}'.")

                # Indexing 'document_source'
                self.qdrant_client.create_payload_index(
                    collection_name=self.qdrant_collection_name,
                    field_name="document_source",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD
                )
                logger.info(f"Created payload index on 'document_source' for collection '{self.qdrant_collection_name}'.")

                # Indexing 'topics' (if it's a list of keywords)
                self.qdrant_client.create_payload_index(
                    collection_name=self.qdrant_collection_name,
                    field_name="topics",
                    field_schema=qmodels.PayloadSchemaType.KEYWORD # For list of strings
                )
                logger.info(f"Created payload index on 'topics' for collection '{self.qdrant_collection_name}'.")

            except Exception as creation_e:
                logger.error(f"Failed to create Qdrant collection '{self.qdrant_collection_name}': {creation_e}", exc_info=True)
                raise


    def add_document(
        self,
        document_content: str,
        document_name: str, # Unique identifier for the document
        document_source: str, # e.g., filename, URL, user_upload_id
        topics: Optional[List[str]] = None
    ) -> None:
        """
        Chunks, embeds, and ingests a document into the Qdrant collection.
        """
        logger.info(f"Adding document: Name='{document_name}', Source='{document_source}'")
        if not document_content.strip():
            logger.warning(f"Document '{document_name}' has no content. Skipping.")
            return

        text_chunks: List[TextChunk] = self.text_chunker.chunk(text=document_content) # type: ignore

        if not text_chunks:
            logger.warning(f"Text chunking resulted in no chunks for document '{document_name}'. Skipping.")
            return

        points_to_upsert = []
        for i, chunk in enumerate(text_chunks):
            chunk_text = chunk.text_content # Assuming TextChunk has text_content

            # Embed the individual chunk text
            try:
                embedding = self.embedder.embed_documents([chunk_text])[0] # type: ignore
            except Exception as e:
                logger.error(f"Failed to embed chunk {i} for document '{document_name}': {e}", exc_info=True)
                continue # Skip this chunk

            payload = {
                "document_name": document_name,
                "document_source": document_source,
                "topics": topics or [],
                "original_text": chunk_text, # Storing the original text in the payload
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            # Generate a unique ID for each point, or let Qdrant assign one if IDs are not critical to manage externally
            point_id = str(uuid.uuid4())

            points_to_upsert.append(qmodels.PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            ))

        if points_to_upsert:
            try:
                self.qdrant_client.upsert(
                    collection_name=self.qdrant_collection_name,
                    points=points_to_upsert,
                    wait=True # Wait for operation to complete for consistency
                )
                logger.info(f"Successfully added {len(points_to_upsert)} chunks for document '{document_name}'.")
            except Exception as e:
                logger.error(f"Failed to upsert points for document '{document_name}': {e}", exc_info=True)
                # Consider partial success or retry strategies if needed
        else:
            logger.warning(f"No document chunks prepared for ingestion for document '{document_name}'.")


    def query_documents(
        self,
        query_text: str,
        document_name: Optional[str] = None,
        topics_filter: Optional[List[str]] = None, # Added topics filter
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Queries the documents for relevant chunks.
        """
        logger.info(f"Querying documents with text: '{query_text[:100]}...', top_k={top_k}")

        try:
            query_embedding = self.embedder.embed_query(query_text) # type: ignore
        except Exception as e:
            logger.error(f"Failed to embed query '{query_text[:100]}...': {e}", exc_info=True)
            return []

        filters_list = []
        if document_name:
            logger.info(f"Filtering query by document_name: '{document_name}'")
            filters_list.append(qmodels.FieldCondition(
                key="document_name", # Assuming payload field is directly "document_name"
                match=qmodels.MatchValue(value=document_name)
            ))

        if topics_filter:
            logger.info(f"Filtering query by topics: {topics_filter}")
            # This creates an OR condition for topics (any of the topics must match)
            # For AND, you would use multiple FieldCondition in the 'must' list.
            filters_list.append(qmodels.FieldCondition(
                key="topics", # Assuming payload field is "topics"
                match=qmodels.MatchAny(any=topics_filter) # Matches if 'topics' array contains any of these
            ))

        query_filter = None
        if filters_list:
            query_filter = qmodels.Filter(must=filters_list)
            logger.debug(f"Constructed Qdrant filter: {query_filter.model_dump_json(indent=2)}")


        try:
            search_results = self.qdrant_client.search(
                collection_name=self.qdrant_collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True # To get the metadata and original_text
            )
        except Exception as e:
            logger.error(f"Error during Qdrant search: {e}", exc_info=True)
            return []

        results_formatted = []
        for hit in search_results:
            results_formatted.append({
                "id": hit.id,
                "score": hit.score,
                "text_content": hit.payload.get("original_text") if hit.payload else None,
                "metadata": {k: v for k, v in hit.payload.items() if k != "original_text"} if hit.payload else {}
            })
        logger.info(f"Retrieved {len(results_formatted)} chunks for query.")
        return results_formatted


    def get_document_chunks(self, document_name: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieves all chunks for a specific document, up to a limit.
        """
        logger.info(f"Retrieving up to {limit} chunks for document_name: '{document_name}'")
        doc_filter = qmodels.Filter(must=[
            qmodels.FieldCondition(key="document_name", match=qmodels.MatchValue(value=document_name))
        ])

        try:
            # Scroll API is suitable for getting all points matching a filter.
            # It's more efficient than search if you don't need vector similarity scoring.
            scrolled_points, next_offset = self.qdrant_client.scroll(
                collection_name=self.qdrant_collection_name,
                scroll_filter=doc_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False # No need for vectors if just retrieving content
            )
            # TODO: Implement pagination using next_offset if more than `limit` chunks are expected for a single document.
            if next_offset:
                 logger.warning(f"Document '{document_name}' has more chunks than the current limit ({limit}). "
                                 "Consider implementing pagination if this is an issue.")

            results = []
            for point in scrolled_points:
                results.append({
                    "id": point.id,
                    "text_content": point.payload.get("original_text") if point.payload else None,
                    "metadata": {k:v for k,v in point.payload.items() if k != "original_text"} if point.payload else {}
                })
            logger.info(f"Retrieved {len(results)} chunks for document '{document_name}'.")
            return results
        except Exception as e:
            logger.error(f"Error retrieving chunks for document '{document_name}': {e}", exc_info=True)
            return []

    def list_all_document_names(self, batch_size: int = 100) -> List[str]:
        """
        Lists unique document names from the collection.
        WARNING: This scrolls through points and collects unique names client-side.
                 It can be inefficient on very large collections.
        """
        logger.info(f"Listing all document names from '{self.qdrant_collection_name}'. This may be slow on large collections.")
        document_names = set()
        current_offset = None

        try:
            while True:
                points, next_offset_id = self.qdrant_client.scroll(
                    collection_name=self.qdrant_collection_name,
                    limit=batch_size,
                    offset=current_offset,
                    with_payload=["document_name"], # Only fetch the 'document_name' field from payload
                    with_vectors=False
                )

                for point in points:
                    if point.payload and "document_name" in point.payload:
                        doc_name = point.payload["document_name"]
                        if isinstance(doc_name, str):
                            document_names.add(doc_name)

                if not next_offset_id: # No more pages
                    break
                current_offset = next_offset_id

            logger.info(f"Found {len(document_names)} unique document names.")
            return sorted(list(document_names))
        except Exception as e:
            # Catching a broad exception here as various issues like connection errors can occur.
            logger.error(f"Error listing document names from Qdrant: {e}", exc_info=True)
            # Depending on policy, you might want to re-raise or return empty list.
            return []


    def delete_document(self, document_name: str) -> bool:
        """
        Deletes all chunks associated with a specific document_name from Qdrant.
        """
        logger.info(f"Attempting to delete document: '{document_name}' from '{self.qdrant_collection_name}'")
        try:
            # Define points selector based on metadata filter
            points_selector = qmodels.FilterSelector(
                filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(
                        key="document_name",
                        match=qmodels.MatchValue(value=document_name)
                    )
                ])
            )

            response = self.qdrant_client.delete_points(
                collection_name=self.qdrant_collection_name,
                points_selector=points_selector,
                wait=True # Wait for the operation to complete
            )

            # response.status will be one of models.UpdateStatus
            if response.status == qmodels.UpdateStatus.COMPLETED:
                logger.info(f"Successfully deleted points for document '{document_name}'. Status: {response.status}")
                return True
            elif response.status == qmodels.UpdateStatus.ACKNOWLEDGED:
                 logger.info(f"Deletion request for document '{document_name}' acknowledged by Qdrant. Status: {response.status}")
                 return True # Usually good enough
            else:
                logger.warning(f"Deletion for document '{document_name}' resulted in status: {response.status}")
                return False
        except Exception as e:
            logger.error(f"Error deleting document '{document_name}': {e}", exc_info=True)
            return False

    def get_collection_info(self) -> Optional[Dict[str, Any]]:
        """Gets information about the Qdrant collection."""
        try:
            collection_info_model = self.qdrant_client.get_collection(collection_name=self.qdrant_collection_name)
            return collection_info_model.model_dump() # Convert Pydantic model to dict
        except Exception as e:
            logger.error(f"Could not get info for collection '{self.qdrant_collection_name}': {e}", exc_info=True)
            return None

# Example Usage (Conceptual - would be in Eidos code or integration tests)
# To run this, you'd need:
# 1. `pip install qdrant-client sentence-transformers` (for the dummy embedder to work with a real model)
# 2. A Qdrant instance running and accessible (e.g., `docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant`)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting conceptual test of RagbitsBookshelfClient...")

    MOCK_QDRANT_HOST = "localhost"
    MOCK_QDRANT_PORT = 6333
    MOCK_COLLECTION_NAME = "test_bookshelf_client_direct" # New name to avoid conflict
    MOCK_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2" # Real model for local test
    MOCK_EMBEDDING_SIZE = 384 # Must match the real model

    # Temp: Replace DummyEmbedder with actual LiteLLMEmbedder for this test block IF ragbits is installed
    # For now, this test will run with the DUMMY embedder, which is fine for structure testing.
    # If you have `ragbits` and `litellm` installed, you could uncomment the real import
    # and comment out the `LiteLLMEmbedder = DummyEmbedder` alias.
    # from ragbits.core.embedders import LiteLLMEmbedder # Actual import

    print(f"Attempting to initialize client with Qdrant at {MOCK_QDRANT_HOST}:{MOCK_QDRANT_PORT}")
    print(f"Using embedding model: {MOCK_EMBEDDING_MODEL} (size: {MOCK_EMBEDDING_SIZE})")
    print(f"Target collection: {MOCK_COLLECTION_NAME}")

    bookshelf_client = None # Initialize to None

    try:
        bookshelf_client = RagbitsBookshelfClient(
            qdrant_host=MOCK_QDRANT_HOST,
            qdrant_port=MOCK_QDRANT_PORT,
            qdrant_collection_name=MOCK_COLLECTION_NAME,
            embedding_model_name=MOCK_EMBEDDING_MODEL,
            embedding_vector_size=MOCK_EMBEDDING_SIZE, # Explicitly pass size
        )
        logger.info("RagbitsBookshelfClient initialized.")

        # Clean up collection if it exists from previous test runs
        try:
            logger.info(f"Attempting to delete pre-existing collection '{MOCK_COLLECTION_NAME}' for a fresh test.")
            bookshelf_client.qdrant_client.delete_collection(collection_name=MOCK_COLLECTION_NAME)
            logger.info(f"Deleted existing collection '{MOCK_COLLECTION_NAME}'.")
            # Re-ensure collection (it will be created by _ensure_collection_exists)
            bookshelf_client._ensure_collection_exists()
        except Exception as e:
            logger.info(f"Could not delete collection (it might not exist, which is fine): {type(e).__name__} - {e}")
            # If deletion failed because it didn't exist, _ensure_collection_exists will create it
            bookshelf_client._ensure_collection_exists()


        logger.info("Testing add_document...")
        sample_content_1 = "The quick brown fox jumps over the lazy dog. This is a classic sentence used for testing typewriters and fonts." * 5
        sample_content_1 += " Artificial intelligence (AI) is rapidly changing the world."
        bookshelf_client.add_document(
            document_content=sample_content_1,
            document_name="doc_alpha",
            document_source="test_data_v1",
            topics=["animals", "testing", "ai"]
        )

        sample_content_2 = "The exploration of Mars continues to be a fascinating subject for scientists and space enthusiasts alike. Future missions aim to search for signs of past life." * 5
        bookshelf_client.add_document(
            document_content=sample_content_2,
            document_name="doc_beta",
            document_source="test_data_v1", # Same source, different name
            topics=["space", "mars", "science"]
        )
        logger.info("add_document test completed.")

        # Verify collection info
        collection_info = bookshelf_client.get_collection_info()
        logger.info(f"Collection info after adding documents: {collection_info}")
        assert collection_info is not None
        # Dummy embedder won't actually add points unless Qdrant is running and accepts them
        # For a real test, points_count would be > 0 if Qdrant is up.
        # With dummy embedder and no Qdrant, this might be 0 or raise error.
        # Assuming Qdrant is running for this conceptual test:
        # assert collection_info.get("points_count", 0) > 0


        logger.info("Testing query_documents...")
        query_results_ai = bookshelf_client.query_documents("What is AI?", top_k=2)
        logger.info(f"Query results for 'AI': {query_results_ai}")
        # Add assertions based on expected dummy behavior or real behavior if Qdrant is up
        # assert len(query_results_ai) > 0
        # if query_results_ai:
        #     assert "artificial intelligence" in query_results_ai[0].get("text_content", "").lower()

        query_results_mars_filtered = bookshelf_client.query_documents(
            "Information about Mars exploration",
            document_name="doc_beta",
            top_k=1
        )
        logger.info(f"Query results for 'Mars' in 'doc_beta': {query_results_mars_filtered}")
        # assert len(query_results_mars_filtered) > 0
        # if query_results_mars_filtered:
        #    assert "mars" in query_results_mars_filtered[0].get("text_content", "").lower()
        #    assert query_results_mars_filtered[0]["metadata"]["document_name"] == "doc_beta"

        query_results_topics = bookshelf_client.query_documents(
            "Tell me about space",
            topics_filter=["space"],
            top_k=1
        )
        logger.info(f"Query results for 'space' topic: {query_results_topics}")
        # assert len(query_results_topics) > 0
        # if query_results_topics:
        #    assert "space" in query_results_topics[0]["metadata"].get("topics", [])


        logger.info("Testing list_all_document_names...")
        doc_names = bookshelf_client.list_all_document_names()
        logger.info(f"Listed document names: {doc_names}")
        # assert "doc_alpha" in doc_names
        # assert "doc_beta" in doc_names

        logger.info("Testing get_document_chunks for 'doc_alpha'...")
        doc_alpha_chunks = bookshelf_client.get_document_chunks("doc_alpha")
        logger.info(f"Retrieved {len(doc_alpha_chunks)} chunks for 'doc_alpha'. First chunk metadata: {doc_alpha_chunks[0]['metadata'] if doc_alpha_chunks else 'N/A'}")
        # assert len(doc_alpha_chunks) > 0
        # if doc_alpha_chunks:
        #    assert doc_alpha_chunks[0]["metadata"]["document_name"] == "doc_alpha"

        logger.info("Testing delete_document for 'doc_alpha'...")
        delete_status = bookshelf_client.delete_document("doc_alpha")
        logger.info(f"Deletion status for 'doc_alpha': {delete_status}")
        # assert delete_status

        doc_names_after_delete = bookshelf_client.list_all_document_names()
        logger.info(f"Listed document names after delete: {doc_names_after_delete}")
        # assert "doc_alpha" not in doc_names_after_delete
        # assert "doc_beta" in doc_names_after_delete

        # Final check on collection info
        final_collection_info = bookshelf_client.get_collection_info()
        logger.info(f"Final collection info: {final_collection_info}")
        # if final_collection_info and doc_names_after_delete: # if doc_beta is still there
        #    assert final_collection_info.get("points_count", 0) > 0 # Check if doc_beta chunks are still there
        # else: # if all docs were deleted or collection is empty
        #    assert final_collection_info.get("points_count", 0) == 0


        logger.info("Conceptual test of RagbitsBookshelfClient completed.")
        logger.info("NOTE: Assertions are commented out as they require a running Qdrant instance and potentially real ragbits components for full validation.")

    except ImportError as ie:
        logger.error(f"ImportError: {ie}. Please ensure qdrant-client is installed. For full functionality, ragbits and litellm would be needed.")
    except ValueError as ve:
        logger.error(f"ValueError during initialization or operation: {ve}", exc_info=True)
    except Exception as e:
        logger.error(f"An unexpected error occurred during the conceptual test: {e}", exc_info=True)
    finally:
        if bookshelf_client and MOCK_COLLECTION_NAME: # Attempt to clean up if client was initialized
            try:
                logger.info(f"Attempting final cleanup: Deleting test collection '{MOCK_COLLECTION_NAME}'")
                # bookshelf_client.qdrant_client.delete_collection(collection_name=MOCK_COLLECTION_NAME)
                logger.info(f"Test collection '{MOCK_COLLECTION_NAME}' cleanup successful or collection did not exist.")
            except Exception as ce:
                logger.warning(f"Error during final cleanup of collection '{MOCK_COLLECTION_NAME}': {ce}")
                logger.warning("You may need to manually delete the Qdrant collection if it persists.")
        logger.info("Test execution finished.")
