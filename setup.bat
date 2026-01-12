@echo off
REM =============================================================================
REM MINI-MIND SETUP SCRIPT (Windows)
REM =============================================================================
REM This script installs all dependencies needed to run Clear.
REM
REM Usage: Double-click this file or run: setup.bat
REM
REM What it does:
REM   1. Creates a virtual environment (isolated Python environment)
REM   2. Installs required Python packages
REM   3. Tells you how to start the app
REM =============================================================================

echo ========================================
echo         Clear Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo X Python is not installed!
    echo Please install Python 3.8+ from https://python.org
    echo Make sure to check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

echo [OK] Found Python
python --version
echo.

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install required packages
echo.
echo Installing dependencies...
echo    - FastAPI (web framework)
echo    - Uvicorn (ASGI server)
echo    - Pydantic (data validation)
echo    - dateparser (natural language dates)
echo.

pip install fastapi uvicorn pydantic dateparser

echo.
echo ========================================
echo       Setup Complete!
echo ========================================
echo.
echo To start Clear:
echo.
echo   1. Run: start.bat
echo      (or manually: venv\Scripts\activate then python assistant.py)
echo.
echo   2. Open index.html in your browser
echo.
echo ========================================
pause
