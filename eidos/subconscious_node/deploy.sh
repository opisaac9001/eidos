#!/bin/bash

# Deployment script for Pathos Subconscious Node
# This script sets up the subconscious node as a standalone system

echo "========================================"
echo "Pathos Subconscious Node - Deployment"
echo "========================================"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if pip is available
if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
    echo "Error: pip is required but not installed."
    exit 1
fi

echo "Installing Python dependencies..."
pip3 install -r requirements.txt

echo ""
echo "Making scripts executable..."
chmod +x run.sh
chmod +x run_thinker.sh
chmod +x run_full.sh

echo ""
echo "Verifying configuration..."
if [ ! -f "config.json" ]; then
    echo "Warning: config.json not found. Please ensure it exists before running."
else
    echo "Configuration file found: ✓"
fi

echo ""
echo "Testing imports..."
python3 -c "
try:
    import api
    import thinker
    import context_store
    import mood
    import utils
    import detectors
    import eidos_context_retriever
    print('All modules import successfully: ✓')
except ImportError as e:
    print(f'Import error: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "Deployment completed successfully!"
    echo "========================================"
    echo ""
    echo "To start the subconscious node:"
    echo "  ./run_full.sh       - Full system (recommended)"
    echo "  ./run.sh            - API server only"
    echo "  ./run_thinker.sh    - Thinking loop only"
    echo ""
    echo "API will be available at: http://localhost:8000"
    echo "API documentation at: http://localhost:8000/docs"
else
    echo ""
    echo "Deployment failed. Please check the error messages above."
    exit 1
fi
