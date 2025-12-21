#!/bin/bash

echo "================================================================================"
echo "Universal Document Learning - Web UI"
echo "================================================================================"
echo ""

# Check if ANTHROPIC_API_KEY is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "[ERROR] ANTHROPIC_API_KEY environment variable is not set!"
    echo ""
    echo "Please set it first:"
    echo "  export ANTHROPIC_API_KEY=sk-ant-api03-..."
    echo ""
    echo "Or add it to your .env file."
    echo ""
    exit 1
fi

echo "[OK] ANTHROPIC_API_KEY is set: ${ANTHROPIC_API_KEY:0:15}..."
echo ""

echo "Starting FastAPI server..."
echo ""
echo "The web UI will be available at:"
echo "  http://localhost:8000/app"
echo ""
echo "Press Ctrl+C to stop the server."
echo ""
echo "================================================================================"
echo ""

python -m src.api.main
