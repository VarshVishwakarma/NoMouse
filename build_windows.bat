@echo off
setlocal
cd /d "%~dp0"
title NoMouse - Build

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Install the development environment first.
  echo Run install_windows.bat, then:
  echo .venv\Scripts\python.exe -m pip install PyInstaller
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install PyInstaller
if errorlevel 1 goto failed

".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm nomouse.spec
if errorlevel 1 goto failed

if not exist "dist\NoMouse\_internal\nomouse\models\hand_landmarker.task" (
  echo ERROR: The bundled hand-tracking model is missing from the build.
  goto failed
)

echo.
echo Build complete: dist\NoMouse\NoMouse.exe
echo This build has not been tested on another computer.
pause
exit /b 0

:failed
echo.
echo Build failed. Read the error above before distributing an artifact.
pause
exit /b 1
