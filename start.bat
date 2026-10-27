@echo off
setlocal
title Bhu-Overlay - Bihar Cadastral Map & Satellite Dashboard
echo =====================================================================
echo    Bhu-Overlay - Bihar Cadastral Map & Satellite Dashboard
echo =====================================================================
echo.

cd /d "%~dp0bhu_overlay_lightweight"
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)

echo [*] Launching Bhu-Overlay server on http://127.0.0.1:5001...
start "" http://127.0.0.1:5001
"%PYTHON_CMD%" app.py

pause
