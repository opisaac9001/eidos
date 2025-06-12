#!/bin/bash

# Eidos Main System Runner
# This script starts the main Eidos AI Agent system

echo "========================================"
echo "Eidos AI Agent - Main System"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting from directory: $SCRIPT_DIR"
echo "Server will be available at: http://localhost:8088"
echo "Web interface at: http://localhost:8088"
echo ""
echo "Press Ctrl+C to stop the server"
echo "----------------------------------------"

# Run the main system
python3 main.py
