@echo off
setlocal enabledelayedexpansion
title Industrial Knowledge Brain Launcher

rem Always work relative to this script's own location, not the caller's CWD.
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo =====================================================================
echo                 Industrial Knowledge Brain (IKB)
echo                      Launch and Setup Utility
echo =====================================================================
echo.

echo [1] Run via Docker Compose (Recommended - one command, bundles Neo4j)
echo [2] Run locally (Requires Python, Node.js, and npm installed)
echo [3] Exit
echo.
set /p choice=Select an option (1-3):

if "%choice%"=="1" goto docker
if "%choice%"=="2" goto local
if "%choice%"=="3" goto end
echo Invalid option.
goto end

:docker
if not exist "%ROOT%.env" (
    echo [INFO] Root .env not found. Creating from .env.example...
    copy "%ROOT%.env.example" "%ROOT%.env" >nul
    echo [WARN] Edit .env in the project root and set GEMINI_API_KEY, then re-run this script.
    goto end
)
findstr /C:"GEMINI_API_KEY=REPLACE_ME" "%ROOT%.env" >nul
if not errorlevel 1 (
    echo [WARN] GEMINI_API_KEY is still REPLACE_ME in .env - edit it before continuing.
    goto end
)
echo.
echo [INFO] Starting services via Docker Compose...
docker compose up --build
goto end

:local
if not exist "%ROOT%.env" (
    echo [INFO] Root .env not found. Creating from .env.example...
    copy "%ROOT%.env.example" "%ROOT%.env" >nul
    echo [WARN] Edit .env in the project root and set GEMINI_API_KEY before continuing.
    goto end
)
findstr /C:"GEMINI_API_KEY=REPLACE_ME" "%ROOT%.env" >nul
if not errorlevel 1 (
    echo [WARN] GEMINI_API_KEY is still REPLACE_ME in .env - edit it before continuing.
    goto end
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH. Install Python 3.11+ and re-run.
    goto end
)
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found on PATH. Install Node 20 LTS and re-run.
    goto end
)

echo [INFO] Installing backend dependencies (this can take a few minutes the first time)...
pushd "%ROOT%backend"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. See the error above.
    popd
    goto end
)
popd

echo [INFO] Launching backend in a new window (title: "IKB Backend")...
start "IKB Backend" cmd /k "cd /d "%ROOT%backend" && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo [INFO] Waiting a few seconds for the backend to boot...
timeout /t 5 /nobreak >nul

echo [INFO] Installing frontend dependencies (this can take a few minutes the first time)...
pushd "%ROOT%frontend"
call npm install
if errorlevel 1 (
    echo [ERROR] npm install failed. See the error above.
    popd
    goto end
)

echo [INFO] Launching frontend in a new window (title: "IKB Frontend")...
start "IKB Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"
popd

echo.
echo =====================================================================
echo   Backend and frontend are starting in their own windows:
echo     - "IKB Backend"  -^> http://localhost:8000/docs
echo     - "IKB Frontend" -^> http://localhost:5173
echo   Close those windows (or Ctrl+C inside them) to stop each service.
echo =====================================================================
goto end

:end
echo.
pause
