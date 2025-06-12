#!/bin/bash

# Subconscious Node API Runner
# This script starts the Pathos Subconscious Node API server

echo "========================================"
echo "Pathos Subconscious Node API"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting from directory: $SCRIPT_DIR"
echo "Server will be available at: http://localhost:8000"
echo "API documentation at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "----------------------------------------"

# Run the API server
python3 api.py
