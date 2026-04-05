@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Missing virtual environment at ".venv\Scripts\python.exe".
  echo Run install_or_update_stocknogs.bat first, or create the venv before starting the app.
  exit /b 1
)

echo Starting stocknogs...
echo GUI: automatic local port ^(tries 8080, 8090, 8100, 8180^)
echo Source: thinkorswim web persistent browser
echo.

".venv\Scripts\python.exe" "scripts\run_gui.py"

endlocal
