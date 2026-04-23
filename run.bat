@echo off
echo ========================================
echo   Comply — Compliance Management System
echo   Schlegel Electronic Materials
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://www.python.org
    pause & exit /b 1
)

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting Comply...
echo Open your browser to: http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.

python app.py
pause
