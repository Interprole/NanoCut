@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\setup.ps1" %*
if errorlevel 1 (
  echo Setup stopped. Read the error above, then run Setup.cmd to retry.
  pause
  exit /b 1
)

