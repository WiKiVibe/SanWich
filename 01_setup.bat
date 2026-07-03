@echo off
setlocal
cd /d "%~dp0"

set "SETUP_BAT="
for %%F in ("*SanWich_setup.bat") do (
  if exist "%%~fF" (
    set "SETUP_BAT=%%~fF"
    goto found_setup
  )
)

:found_setup
if not defined SETUP_BAT (
  echo SanWich setup script was not found.
  echo Expected a file matching: *SanWich_setup.bat
  pause
  exit /b 1
)

call "%SETUP_BAT%"
exit /b %ERRORLEVEL%
