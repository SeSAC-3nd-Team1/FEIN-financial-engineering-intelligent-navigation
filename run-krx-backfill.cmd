@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-krx-backfill.ps1" %*
exit /b %ERRORLEVEL%
