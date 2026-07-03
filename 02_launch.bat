@echo off
cd /d "%~dp0"
if exist "app" cd app
set "PYW=.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=.venv\Scripts\python.exe"
if not exist "%PYW%" (
  echo Please run 01_setup.bat first.
  pause
  exit /b 1
)
set "APP="
for %%F in ("*SanWich*.py") do set "APP=%%~fF"
start "" "%PYW%" "%APP%"
