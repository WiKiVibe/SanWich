@echo off
setlocal EnableDelayedExpansion
title SanWich INSTALL
cd /d "%~dp0"
if exist "app" cd app
set "LOG=%~dp0install_log.txt"
echo SanWich install started %date% %time% > "%LOG%"
echo working dir: %cd% >> "%LOG%"

echo ============================================================
echo   SanWich INSTALL  (KEEP THIS WINDOW OPEN)
echo   Working dir: %cd%
echo ============================================================
echo.

set "PYC="
for %%V in (3.12 3.11 3.10 3.13) do (
  if not defined PYC ( py -%%V --version >nul 2>&1 && set "PYC=py -%%V" )
)
if not defined PYC (
  echo [ERROR] Need Python 3.10-3.13. You appear to have 3.14 which PyTorch does not support.
  echo [ERROR] Install Python 3.12 ^(tick "Add python.exe to PATH"^), then run this again.
  echo no-python-3.10-3.13 >> "%LOG%"
  pause
  exit /b 1
)
echo Using !PYC!
!PYC! --version
echo using !PYC! >> "%LOG%"
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment .venv ...
  !PYC! -m venv .venv
  if errorlevel 1 ( echo [ERROR] venv creation failed & echo venv-fail >> "%LOG%" & pause & exit /b 1 )
)
set "PY=.venv\Scripts\python.exe"
echo venv-ok >> "%LOG%"

echo.
echo Upgrading pip ...
"%PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 ( echo [ERROR] pip upgrade failed & echo pip-fail >> "%LOG%" & pause & exit /b 1 )

set "TORCH=https://download.pytorch.org/whl/cpu"
nvidia-smi >nul 2>&1 && set "TORCH=https://download.pytorch.org/whl/cu121"
echo.
echo Installing PyTorch from !TORCH!  (this is large, may take 10+ min) ...
"%PY%" -m pip install torch torchaudio --index-url !TORCH!
if errorlevel 1 ( echo [ERROR] torch install failed & echo torch-fail >> "%LOG%" & pause & exit /b 1 )

echo.
echo Installing app packages (transformers, sherpa-onnx, etc.) ...
"%PY%" -m pip install --upgrade transformers accelerate safetensors numpy huggingface_hub jieba tkinterdnd2 customtkinter pillow sherpa-onnx
if errorlevel 1 ( echo [ERROR] package install failed & echo pkg-fail >> "%LOG%" & pause & exit /b 1 )

where ffmpeg >nul 2>&1 && goto FFOK
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto FFOK
echo.
echo Downloading FFmpeg ...
if not exist "tools\ffmpeg\bin" mkdir "tools\ffmpeg\bin"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;$ProgressPreference='SilentlyContinue';try{Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile '%TEMP%\ff.zip';exit 0}catch{exit 1}"
if errorlevel 1 ( echo [WARN] FFmpeg download failed; WAV still works & goto FFOK )
powershell -NoProfile -Command "Expand-Archive -Path '%TEMP%\ff.zip' -DestinationPath '%TEMP%\ffx' -Force"
for /f "delims=" %%F in ('dir /s /b "%TEMP%\ffx\ffmpeg.exe" 2^>nul') do ( copy "%%F" "tools\ffmpeg\bin\ffmpeg.exe" >nul 2>&1 & goto FFOK )
:FFOK
echo install-finished-OK >> "%LOG%"
echo.
echo ============================================================
echo   DONE. Go up one folder and run 02_launch.bat
echo   (or run app\run_debug.bat to see the app with a console)
echo ============================================================
pause
