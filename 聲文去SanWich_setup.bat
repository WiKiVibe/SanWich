@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
title 聲文去SanWich - 一鍵安裝
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set "LOG=logs\setup.log"

echo ============================================================ > "%LOG%"
echo 聲文去SanWich 一鍵安裝 >> "%LOG%"
echo Started at %date% %time% >> "%LOG%"
echo Folder: %cd% >> "%LOG%"
echo ============================================================ >> "%LOG%"

echo.
echo ============================================================
echo   聲文去SanWich v1.0 - 一鍵安裝程式
echo   本程式會自動安裝所有需要的元件，請保持網路連線。
echo ============================================================
echo.
echo 安裝項目：
echo   1. Python 3.12（若尚未安裝）
echo   2. FFmpeg（音訊轉換工具）
echo   3. PyTorch + AI 模型套件
echo   4. 首次啟動後會自動下載語音模型（約 3-4 GB）
echo.
echo 整體安裝時間約 10-20 分鐘，請勿關閉此視窗。
echo.
pause

REM ------------------------------------------------------------
:: STEP 1：檢查並自動安裝 Python
REM ------------------------------------------------------------
echo.
echo [1/5] 檢查 Python...

set "PY_CMD="
set "PY_EXE="
py -3.12 --version > nul 2>&1
if not errorlevel 1 ( set "PY_CMD=py -3.12" & goto :FOUND_PY )
py -3.11 --version > nul 2>&1
if not errorlevel 1 ( set "PY_CMD=py -3.11" & goto :FOUND_PY )
py -3.10 --version > nul 2>&1
if not errorlevel 1 ( set "PY_CMD=py -3.10" & goto :FOUND_PY )
python -c "import sys; raise SystemExit(0 if (sys.version_info[:2] >= (3,10) and sys.version_info[:2] <= (3,12)) else 1)" > nul 2>&1
if %ERRORLEVEL% EQU 0 set "PY_CMD=python"

:FOUND_PY
if defined PY_CMD (
    echo     已找到 Python：
    %PY_CMD% --version
    goto :PYTHON_OK
)

:: 沒有 Python，自動下載安裝 Python 3.12
echo     未找到相容的 Python，正在自動下載 Python 3.12...
echo     下載來源：python.org 官方（約 25 MB）
echo.

set "PY_INSTALLER=%TEMP%\python312_installer.exe"
set "PY_URL=https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"

:: 使用 PowerShell 下載
powershell -NoProfile -Command "& {[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%'}" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     錯誤：Python 下載失敗，請手動安裝後重新執行。
    echo     下載位置：https://www.python.org/downloads/
    goto :END_FAIL
)

echo     正在安裝 Python 3.12（靜默安裝，請稍候）...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     錯誤：Python 安裝失敗，請手動安裝。
    goto :END_FAIL
)
del "%PY_INSTALLER%" > nul 2>&1

:: 重新整理環境變數（讓新安裝的 Python 生效）
for /f "tokens=*" %%A in ('powershell -NoProfile -Command "[System.Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "USER_PATH=%%A"
set "PATH=%PATH%;%USER_PATH%"

:: 再次確認
set "PY_CMD="
for /f "tokens=1,*" %%A in ('py -0p 2^>nul ^| findstr /r /c:"-V:3\.12"') do (
    set "PY_CMD="%%B""
    echo     Python 3.12 安裝完成。
    goto :PYTHON_OK
)
python -c "import sys; raise SystemExit(0 if (sys.version_info[:2] >= (3,10) and sys.version_info[:2] <= (3,12)) else 1)" > nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
    echo     Python 安裝完成。
    goto :PYTHON_OK
)

echo     錯誤：Python 安裝後仍無法找到，請重新開機後再執行此腳本。
goto :END_FAIL

:PYTHON_OK
echo     Python 準備完畢。
echo [PYTHON OK] >> "%LOG%"

REM ------------------------------------------------------------
:: STEP 2：檢查並自動下載 FFmpeg
REM ------------------------------------------------------------
echo.
echo [2/5] 檢查 FFmpeg...

where ffmpeg > nul 2>&1
if not errorlevel 1 (
    echo     已在 PATH 中找到 FFmpeg。
    goto :FFMPEG_OK
)
if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo     已找到 tools\ffmpeg\bin\ffmpeg.exe
    goto :FFMPEG_OK
)

:: 沒有 FFmpeg，自動下載
echo     未找到 FFmpeg，正在自動下載...
echo     下載來源：github.com/BtbN/FFmpeg-Builds（約 80 MB）
echo.

if not exist "tools\ffmpeg\bin" mkdir "tools\ffmpeg\bin"
set "FF_ZIP=%TEMP%\ffmpeg_win.zip"
set "FF_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

powershell -NoProfile -Command "& {[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%FF_URL%' -OutFile '%FF_ZIP%'}" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     錯誤：FFmpeg 下載失敗。
    echo     請手動下載後放到 tools\ffmpeg\bin\ffmpeg.exe
    echo     下載位置：https://ffmpeg.org/download.html
    echo     （非必要，可先略過，但部分音訊格式無法轉寫）
    goto :FFMPEG_SKIP
)

echo     正在解壓 FFmpeg...
set "FF_EXTRACT=%TEMP%\ffmpeg_extract"
powershell -NoProfile -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%FF_EXTRACT%' -Force" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     解壓失敗，跳過 FFmpeg 安裝。
    goto :FFMPEG_SKIP
)

:: 從解壓資料夾找 ffmpeg.exe 並複製過來
for /f "delims=" %%F in ('dir /s /b "%FF_EXTRACT%\ffmpeg.exe" 2^>nul') do (
    copy "%%F" "tools\ffmpeg\bin\ffmpeg.exe" > nul 2>&1
    goto :FF_COPY_DONE
)
:FF_COPY_DONE
del "%FF_ZIP%" > nul 2>&1
rd /s /q "%FF_EXTRACT%" > nul 2>&1

if exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo     FFmpeg 安裝完成。
    goto :FFMPEG_OK
) else (
    echo     FFmpeg 複製失敗，跳過。
)

:FFMPEG_SKIP
echo     警告：FFmpeg 未安裝，WAV 以外的音訊格式可能無法轉寫。
echo [FFMPEG SKIP] >> "%LOG%"
goto :VENV_START

:FFMPEG_OK
echo     FFmpeg 準備完畢。
echo [FFMPEG OK] >> "%LOG%"

REM ------------------------------------------------------------
:: STEP 3：建立虛擬環境
REM ------------------------------------------------------------
:VENV_START
echo.
echo [3/5] 建立 Python 虛擬環境...

if not exist ".venv\Scripts\python.exe" (
    %PY_CMD% -m venv .venv >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo     錯誤：虛擬環境建立失敗。
        goto :END_FAIL
    )
    echo     虛擬環境建立完成。
) else (
    echo     重用現有 .venv
)

set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1

REM ------------------------------------------------------------
:: STEP 4：偵測 GPU，安裝對應的 PyTorch
REM ------------------------------------------------------------
echo.
echo [4/5] 偵測顯示卡並安裝 PyTorch...

:: 預設保底：CPU 版（三層偵測都失敗時，至少裝得起來能跑）
set "TORCH_INDEX=https://download.pytorch.org/whl/cpu"
set "TORCH_LABEL=CPU"
set "HAS_NVIDIA=0"
set "GPU_NAME="
set "COMPUTE_CAP="
set "CC_MAJOR="

:: 先取得顯卡名稱，判斷有沒有 NVIDIA 卡
for /f "delims=" %%G in ('nvidia-smi --query-gpu^=name --format^=csv,noheader 2^>nul') do (
    if not defined GPU_NAME set "GPU_NAME=%%G"
    set "HAS_NVIDIA=1"
)

if "!HAS_NVIDIA!"=="0" (
    echo     未偵測到 NVIDIA 顯示卡，安裝 CPU 版 PyTorch...
    echo     （CPU 模式轉寫速度較慢，建議用於測試）
    goto :DO_TORCH_INSTALL
)

echo     偵測到 NVIDIA 顯示卡：!GPU_NAME!

:: 第一層：以 compute_cap 數值判斷架構（12.x = Blackwell -> cu128，其餘 -> cu121）
for /f "delims=" %%C in ('nvidia-smi --query-gpu^=compute_cap --format^=csv,noheader 2^>nul') do (
    if not defined COMPUTE_CAP set "COMPUTE_CAP=%%C"
)
if defined COMPUTE_CAP (
    for /f "tokens=1 delims=." %%M in ("!COMPUTE_CAP!") do set "CC_MAJOR=%%M"
)

if defined CC_MAJOR (
    echo     運算能力 compute_cap = !COMPUTE_CAP!
    if !CC_MAJOR! GEQ 12 (
        set "TORCH_INDEX=https://download.pytorch.org/whl/cu128"
        set "TORCH_LABEL=CUDA 12.8 Blackwell"
        echo     判斷為 Blackwell 架構，使用 CUDA 12.8 版 PyTorch...
    ) else (
        set "TORCH_INDEX=https://download.pytorch.org/whl/cu121"
        set "TORCH_LABEL=CUDA 12.1"
        echo     使用 CUDA 12.1 版 PyTorch...
    )
    goto :DO_TORCH_INSTALL
)

:: 第二層：compute_cap 取不到，退回以顯卡名稱判斷
echo     無法取得 compute_cap，改以顯卡名稱判斷...
echo !GPU_NAME! | findstr /i /c:"RTX 50" > nul
if not errorlevel 1 (
    set "TORCH_INDEX=https://download.pytorch.org/whl/cu128"
    set "TORCH_LABEL=CUDA 12.8 Blackwell"
    echo     名稱含 RTX 50 系列，使用 CUDA 12.8 版 PyTorch...
) else (
    set "TORCH_INDEX=https://download.pytorch.org/whl/cu121"
    set "TORCH_LABEL=CUDA 12.1"
    echo     使用 CUDA 12.1 版 PyTorch...
)

:DO_TORCH_INSTALL
echo     安裝 PyTorch（!TORCH_LABEL!），檔案較大約需 5-10 分鐘...
"%PY%" -m pip uninstall torch torchaudio torchvision -y >> "%LOG%" 2>&1
"%PY%" -m pip install torch torchaudio --index-url !TORCH_INDEX! >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     錯誤：PyTorch 安裝失敗，請查閱 %LOG%
    goto :END_FAIL
)

REM ------------------------------------------------------------
:: STEP 5：安裝其他套件
REM ------------------------------------------------------------
echo.
echo [5/5] 安裝 AI 套件（transformers / huggingface_hub 等）...

"%PY%" -m pip install --upgrade transformers accelerate safetensors numpy huggingface_hub jieba tkinterdnd2 customtkinter pillow sherpa-onnx >> "%LOG%" 2>&1
if errorlevel 1 (
    echo     錯誤：套件安裝失敗，請查閱 %LOG%
    goto :END_FAIL
)

REM ------------------------------------------------------------
:: 驗證
REM ------------------------------------------------------------
echo.
echo 驗證安裝結果...
"%PY%" -c "import torch; print('PyTorch:', torch.__version__); print('CUDA 可用:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '（使用 CPU）')"
"%PY%" -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())" >> "%LOG%" 2>&1

REM ------------------------------------------------------------
:: 完成，詢問是否立即啟動
REM ------------------------------------------------------------
echo.
echo ============================================================
echo   安裝完成！
echo ============================================================
echo.
echo 注意：第一次按「開始轉寫」時，程式會自動下載語音辨識模型
echo       （Breeze-ASR-25，約 3-4 GB），請保持網路連線並耐心等候。
echo       之後使用就不需要再下載。
echo.
echo 完整安裝日誌：%cd%\%LOG%
echo.
echo 即將自動啟動 聲文去SanWich...

set "APP_PY="
for %%F in ("%~dp0*SanWich*.py") do (
    set "APP_PY=%%~fF"
    goto :FOUND_APP
)

:FOUND_APP
if not defined APP_PY (
    echo 找不到主程式，請確認 聲文去SanWich.py 在同一資料夾。
    pause
    exit /b 1
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%APP_PY%"
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" "%APP_PY%"
) else (
    echo 找不到 Python 執行環境，請確認 .venv 已建立完成。
    pause
)

exit /b 0

REM ------------------------------------------------------------
:: 失敗處理
REM ------------------------------------------------------------
:END_FAIL
echo.
echo ============================================================
echo   安裝失敗
echo ============================================================
echo.
echo 請把以下檔案的內容傳給開發者協助排查：
echo   