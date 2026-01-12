@echo off
REM =============================================================================
REM MINI-MIND START SCRIPT (Windows)
REM =============================================================================
REM Double-click this file to start Clear!
REM =============================================================================

echo ========================================
echo    Starting Clear...
echo ========================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the server
python assistant.py
