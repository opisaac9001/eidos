import subprocess
import os
import time
import logging
import requests # For health check
from pathlib import Path
from typing import Optional

# Assuming the client is in this structure, adjust if necessary
from eidos_agent.features.subconscious_interface_to_node.subconscious.client import (
    SUBCONSCIOUS_NODE_BASE_URL as CLIENT_SUBCONSCIOUS_NODE_BASE_URL, # Use the one from client
    send_node_control_command,
    DEFAULT_TIMEOUT as CLIENT_DEFAULT_TIMEOUT
)

logger = logging.getLogger(__name__)
subconscious_process: Optional[subprocess.Popen] = None

# Define Project Root - assuming this file is eidos_agent/core/subconscious_orchestrator.py
# So, two levels up to reach the project root where 'subconscious_node' package resides.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def launch_subconscious_node_process(
    stdout_log_path: str = "logs/subconscious_stdout.log",
    stderr_log_path: str = "logs/subconscious_stderr.log"
) -> Optional[subprocess.Popen]:
    """
    Launches the Subconscious Node API server as a subprocess using Uvicorn.

    Args:
        stdout_log_path: Path to redirect subprocess stdout.
        stderr_log_path: Path to redirect subprocess stderr.

    Returns:
        The subprocess.Popen object if successful, None otherwise.
    """
    global subconscious_process
    if subconscious_process is not None and subconscious_process.poll() is None:
        logger.info("Subconscious Node process appears to be already running.")
        return subconscious_process

    port = os.getenv("EIDOS_SUBCONSCIOUS_NODE_PORT", "8000")
    host = "0.0.0.0" # Or make this configurable via env var too if needed

    # Command using Uvicorn
    cmd = [
        "uvicorn",
        "subconscious_node.api:app",
        f"--host={host}",
        f"--port={port}",
        # "--reload" # Useful for dev, but remove for "production" Eidos runs
    ]
    # Ensure log directory exists
    os.makedirs(Path(stdout_log_path).parent, exist_ok=True)
    os.makedirs(Path(stderr_log_path).parent, exist_ok=True)

    try:
        logger.info(f"Launching Subconscious Node API: {' '.join(cmd)}")
        logger.info(f"Subconscious Node CWD: {PROJECT_ROOT}")
        logger.info(f"Subconscious Node stdout log: {stdout_log_path}")
        logger.info(f"Subconscious Node stderr log: {stderr_log_path}")

        with open(stdout_log_path, 'ab') as stdout_file, open(stderr_log_path, 'ab') as stderr_file:
            subconscious_process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT, # Run from the project root
                stdout=stdout_file,
                stderr=stderr_file,
                # Close fds in POSIX environments to prevent issues with child processes inheriting them
                close_fds=os.name == 'posix'
            )
        logger.info(f"Subconscious Node process started with PID: {subconscious_process.pid}.")
        return subconscious_process
    except FileNotFoundError:
        logger.error(
            f"Failed to launch Subconscious Node: 'uvicorn' command not found. "
            "Ensure Uvicorn is installed and in PATH. "
            f"Attempted command: {' '.join(cmd)}"
        )
        subconscious_process = None
        return None
    except Exception as e:
        logger.error(f"Failed to launch Subconscious Node: {e}", exc_info=True)
        subconscious_process = None
        return None

def terminate_subconscious_node_process():
    """
    Terminates the Subconscious Node process if it's running.
    """
    global subconscious_process
    if subconscious_process and subconscious_process.poll() is None:
        logger.info(f"Terminating Subconscious Node process (PID: {subconscious_process.pid})...")
        subconscious_process.terminate() # Send SIGTERM
        try:
            subconscious_process.wait(timeout=10) # Wait for graceful shutdown
            logger.info("Subconscious Node process terminated.")
        except subprocess.TimeoutExpired:
            logger.warning("Subconscious Node process did not terminate in time (SIGTERM), attempting to kill (SIGKILL)...")
            subconscious_process.kill() # Send SIGKILL
            try:
                subconscious_process.wait(timeout=5) # Wait for kill
                logger.info("Subconscious Node process killed.")
            except subprocess.TimeoutExpired:
                logger.error("Subconscious Node process failed to be killed. Manual intervention may be required.")
            except Exception as e_kill:
                 logger.error(f"Error during SIGKILL: {e_kill}", exc_info=True)
        except Exception as e_term:
            logger.error(f"Error during SIGTERM: {e_term}", exc_info=True)
            # Fallback to kill if terminate wait fails for other reasons
            if subconscious_process.poll() is None: # Check if it's still running
                subconscious_process.kill()
                subconscious_process.wait() # Should be quick after kill
        subconscious_process = None
    else:
        logger.info("Subconscious Node process not running or already terminated.")

def check_subconscious_api_health(max_wait_seconds: int = 30, check_interval: int = 2) -> bool:
    """
    Checks if the Subconscious Node API is healthy by polling its root endpoint.

    Args:
        max_wait_seconds: Maximum time to wait for the API to become healthy.
        check_interval: Interval in seconds between health checks.

    Returns:
        True if the API is healthy within the max_wait_seconds, False otherwise.
    """
    if not subconscious_process or subconscious_process.poll() is not None:
        logger.warning("Health Check: Subconscious node process is not running.")
        return False

    # The SUBCONSCIOUS_NODE_BASE_URL from client.py already considers env var EIDOS_SUBCONSCIOUS_NODE_BASE_URL
    # and EIDOS_SUBCONSCIOUS_NODE_PORT (implicitly, as it's part of the URL construction if port is in env var)
    health_check_url = f"{CLIENT_SUBCONSCIOUS_NODE_BASE_URL}/" # Root endpoint

    logger.info(f"Checking Subconscious Node API health at {health_check_url} for up to {max_wait_seconds}s...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        if subconscious_process.poll() is not None:
            logger.error(f"Health Check: Subconscious node process terminated prematurely (PID: {subconscious_process.pid}). Exit code: {subconscious_process.returncode}")
            return False
        try:
            # Use a short timeout for individual health check requests
            response = requests.get(health_check_url, timeout=CLIENT_DEFAULT_TIMEOUT)
            response.raise_for_status() # Check for 2xx status codes
            # Further check if response content is as expected, e.g., if it's JSON and has a specific key
            # For now, a 200 OK is sufficient to consider it "healthy enough" for startup.
            # The subconscious_node root returns: {"message": "Pathos Subconscious Node is active..."}
            if response.json().get("message"):
                 logger.info(f"Subconscious Node API is healthy. Response: {response.json().get('message')}")
                 return True
            else:
                logger.warning(f"Subconscious Node API responded 2xx but with unexpected content at {health_check_url}.")

        except requests.exceptions.RequestException as e:
            logger.debug(f"Health Check: API not yet healthy (Attempt: {int((time.time() - start_time) / check_interval) + 1}). Error: {e}")
        except Exception as e_other: # Catch other errors like json.JSONDecodeError if API returns malformed JSON
            logger.warning(f"Health Check: Error during health check call to {health_check_url}: {e_other}")

        time.sleep(check_interval)

    logger.error(f"Subconscious Node API failed to become healthy at {health_check_url} after {max_wait_seconds} seconds.")
    return False

def initialize_subconscious_node_state() -> bool:
    """
    Initializes the Subconscious Node to a default operational state (e.g., AWAKE_THINKING).

    Returns:
        True if the state was successfully set, False otherwise.
    """
    logger.info("Initializing Subconscious Node state to AWAKE_THINKING...")
    # This uses the send_node_control_command from the client, which already handles
    # the SUBCONSCIOUS_NODE_BASE_URL and logging.
    success = send_node_control_command(node_state="AWAKE_THINKING")
    if success:
        logger.info("Subconscious Node state initialized to AWAKE_THINKING successfully.")
    else:
        logger.error("Failed to initialize Subconscious Node state to AWAKE_THINKING.")
    return success

# Example of how these would be called in Eidos main application
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Subconscious Orchestrator Test ---")

    # 1. Launch
    process = launch_subconscious_node_process()
    launched_successfully = process is not None and process.poll() is None
    print(f"Launch successful: {launched_successfully}")

    healthy = False
    if launched_successfully:
        # 2. Check Health
        healthy = check_subconscious_api_health(max_wait_seconds=20) # Wait shorter for local test
        print(f"API Healthy: {healthy}")

        if healthy:
            # 3. Initialize State
            initialized = initialize_subconscious_node_state()
            print(f"State Initialized: {initialized}")

            # Let it run for a bit
            print("Subconscious node running. Orchestrator will sleep for 10s before terminating...")
            time.sleep(10)
        else:
            print("Subconscious API not healthy, skipping state initialization.")
    else:
        print("Subconscious process failed to launch, skipping health check and initialization.")

    # 4. Terminate (on Eidos shutdown)
    print("Terminating subconscious node process...")
    terminate_subconscious_node_process()
    if process and process.poll() is not None:
        print(f"Process terminated with code: {process.returncode}")
    else:
        print("Process termination check done.")

    logger.info("--- Subconscious Orchestrator Test Finished ---")

# Instructions for Eidos main.py integration:
#
# In your main Eidos application startup:
# from eidos_agent.core import subconscious_orchestrator
#
# subconscious_orchestrator.launch_subconscious_node_process()
# if subconscious_orchestrator.check_subconscious_api_health():
#     subconscious_orchestrator.initialize_subconscious_node_state()
# else:
#     logging.critical("Subconscious Node could not be started or is unhealthy. Eidos may have limited functionality.")
#     # Decide if Eidos should exit or continue
#
# In your main Eidos application shutdown (e.g., FastAPI shutdown event, try/finally block):
# subconscious_orchestrator.terminate_subconscious_node_process()
#
# Ensure that the EIDOS_SUBCONSCIOUS_NODE_PORT and EIDOS_SUBCONSCIOUS_NODE_BASE_URL
# environment variables are consistent between the orchestrator and the client logic.
# The client uses EIDOS_SUBCONSCIOUS_NODE_BASE_URL which should include the port.
# The orchestrator uses EIDOS_SUBCONSCIOUS_NODE_PORT to launch the process.
# The health check in the orchestrator uses CLIENT_SUBCONSCIOUS_NODE_BASE_URL from the client.
# It's recommended that EIDOS_SUBCONSCIOUS_NODE_BASE_URL (e.g., "http://localhost:8000") is the primary
# env var, and EIDOS_SUBCONSCIOUS_NODE_PORT is derived from it if needed, or set consistently.
# For this implementation, CLIENT_SUBCONSCIOUS_NODE_BASE_URL (which uses EIDOS_SUBCONSCIOUS_NODE_BASE_URL)
# is used for health checks, and EIDOS_SUBCONSCIOUS_NODE_PORT is used for launching.
# This implies EIDOS_SUBCONSCIOUS_NODE_BASE_URL should be like "http://<host>:<port>".
# The launch function gets the port from EIDOS_SUBCONSCIOUS_NODE_PORT, defaulting to 8000.
# The client gets the base URL from EIDOS_SUBCONSCIOUS_NODE_BASE_URL, defaulting to "http://localhost:8000".
# These defaults are consistent. If overridden, they must be overridden consistently.
# A single env var for the full base URL (EIDOS_SUBCONSCIOUS_NODE_BASE_URL) is generally simpler,
# and the port can be parsed from it if needed for the Uvicorn command.
# However, the current setup with two distinct (but consistently defaulted) env vars also works.

```
