@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV_DIR=%ROOT%venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%ROOT%requirements.txt"
set "READY_FLAG=%VENV_DIR%\.deps_installed"
set "FRONTEND_DIR=%ROOT%frontend"
set "NODE_MODULES=%ROOT%node_modules"
set "FRONTEND_OUT=%ROOT%app\static\react"

if not exist "%VENV_PY%" (
    echo Creating virtual environment...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

if not exist "%READY_FLAG%" (
    echo Installing dependencies...
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo Failed to upgrade pip.
        pause
        exit /b 1
    )

    "%VENV_PY%" -m pip install -r "%REQ_FILE%"
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )

    > "%READY_FLAG%" echo installed
)

if exist "%ROOT%package.json" (
    if not exist "%NODE_MODULES%" (
        echo Installing frontend dependencies...
        npm.cmd install
        if errorlevel 1 (
            echo Failed to install frontend dependencies.
            pause
            exit /b 1
        )
    )

    echo Building React frontend...
    npm.cmd run build
    if errorlevel 1 (
        echo Failed to build React frontend.
        pause
        exit /b 1
    )
)

if not exist "%ROOT%.env" (
    echo WARNING: .env not found. Copy .env.example to .env and fill in SECRET_KEY, GROQ_API_KEY, OPENROUTER_API_KEY first.
    pause
    exit /b 1
)

echo Starting Stash API...
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

pause
