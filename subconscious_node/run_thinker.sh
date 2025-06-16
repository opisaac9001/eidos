#!/bin/bash

# Subconscious Node Thinker Runner
# This script starts the Pathos Subconscious Node thinking loop

echo "========================================"
echo "Pathos Subconscious Node - Thinker"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting thinking loop from directory: $SCRIPT_DIR"
echo "This will generate continuous subconscious thoughts"
echo ""
echo "Press Ctrl+C to stop the thinking loop"
echo "----------------------------------------"

# Run the thinker loop
python3 thinker.py
