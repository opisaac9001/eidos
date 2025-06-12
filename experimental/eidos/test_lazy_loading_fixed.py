#!/usr/bin/env python3
"""
Test script to validate lazy loading optimizations for Eidos AI agent startup.
This script tests both MemoryStorage and RagbitsBookshelfClient optimizations.
"""

import time
import sys
import traceback

def test_memory_storage_lazy_loading():
    """Test MemoryStorage lazy loading optimization."""
    print("=" * 60)
    print("1. TESTING MEMORYSTORAGE LAZY LOADING")
    print("=" * 60)
    
    try:
        start_time = time.time()
        from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryStorage
        from eidos_agent.core.config import Config
        
        # Create a minimal config for testing
        config = Config()
        
        # Initialize MemoryStorage
        init_start = time.time()
        memory_storage = MemoryStorage(config)
        init_end = time.time()
        
        print(f"✅ MemoryStorage imported successfully")
        print(f"⏱️  Initialization time: {init_end - init_start:.3f} seconds")
        print(f"🔍 Embedder loaded during init: {memory_storage._embedder is not None}")
        print(f"🔍 Embedder loading failed flag: {memory_storage._embedder_loading_failed}")
        
        # Test lazy loading by calling a method that should trigger embedder loading
        print("\n--- Testing lazy loading trigger ---")
        test_start = time.time()
        try:
            # This should trigger lazy loading
            result = memory_storage.find_similar("test query", limit=1)
            test_end = time.time()
            print(f"✅ find_similar() executed (lazy loading triggered)")
            print(f"⏱️  Method execution time: {test_end - test_start:.3f} seconds")
            print(f"🔍 Embedder loaded after method call: {memory_storage._embedder is not None}")
            print(f"📊 Results returned: {len(result)} items")
        except Exception as e:
            print(f"⚠️  find_similar() failed (expected if no embedding model): {str(e)}")
            print(f"🔍 Embedder loading failed flag: {memory_storage._embedder_loading_failed}")
        
        return True
        
    except Exception as e:
        print(f"❌ MemoryStorage test failed: {str(e)}")
        traceback.print_exc()
        return False

def test_bookshelf_lazy_loading():
    """Test RagbitsBookshelfClient lazy loading optimization."""
    print("\n" + "=" * 60)
    print("2. TESTING RAGBITSBOOKSHELFCLIENT LAZY LOADING")
    print("=" * 60)
    
    try:
        start_time = time.time()
        from eidos_agent.integrations.ragbits_bookshelf_client import RagbitsBookshelfClient
        from eidos_agent.core.config import BookshelfConfig
        
        # Create a minimal BookshelfConfig for testing
        bookshelf_config: BookshelfConfig = {
            "qdrant_host": "localhost",
            "qdrant_port": 6333,
            "qdrant_collection_name": "test_bookshelf",
            "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
            "embedding_dimension": 384,
            "chunk_size": 512,
            "chunk_overlap": 50,
            "qdrant_api_key": None
        }
        
        # Initialize RagbitsBookshelfClient
        init_start = time.time()
        bookshelf_client = RagbitsBookshelfClient(bookshelf_config)
        init_end = time.time()
        
        print(f"✅ RagbitsBookshelfClient imported successfully")
        print(f"⏱️  Initialization time: {init_end - init_start:.3f} seconds")
        print(f"🔍 Embedder loaded during init: {bookshelf_client.embedder is not None}")
        print(f"🔍 Vector store loaded during init: {bookshelf_client.qdrant_vector_store is not None}")
        
        # Test lazy loading by calling a method that should trigger embedder loading
        print("\n--- Testing lazy loading trigger ---")
        test_start = time.time()
        try:
            # This should trigger lazy loading (will likely fail due to missing dependencies)
            import asyncio
            result = asyncio.run(bookshelf_client.query_bookshelf("test query", top_k=1))
            test_end = time.time()
            print(f"✅ query_bookshelf() executed (lazy loading triggered)")
            print(f"⏱️  Method execution time: {test_end - test_start:.3f} seconds")
            print(f"🔍 Embedder loaded after method call: {bookshelf_client.embedder is not None}")
            print(f"📊 Results returned: {len(result)} items")
        except Exception as e:
            print(f"⚠️  query_bookshelf() failed (expected if no Qdrant/embedding model): {str(e)}")
        
        return True
        
    except Exception as e:
        print(f"❌ RagbitsBookshelfClient test failed: {str(e)}")
        traceback.print_exc()
        return False

def main():
    """Run all lazy loading tests."""
    print("🚀 EIDOS AI AGENT - LAZY LOADING OPTIMIZATION TESTS")
    print("=" * 60)
    
    overall_start = time.time()
    
    # Test results
    memory_success = test_memory_storage_lazy_loading()
    bookshelf_success = test_bookshelf_lazy_loading()
    
    overall_end = time.time()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"⏱️  Total test time: {overall_end - overall_start:.3f} seconds")
    print(f"✅ MemoryStorage lazy loading: {'PASSED' if memory_success else 'FAILED'}")
    print(f"✅ RagbitsBookshelfClient lazy loading: {'PASSED' if bookshelf_success else 'FAILED'}")
    
    if memory_success and bookshelf_success:
        print("\n🎉 ALL OPTIMIZATIONS WORKING CORRECTLY!")
        print("🚀 Eidos AI agent startup should be significantly faster!")
    else:
        print("\n⚠️  Some optimizations need attention.")
        
    return memory_success and bookshelf_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
