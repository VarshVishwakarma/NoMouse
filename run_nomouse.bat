@echo off
setlocal
cd /d "%~dp0"
title NoMouse

if not exist ".venv\Scripts\python.exe" (
  echo NoMouse is not set up yet.
  echo Double-click install_windows.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" main.py %*
if errorlevel 1 (
  echo.
  echo NoMouse stopped with an error. Read the message above, or run diagnose_windows.bat.
  pause
)
