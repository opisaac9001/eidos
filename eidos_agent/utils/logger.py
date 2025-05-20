# eidos_agent/utils/logger.py
import logging
from pathlib import Path
from datetime import datetime
import sys
import os 

# Define PROJECT_ROOT relative to this file's location
PROJECT_ROOT = Path(__file__).parent.parent.parent

def configure_logging():
    """Configure system-wide logging."""
    log_dir = PROJECT_ROOT / "logs"
    try:
        log_dir.mkdir(exist_ok=True)
        # Use a fixed name or rotating handler for production? For now, timestamped.
        log_file = log_dir / f"eidos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # --- Get desired console log level from environment ---
        # Default to INFO if not set or invalid
        log_level_name_env = os.getenv('API_LOG_LEVEL', 'info').upper()
        # Convert name to actual logging level (e.g., logging.DEBUG, logging.INFO)
        log_level_console = getattr(logging, log_level_name_env, logging.INFO)
        # ---

        root_logger = logging.getLogger()
        
        # Prevent duplicate handlers if called multiple times
        if root_logger.hasHandlers():
             # Check if handlers are already configured correctly (simple check)
             # This avoids reconfiguring if logging was already set up perfectly.
             # A more robust check might compare handler types and levels.
             # For now, let's clear existing handlers to ensure a clean setup.
            logger = get_logger(__name__) # Get logger for this function
            logger.debug("Removing existing logging handlers before reconfiguring.")
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
                handler.close() # Ensure handlers are closed properly

        # --- Set Root Logger Level ---
        # Set root to DEBUG so handlers can filter messages appropriately.
        # If root is INFO, DEBUG messages will never reach any handler.
        root_logger.setLevel(logging.DEBUG) 
        # ---

        # --- Create File Handler ---
        # File handler always logs at DEBUG level to capture everything.
        try:
             file_handler = logging.FileHandler(log_file, encoding='utf-8')
             file_handler.setLevel(logging.DEBUG) 
             file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)')
             file_handler.setFormatter(file_formatter)
             root_logger.addHandler(file_handler)
        except Exception as file_log_e:
             # Fallback to console if file logging fails
             print(f"ERROR: Failed to configure file logging to {log_file}: {file_log_e}", file=sys.stderr)


        # --- Create Console Handler ---
        console_handler = logging.StreamHandler(sys.stdout)
        # Set console level based *only* on the environment variable read earlier
        console_handler.setLevel(log_level_console) 
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        # Attempt to set console encoding
        try:
            if hasattr(sys.stdout, 'reconfigure') and callable(sys.stdout.reconfigure):
                 sys.stdout.reconfigure(encoding='utf-8')
        except Exception as encoding_e:
             # Log warning if reconfigure fails but continue
             print(f"Warning: Could not reconfigure stdout encoding: {encoding_e}", file=sys.stderr)
        root_logger.addHandler(console_handler)
        # ---

        # Quieten noisy libraries (keep these)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.INFO) # Can be noisy at DEBUG

        # --- Log Confirmation ---
        # Use the logger *after* handlers are added
        logger_confirm = logging.getLogger(__name__) # Get logger instance again after setup
        logger_confirm.info(f"Logging configured. Log file: {log_file}. Console Level: {logging.getLevelName(log_level_console)}")
        # Add a specific debug message to test if DEBUG level is working *now*
        logger_confirm.debug("Debug level logging is active.") 
        # ---

    except Exception as e:
        # Fallback basic config if anything goes wrong during setup
        print(f"CRITICAL ERROR configuring logging: {e}", file=sys.stderr)
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logger_fallback = logging.getLogger(__name__)
        logger_fallback.error(f"configure_logging failed: {e}. Using basic config (INFO level).", exc_info=True)


def get_logger(name: str) -> logging.Logger:
    """Helper to get a logger instance."""
    # Basic check if root logger has handlers - assumes configure_logging was called or basicConfig ran.
    if not logging.getLogger().hasHandlers():
         # Apply basic config just in case configure_logging failed silently before this was called.
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
         logging.getLogger(__name__).warning("Logger accessed before handlers were configured. Applied basic config.")
    return logging.getLogger(name)