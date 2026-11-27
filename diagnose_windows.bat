@echo off
setlocal
cd /d "%~dp0"
title NoMouse - Diagnostics

if not exist ".venv\Scripts\python.exe" (
  echo NoMouse is not set up yet. Run install_windows.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" tools\diagnose.py
pause
