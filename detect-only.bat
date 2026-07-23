@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0test-detection.ps1"
set "script_exit_code=%ERRORLEVEL%"
pause
exit /b %script_exit_code%
