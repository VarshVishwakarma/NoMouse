@echo off
setlocal
cd /d "%~dp0"
title NoMouse - Setup

echo ========================================
echo  NoMouse - Windows Setup
echo ========================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python Launcher ^(py^) was not found.
  echo Install Python 3.11 64-bit from https://www.python.org/downloads/release/python-3119/
  echo Then run this file again.
  pause
  exit /b 1
)

py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.11 was not found.
  echo Install Python 3.11 64-bit, then run this file again.
  pause
  exit /b 1
)

py -3.11 -c "import struct, sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.11 is installed as a 32-bit build, but MediaPipe needs 64-bit.
  echo Install the 64-bit version of Python 3.11, then run this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3.11 -m venv .venv
  if errorlevel 1 goto failed
)

echo Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed

echo Installing NoMouse dependencies ^(this can take a few minutes^)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo Setup complete. Double-click run_nomouse.bat to start NoMouse.
pause
exit /b 0

:failed
echo.
echo SETUP FAILED. Read the error above, then run diagnose_windows.bat for environment details.
pause
exit /b 1
