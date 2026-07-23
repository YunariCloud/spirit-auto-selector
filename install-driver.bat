@echo off
chcp 65001 >nul
fltmc >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo Requesting administrator permission to install Interception driver...
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" install_driver.py
) else (
    python install_driver.py
)

pause
exit /b %ERRORLEVEL%
