@echo off
chcp 65001 >nul
fltmc >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo Requesting administrator permission so the game can receive mouse input...
    powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
set "script_exit_code=%ERRORLEVEL%"
if not "%script_exit_code%"=="0" pause
exit /b %script_exit_code%
