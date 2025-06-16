# eidos_agent/utils/document_parser.py
import io
import logging
from pathlib import Path
from typing import Optional

# Ensure PyPDF2 and python-docx are installed: pip install pypdf2 python-docx
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None
    logging.getLogger(__name__).warning("PyPDF2 not found. PDF parsing disabled. Install with: pip install pypdf2")

try:
    import docx # python-docx library
except ImportError:
     docx = None
     logging.getLogger(__name__).warning("python-docx not found. DOCX parsing disabled. Install with: pip install python-docx")


from .logger import get_logger

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

def get_file_type(filename: str) -> Optional[str]:
    """Determine file type from extension."""
    extension = Path(filename).suffix.lower()
    if extension in SUPPORTED_EXTENSIONS:
        return extension
    logger.warning(f"Unsupported file extension: {extension} for filename: {filename}")
    return None

def parse_pdf(file_content: bytes) -> str:
    """Extract text content from PDF bytes."""
    if PdfReader is None:
        raise ImportError("PyPDF2 library is required for PDF parsing.")
    text = ""
    try:
        reader = PdfReader(io.BytesIO(file_content))
        logger.info(f"Parsing PDF with {len(reader.pages)} pages.")
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n" # Add newline between pages
        logger.info(f"Extracted ~{len(text)} characters from PDF.")
    except Exception as e:
        logger.error(f"Error parsing PDF content: {e}", exc_info=True)
        raise ValueError(f"Failed to parse PDF: {e}") from e
    return text

def parse_docx(file_content: bytes) -> str:
    """Extract text content from DOCX bytes."""
    if docx is None:
        raise ImportError("python-docx library is required for DOCX parsing.")
    text = ""
    try:
        document = docx.Document(io.BytesIO(file_content))
        logger.info(f"Parsing DOCX document.")
        for para in document.paragraphs:
            text += para.text + "\n"
        logger.info(f"Extracted ~{len(text)} characters from DOCX.")
    except Exception as e:
        logger.error(f"Error parsing DOCX content: {e}", exc_info=True)
        raise ValueError(f"Failed to parse DOCX: {e}") from e
    return text

def parse_txt(file_content: bytes) -> str:
    """Extract text content from TXT bytes."""
    try:
        # Try decoding with common encodings
        encodings_to_try = ['utf-8', 'latin-1', 'windows-1252']
        text = None
        for encoding in encodings_to_try:
            try:
                text = file_content.decode(encoding)
                logger.info(f"Successfully decoded TXT file with encoding: {encoding}")
                break
            except UnicodeDecodeError:
                continue # Try next encoding
        if text is None:
            raise ValueError("Could not decode TXT file with common encodings.")
        logger.info(f"Extracted ~{len(text)} characters from TXT.")
        return text
    except Exception as e:
        logger.error(f"Error parsing TXT content: {e}", exc_info=True)
        raise ValueError(f"Failed to parse TXT: {e}") from e

async def parse_document(filename: str, file_content: bytes) -> str:
    """Parses document content based on filename extension."""
    file_type = get_file_type(filename)
    if not file_type:
        raise ValueError(f"Unsupported file type for '{filename}'")

    logger.info(f"Parsing document '{filename}' of type '{file_type}'...")
    try:
        if file_type == ".pdf":
            return parse_pdf(file_content)
        elif file_type == ".docx":
            return parse_docx(file_content)
        elif file_type == ".txt":
            return parse_txt(file_content)
        else:
            # Should not be reached due to get_file_type check
            raise ValueError(f"Parser not implemented for type: {file_type}")
    except Exception as e:
        logger.error(f"Failed to parse document '{filename}': {e}", exc_info=True)
        # Re-raise to be handled by the caller (e.g., LogosCore)
        raise