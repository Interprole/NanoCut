@echo off
setlocal
set "NC_BASE=%LOCALAPPDATA%\NanoCutRuntime"
set "PATH=%NC_BASE%\tools;%PATH%"
if not exist "%NC_BASE%\ready-v1" goto setup
if not exist "%NC_BASE%\python-path.txt" goto setup
set /p NC_PYDIR=<"%NC_BASE%\python-path.txt"
if exist "%NC_PYDIR%\pythonw.exe" goto launch
:setup
call "%~dp0Setup.cmd"
if errorlevel 1 exit /b 1
set /p NC_PYDIR=<"%NC_BASE%\python-path.txt"
:launch
start "" "%NC_PYDIR%\pythonw.exe" "%~dp0NanoCut.py"

