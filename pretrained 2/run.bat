@echo off
title SafeRoad AI Pretrained Analyzer
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo Backend Python environment not found: %PYTHON%
  echo Follow backend\README.md to install project dependencies.
  pause
  exit /b 1
)
cd /d "%~dp0"
"%PYTHON%" -m uvicorn app:app --host 127.0.0.1 --port 8001
