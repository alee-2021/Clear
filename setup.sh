#!/bin/bash
# =============================================================================
# MINI-MIND SETUP SCRIPT
# =============================================================================
# This script installs all dependencies needed to run Mini-Mind.
#
# Usage:
#   On Mac/Linux: bash setup.sh
#   On Windows (Git Bash): bash setup.sh
#
# What it does:
#   1. Creates a virtual environment (isolated Python environment)
#   2. Installs required Python packages
#   3. Tells you how to start the app
# =============================================================================

echo "========================================"
echo "🧠 Mini-Mind Setup"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ Python is not installed!"
    echo "Please install Python 3.8+ from https://python.org"
    exit 1
fi

# Use python3 if available, otherwise python
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "✓ Found Python: $($PYTHON_CMD --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
$PYTHON_CMD -m venv venv

# Activate virtual environment
echo "🔄 Activating virtual environment..."
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    # Windows (Git Bash)
    source venv/Scripts/activate
else
    # Mac/Linux
    source venv/bin/activate
fi

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install required packages
echo ""
echo "📥 Installing dependencies..."
echo "   - FastAPI (web framework)"
echo "   - Uvicorn (ASGI server)"
echo "   - Pydantic (data validation)"
echo "   - dateparser (natural language dates)"
echo ""

pip install fastapi uvicorn pydantic dateparser

echo ""
echo "========================================"
echo "✅ Setup Complete!"
echo "========================================"
echo ""
echo "To start Mini-Mind:"
echo ""
echo "  1. Activate the virtual environment:"
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "     source venv/Scripts/activate"
else
    echo "     source venv/bin/activate"
fi
echo ""
echo "  2. Start the server:"
echo "     python assistant.py"
echo ""
echo "  3. Open index.html in your browser"
echo ""
echo "========================================"
