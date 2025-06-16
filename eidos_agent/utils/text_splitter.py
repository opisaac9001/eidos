# eidos_agent/utils/text_splitter.py
import logging
from typing import List

from .logger import get_logger

logger = get_logger(__name__)

def chunk_text_by_char(
    text: str,
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """
    Splits text into chunks based on character count with overlap.
    Simple implementation. Consider sentence splitting or token splitting for better results.
    """
    if not text:
        return []
    if chunk_overlap < 0:
         logger.warning(f"Chunk overlap ({chunk_overlap}) is negative. Setting overlap to 0.")
         chunk_overlap = 0
    if chunk_size <= 0:
         logger.error(f"Chunk size ({chunk_size}) must be positive.")
         raise ValueError("Chunk size must be positive")
    if chunk_overlap >= chunk_size:
        logger.warning(f"Chunk overlap ({chunk_overlap}) >= chunk size ({chunk_size}). Setting overlap to chunk_size / 4.")
        chunk_overlap = chunk_size // 4

    chunks = []
    start_index = 0
    text_len = len(text)

    logger.info(f"Chunking text of length {text_len} with size={chunk_size}, overlap={chunk_overlap}")

    while start_index < text_len:
        end_index = min(start_index + chunk_size, text_len)
        chunk = text[start_index:end_index]
        # Ensure chunk isn't just whitespace if possible (can happen with large overlaps)
        if chunk.strip():
            chunks.append(chunk)

        # Move start index for the next chunk
        next_start_index = start_index + chunk_size - chunk_overlap

        # Check if we are making progress
        if next_start_index <= start_index:
             if end_index == text_len: break # Reached the end
             logger.warning("Text chunking stall detected due to overlap/size ratio, advancing past current chunk.")
             next_start_index = end_index # Force advance

        start_index = next_start_index

    logger.info(f"Split text into {len(chunks)} chunks.")
    return chunks

# --- Future Enhancements ---
# def chunk_text_by_sentence(text: str, max_chars_per_chunk: int) -> List[str]:
#    # Use NLP library like spaCy or NLTK to split into sentences first,
#    # then group sentences into chunks respecting max_chars_per_chunk.
#    pass

# def chunk_text_by_tokens(text: str, model_tokenizer, max_tokens: int, overlap_tokens: int) -> List[str]:
#    # Use a tokenizer (e.g., from Hugging Face transformers or tiktoken)
#    # to split based on token count, which aligns better with LLM context windows.
#    pass