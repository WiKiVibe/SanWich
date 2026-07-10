@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SanWich setup
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set "LOG=logs\setup.log"

echo ============================================================ > "%LOG%"
echo SanWich setup >> "%LOG%"
echo Started at %date% %time% >> "%LOG%"
echo Folder: %cd% >> "%LOG%"
echo ============================================================ >> "%LOG%"

echo.
echo ============================================================
echo   SanWich setup
echo   This installer downloads and prepares the required runtime.
echo ============================================================
echo.
echo It will install or prepare:
echo   1. Python 3.12 if a compatible Python is not found
echo   2. FFmpeg for audio conversion
echo   3. A local Python virtual environment
echo   4. PyTorch and AI packages
echo.
echo This can take 10 to 20 minutes. Keep this window open.
echo.
pause

REM ------------------------------------------------------------
REM STEP 1: Find or install Python.
REM ------------------------------------------------------------
echo.
echo [1/5] Checking Python...

set "PY_CMD="
set "PY_INSTALLER=%TEMP%\python312_installer.exe"
set "BUNDLED_PY_INSTALLER=tools\python-3.12.9-amd64.exe"
set "PY_INSTALLER_IS_TEMP=0"
set "PY_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"

for %%V in (3.12 3.11 3.10 3.13) do (
    if not defined PY_CMD (
        py -%%V --version > nul 2>&1
        if not errorlevel 1 set "PY_CMD=py -%%V"
    )
)

if defined PY_CMD goto :PYTHON_OK

python -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if v >= (3,10) and v <= (3,13) else 1)" > nul 2>&1
if not errorlevel 1 set "PY_CMD=python"

if defined PY_CMD goto :PYTHON_OK

echo     Compatible Python was not found.
echo.

if exist "%BUNDLED_PY_INSTALLER%" (
    echo     Using bundled Python installer:
    echo     %BUNDLED_PY_INSTALLER%
    set "PY_INSTALLER=%BUNDLED_PY_INSTALLER%"
) else (
    echo     Bundled Python installer was not found.
    echo     Downloading Python 3.12 from python.org...
    echo     This file is about 25 MB.
    set "PY_INSTALLER_IS_TEMP=1"

    powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'; exit 0 } catch { exit 1 }" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo     [ERROR] Python download failed.
        echo     Please install Python 3.12 manually from:
        echo     https://www.python.org/downloads/
        goto :END_FAIL
    )
)

echo     Installing Python 3.12 silently...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0 >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     [ERROR] Python install failed.
    goto :END_FAIL
)
if "%PY_INSTALLER_IS_TEMP%"=="1" del "%PY_INSTALLER%" > nul 2>&1

for /f "tokens=*" %%A in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('PATH','User')"') do set "USER_PATH=%%A"
set "PATH=%PATH%;%USER_PATH%"

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PY_CMD="%LocalAppData%\Programs\Python\Python312\python.exe""
    goto :PYTHON_OK
)

py -3.12 --version > nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto :PYTHON_OK
)

python -c "import sys; v=sys.version_info[:2]; raise SystemExit(0 if v >= (3,10) and v <= (3,13) else 1)" > nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :PYTHON_OK
)

echo     [ERROR] Python was installed, but this window cannot find it yet.
echo     Restart Windows or open a new terminal, then run setup again.
goto :END_FAIL

:PYTHON_OK
echo     Using Python:
!PY_CMD! --version
echo [PYTHON OK] >> "%LOG%"

REM ------------------------------------------------------------
REM STEP 2: Find or download FFmpeg.
REM ------------------------------------------------------------
echo.
echo [2/5] Checking FFmpeg...

where ffmpeg > nul 2>&1
if not errorlevel 1 (
    echo     FFmpeg found in PATH.
    goto :FFMPEG_OK
)

if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo     FFmpeg found locally.
    goto :FFMPEG_OK
)

echo     FFmpeg was not found.
echo     Downloading FFmpeg from GitHub...
echo     This file is about 80 MB.
echo.

if not exist "tools\ffmpeg\bin" mkdir "tools\ffmpeg\bin"
set "FF_ZIP=%TEMP%\ffmpeg_win.zip"
set "FF_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
set "FF_EXTRACT=%TEMP%\ffmpeg_extract"

powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%FF_URL%' -OutFile '%FF_ZIP%'; exit 0 } catch { exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     [WARN] FFmpeg download failed.
    echo     WAV files should still work. Other audio formats may fail.
    goto :FFMPEG_SKIP
)

if exist "%FF_EXTRACT%" rd /s /q "%FF_EXTRACT%" > nul 2>&1
echo     Extracting FFmpeg...
powershell -NoProfile -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%FF_EXTRACT%' -Force" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     [WARN] FFmpeg extract failed.
    goto :FFMPEG_SKIP
)

for /f "delims=" %%F in ('dir /s /b "%FF_EXTRACT%\ffmpeg.exe" 2^>nul') do (
    copy "%%F" "tools\ffmpeg\bin\ffmpeg.exe" > nul 2>&1
    goto :FF_COPY_DONE
)

:FF_COPY_DONE
del "%FF_ZIP%" > nul 2>&1
rd /s /q "%FF_EXTRACT%" > nul 2>&1

if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo     FFmpeg is ready.
    goto :FFMPEG_OK
)

echo     [WARN] FFmpeg was not copied.

:FFMPEG_SKIP
echo     Continuing without FFmpeg.
echo [FFMPEG SKIP] >> "%LOG%"
goto :VENV_START

:FFMPEG_OK
echo [FFMPEG OK] >> "%LOG%"

REM ------------------------------------------------------------
REM STEP 3: Create the virtual environment.
REM ------------------------------------------------------------
:VENV_START
echo.
echo [3/5] Preparing Python virtual environment...

if not exist ".venv\Scripts\python.exe" (
    !PY_CMD! -m venv .venv >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo     [ERROR] Virtual environment creation failed.
        goto :END_FAIL
    )
    echo     Virtual environment created.
) else (
    echo     Reusing existing virtual environment.
)

set "PY=.venv\Scripts\python.exe"

echo     Upgrading pip tools...
"%PY%" -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     [ERROR] pip upgrade failed. See %LOG%
    goto :END_FAIL
)

REM ------------------------------------------------------------
REM STEP 4: Select and install PyTorch.
REM ------------------------------------------------------------
echo.
echo [4/5] Installing PyTorch...

REM GPU detection, CUDA build selection, cache purge, install and verify
REM all happen inside setup_torch.py (Python). Do NOT parse compute_cap or
REM pass index URLs through cmd - it mangles them (Playbook section 3).
set "SETUP_TOOLS_DIR=."
if exist "scripts\install\setup_torch.py" set "SETUP_TOOLS_DIR=scripts\install"
if not exist "%SETUP_TOOLS_DIR%\setup_torch.py" (
    echo     [ERROR] setup_torch.py is missing.
    goto :END_FAIL
)
echo     This download is large and may take several minutes.
echo [TORCH via setup_torch.py] >> "%LOG%"
"%PY%" "%SETUP_TOOLS_DIR%\setup_torch.py"
if errorlevel 1 (
    echo     [ERROR] PyTorch install failed. See gpu_detect_log.txt
    goto :END_FAIL
)

REM ------------------------------------------------------------
REM STEP 5: Install app packages.
REM ------------------------------------------------------------
echo.
echo [5/5] Installing app packages...

"%PY%" -m pip install --upgrade transformers accelerate safetensors numpy huggingface_hub jieba tkinterdnd2 customtkinter pillow sherpa-onnx >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     [ERROR] Package install failed. See %LOG%
    goto :END_FAIL
)

REM ------------------------------------------------------------
REM Verify and launch.
REM ------------------------------------------------------------
echo.
echo Verifying install...
"%PY%" -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
"%PY%" -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())" >> "%LOG%" 2>&1

echo.
echo Creating shortcuts...
set "SHORTCUT_SCRIPT=create_shortcuts.ps1"
if exist "scripts\install\create_shortcuts.ps1" set "SHORTCUT_SCRIPT=scripts\install\create_shortcuts.ps1"
if exist "%SHORTCUT_SCRIPT%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SHORTCUT_SCRIPT%" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo     [WARN] Shortcut creation failed. See %LOG%
        echo [SHORTCUT WARN] >> "%LOG%"
    ) else (
        echo     Desktop and folder shortcuts are ready.
        echo [SHORTCUT OK] >> "%LOG%"
    )
) else (
    echo     [WARN] Shortcut script was not found.
    echo [SHORTCUT SCRIPT MISSING] >> "%LOG%"
)

echo.
echo ============================================================
echo   Setup finished
echo ============================================================
echo.
echo First transcription will download the speech model.
echo The model is about 3 to 4 GB.
echo Log file: %cd%\%LOG%
echo.
echo Starting SanWich...

set "APP_PY=SanWich.py"
if exist "%APP_PY%" goto :FOUND_APP

set "APP_PY="
for %%F in ("*SanWich*.py") do (
    if exist "%%~fF" (
        set "APP_PY=%%~fF"
        goto :FOUND_APP
    )
)

:FOUND_APP
if not defined APP_PY (
    echo [ERROR] Main app file was not found.
    pause
    exit /b 1
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%APP_PY%"
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" "%APP_PY%"
) else (
    echo [ERROR] Python runtime was not found in .venv.
    pause
    exit /b 1
)

exit /b 0

REM ------------------------------------------------------------
REM Failure handling.
REM ------------------------------------------------------------
:END_FAIL
echo.
echo ============================================================
echo   SETUP FAILED
echo ============================================================
echo.
echo See this log file:
echo %cd%\%LOG%
echo.
echo Press any key to close this window.
pause > nul
exit /b 1
