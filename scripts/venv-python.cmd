@echo off
REM Run a script with the repo venv (Windows cmd). Example:
REM   scripts\venv-python.cmd scripts\scan_historical_moves.py

setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo No .venv found. Run: powershell -ExecutionPolicy Bypass -File scripts\windows-install.ps1
  exit /b 1
)
set PYTHONPATH=%CD%
".venv\Scripts\python.exe" %*
