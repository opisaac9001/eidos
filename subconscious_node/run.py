"""
Manager script to run both the API server and the thinker process.
"""
import subprocess
import sys
import os
import time

def main():
    # Get the absolute path to the subconscious_node directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Start thinker.py in a separate process
    print("Starting thinker process...")
    thinker_process = subprocess.Popen([sys.executable, "thinker.py"], cwd=base_dir)
    
    # Give thinker a moment to initialize
    time.sleep(2)
    
    # Start the API server
    print("Starting API server...")
    api_process = subprocess.Popen([sys.executable, "api.py"], cwd=base_dir)
    
    try:
        # Wait for both processes
        api_process.wait()
        thinker_process.wait()
    except KeyboardInterrupt:
        print("\nShutting down processes...")
        api_process.terminate()
        thinker_process.terminate()
        api_process.wait()
        thinker_process.wait()
        print("Processes terminated.")

if __name__ == "__main__":
    main()
