@echo off
echo ================================================================================
echo Universal Document Learning - Web UI
echo ================================================================================
echo.

REM Check if ANTHROPIC_API_KEY is set
if "%ANTHROPIC_API_KEY%"=="" (
    echo [ERROR] ANTHROPIC_API_KEY environment variable is not set!
    echo.
    echo Please set it first:
    echo   set ANTHROPIC_API_KEY=sk-ant-api03-...
    echo.
    echo Or add it to your .env file.
    echo.
    pause
    exit /b 1
)

echo [OK] ANTHROPIC_API_KEY is set: %ANTHROPIC_API_KEY:~0,15%...
echo.

echo Starting FastAPI server...
echo.
echo The web UI will be available at:
echo   http://localhost:8000/app
echo.
echo Press Ctrl+C to stop the server.
echo.
echo ================================================================================
echo.

python -m src.api.main
