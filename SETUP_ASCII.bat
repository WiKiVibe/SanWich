@echo off
setlocal EnableDelayedExpansion
title SanWich setup (ASCII)
cd /d "%~dp0"
if exist "app" cd app

echo ============================================================
echo   SanWich setup
echo   Working dir: %cd%
echo ============================================================
echo.

REM ---- find a usable Python 3.10-3.13 (3.14 is too new for PyTorch) ----
set "PYC="
for %%V in (3.12 3.11 3.10 3.13) do (
  if not defined PYC ( py -%%V --version >nul 2>&1 && set "PYC=py -%%V" )
)
if not defined PYC (
  echo [ERROR] Need Python 3.10-3.13. None found via the 'py' launcher.
  echo Your default Python is likely 3.14, which PyTorch does not support yet.
  echo Please install Python 3.12 from https://www.python.org/downloads/release/python-3129/
  echo (tick "Add python.exe to PATH"), then run this again.
  pause
  exit /b 1
)
echo Using Python: !PYC!
!PYC! --version
echo.

REM ---- create venv ----
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  !PYC! -m venv .venv
  if errorlevel 1 ( echo [ERROR] venv creation failed & pause & exit /b 1 )
) else (
  echo Reusing existing .venv
)
set "PY=.venv\Scripts\python.exe"

echo.
echo Upgrading pip ...
"%PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 ( echo [ERROR] pip upgrade failed & pause & exit /b 1 )

REM ---- PyTorch: detection + install + verify via setup_torch.py ----
echo.
echo Installing PyTorch via setup_torch.py (the big one, please wait) ...
"%PY%" setup_torch.py
if errorlevel 1 ( echo [ERROR] torch install failed & pause & exit /b 1 )

echo.
echo Installing app packages (transformers, sherpa-onnx, etc.) ...
"%PY%" -m pip install --upgrade transformers accelerate safetensors numpy huggingface_hub jieba tkinterdnd2 customtkinter pillow sherpa-onnx
if errorlevel 1 ( echo [ERROR] package install failed & pause & exit /b 1 )

REM ---- FFmpeg (needed for audio conversion) ----
where ffmpeg >nul 2>&1 && ( echo FFmpeg found in PATH & goto FFDONE )
if exist "tools\ffmpeg\bin\ffmpeg.exe" ( echo FFmpeg found locally & goto FFDONE )
echo.
echo Downloading FFmpeg ...
if not exist "tools\ffmpeg\bin" mkdir "tools\ffmpeg\bin"
set "FFZIP=%TEMP%\ffmpeg_win.zip"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; try{Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile '%FFZIP%'; exit 0}catch{exit 1}"
if errorlevel 1 ( echo [WARN] FFmpeg download failed; WAV should still work & goto FFDONE )
set "FFX=%TEMP%\ffmpeg_x"
powershell -NoProfile -Command "Expand-Archive -Path '%FFZIP%' -DestinationPath '%FFX%' -Force"
for /f "delims=" %%F in ('dir /s /b "%FFX%\ffmpeg.exe" 2^>nul') do ( copy "%%F" "tools\ffmpeg\bin\ffmpeg.exe" >nul 2>&1 & goto FFCOPIED )
:FFCOPIED
del "%FFZIP%" >nul 2>&1
rd /s /q "%FFX%" >nul 2>&1
:FFDONE

echo.
echo ============================================================
echo   Setup finished.
echo   Next: go back up one folder and run 02_launch.bat
echo   (or run app\run_debug.bat to see errors in a console)
echo ============================================================
pause
