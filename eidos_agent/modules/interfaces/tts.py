import logging
import platform
import subprocess
import asyncio

# Adjust import path
from eidos_agent.utils.logger import get_logger
from eidos_agent.core.config import Config # Import Config

logger = get_logger(__name__)

class TextToSpeechService:
    """
    Basic Text-to-Speech service using system commands or print fallback.
    """
    def __init__(self, config: Config): # Accept config
        self.config = config
        # self.voice_config = config.get_voice_config() # Get voice specific config if needed
        self.system = platform.system()
        logger.info(f"TTS Service initialized (System: {self.system}). Using basic system TTS or print.")

    async def speak(self, text: str):
        """Speak the given text using basic system TTS or print."""
        if not text:
            return

        logger.info(f"TTS Request: '{text}'")
        # Print is handled by the frontend (Open WebUI).
        # This method is primarily for the backend to speak directly if needed.
        # For the API mode using Open WebUI, this method is generally NOT called
        # by the main chat endpoint. It would be used for backend-initiated speech.
        # print(f"\nEidos (Speaking): {text}\n") # Handled by frontend

        # --- Basic System TTS (Fire-and-forget) ---
        # This is non-blocking but doesn't guarantee completion or handle errors well.
        # Real async TTS often requires dedicated libraries or services.
        cmd = None
        try:
            if self.system == "Darwin": # macOS
                cmd = ['say', text]
            elif self.system == "Linux":
                # Check if espeak-ng is installed (preferred over espeak)
                espeak_cmd = None
                if subprocess.call(['which', 'espeak-ng'], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
                    espeak_cmd = 'espeak-ng'
                elif subprocess.call(['which', 'espeak'], stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0:
                    espeak_cmd = 'espeak'

                if espeak_cmd:
                     cmd = [espeak_cmd, text]
                else:
                     logger.warning("TTS: 'espeak-ng' or 'espeak' command not found on Linux. Cannot speak aloud.")
            else: # Windows or other
                logger.warning(f"TTS: System TTS not implemented for {self.system}. Printing only.")
                # Consider pyttsx3 for cross-platform basic TTS, but manage blocking carefully.

            if cmd:
                # Run command in the background without waiting
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.debug(f"Executed TTS command: {' '.join(cmd)}")

        except Exception as e:
            logger.error(f"Error executing system TTS command: {e}", exc_info=True)
