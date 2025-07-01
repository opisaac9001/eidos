# Lazy imports to avoid startup failures when optional dependencies are missing
def _lazy_import_ragbits_bookshelf_client():
    """Lazy import of RagbitsBookshelfClient to avoid startup failures."""
    try:
        from .ragbits_bookshelf_client import RagbitsBookshelfClient
        return RagbitsBookshelfClient
    except ImportError as e:
        # Return a dummy class that raises informative errors
        class DummyRagbitsBookshelfClient:
            def __init__(self, *args, **kwargs):
                raise ImportError(f"RagbitsBookshelfClient requires ragbits library: {e}")
        return DummyRagbitsBookshelfClient

def _lazy_import_document_chunk_info():
    """Lazy import of DocumentChunkInfo to avoid startup failures."""
    try:
        from .ragbits_bookshelf_client import DocumentChunkInfo
        return DocumentChunkInfo
    except ImportError as e:
        # Return a dummy TypedDict that raises informative errors
        from typing import TypedDict, Dict, Any
        class DummyDocumentChunkInfo(TypedDict):
            chunk_id: str
            document_id: str
            chunk_index: int
            text_preview: str
            metadata: Dict[str, Any]
        return DummyDocumentChunkInfo

# Make components available for import but load them lazily
RagbitsBookshelfClient = None
DocumentChunkInfo = None

def __getattr__(name):
    global RagbitsBookshelfClient, DocumentChunkInfo
    if name == "RagbitsBookshelfClient":
        if RagbitsBookshelfClient is None:
            RagbitsBookshelfClient = _lazy_import_ragbits_bookshelf_client()
        return RagbitsBookshelfClient
    elif name == "DocumentChunkInfo":
        if DocumentChunkInfo is None:
            DocumentChunkInfo = _lazy_import_document_chunk_info()
        return DocumentChunkInfo
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
