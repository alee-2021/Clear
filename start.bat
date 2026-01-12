@echo off
REM =============================================================================
REM MINI-MIND START SCRIPT (Windows)
REM =============================================================================
REM Double-click this file to start Mini-Mind!
REM =============================================================================

echo ========================================
echo    Starting Mini-Mind...
echo ========================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the server
python assistant.py
