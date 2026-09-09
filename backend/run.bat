@echo off
REM Starts the Fabula API on http://127.0.0.1:8000  (interactive docs at /docs)
setlocal
cd /d "%~dp0"
set "PY=C:\Users\eiman\AppData\Local\Programs\python-embed-3.12\python.exe"
set "PYTHONIOENCODING=utf-8"
echo Fabula API -> http://127.0.0.1:8000     docs: http://127.0.0.1:8000/docs
echo Keep this window open. Close it (or Ctrl+C) to stop.
echo.
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo (api stopped)
pause
