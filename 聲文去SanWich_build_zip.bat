@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

rem Find build_zip ps1 in this folder (matches Chinese filename via wildcard).
set "PS1="
for %%F in ("*build_zip*.ps1") do (
  set "PS1=%%~fF"
  goto run
)

echo [ERROR] Cannot find *build_zip*.ps1 in this folder.
echo Folder: %CD%
goto end

:run
echo Running: %PS1%
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo [OK] Build finished. ZIP should be in release\
) else (
  echo [FAIL] PowerShell exit code: %RC%
)

:end
echo.
echo (Press any key to close)
pause >nul
