@echo off
setlocal

set "SCRIPT_URL=https://raw.githubusercontent.com/seeeeeeeeeeeeek/final/main/install_or_update_stocknogs.ps1"
set "TEMP_SCRIPT=%TEMP%\stocknogs_install_or_update.ps1"

echo [stocknogs] Downloading latest installer/update script...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%SCRIPT_URL%' -OutFile '%TEMP_SCRIPT%'" 
if errorlevel 1 (
  echo [stocknogs] Failed to download the installer script from GitHub.
  pause
  exit /b 1
)

echo [stocknogs] Running installer/update script...
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

del "%TEMP_SCRIPT%" >nul 2>nul

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [stocknogs] Update failed with exit code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
