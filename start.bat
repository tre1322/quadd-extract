@echo off
echo ========================================
echo   Sports Stats Formatter - Startup
echo ========================================
echo.

REM Check if API key is set
if "%ANTHROPIC_API_KEY%"=="" (
    echo ERROR: ANTHROPIC_API_KEY is not set!
    echo.
    echo Please set it first:
    echo   set ANTHROPIC_API_KEY=your-key-here
    echo.
    pause
    exit /b 1
)

echo Starting API server...
echo.
echo Once started, open this URL in your browser:
echo   http://localhost:8000/app
echo.
echo Press Ctrl+C to stop the server
echo ========================================
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Start the server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
