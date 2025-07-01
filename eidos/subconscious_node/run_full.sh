#!/bin/bash

# Master Subconscious Node Runner
# This script starts both the thinker and API server

echo "========================================"
echo "Pathos Subconscious Node - Full System"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting from directory: $SCRIPT_DIR"
echo ""

# Function to handle cleanup
cleanup() {
    echo ""
    echo "Shutting down subconscious node..."
    jobs -p | xargs -r kill
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo "Starting Pathos Subconscious Node components..."
echo ""

# Start the thinking loop in background
echo "Starting thinking loop..."
python3 thinker.py &
THINKER_PID=$!

# Give it a moment to start
sleep 2

# Start the API server in background
echo "Starting API server..."
echo "API will be available at: http://localhost:8000"
echo "API documentation at: http://localhost:8000/docs"
echo ""
python3 api.py &
API_PID=$!

echo "Both components are running!"
echo "Thinker PID: $THINKER_PID"
echo "API PID: $API_PID"
echo ""
echo "Press Ctrl+C to stop both components"
echo "----------------------------------------"

# Wait for both processes
wait
