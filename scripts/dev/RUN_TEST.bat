@echo off
setlocal
cd /d "%~dp0\..\.."

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] .venv\Scripts\python.exe not found.
  pause
  exit /b 1
)

set "APP=%CD%\SanWich.py"
if not exist "%APP%" (
  echo [ERROR] SanWich.py not found.
  pause
  exit /b 1
)

echo Launching: %APP%
echo If the window does not appear or crashes, the error will show below.
echo ------------------------------------------------------------

REM Disable auto-relaunch; run in this console so errors stay visible.
set "SANWICH_MAIN_RELAUNCHED=1"
"%PY%" "%APP%"

echo ------------------------------------------------------------
echo App exited. If there is a red error above, please screenshot it all.
pause
