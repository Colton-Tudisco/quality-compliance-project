@echo off
echo ========================================
echo   Quality Compliance Document Program
echo ========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
echo Checking dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting server...
echo Open your browser to: http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.

python app.py
pause