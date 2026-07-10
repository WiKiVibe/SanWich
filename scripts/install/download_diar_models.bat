@echo off
setlocal
rem Release-packaging helper; normally invoked from the packaged app folder.
cd /d "%~dp0"
chcp 437 > nul
set "DEST=_diar_candidates"
if not exist "%DEST%" mkdir "%DEST%"

echo ============================================================
echo   SanWich - download speaker embedding candidate models
echo   Saving into: %CD%\%DEST%
echo   This may take a few minutes.
echo ============================================================
echo.

call :get "3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx" "eres2netv2.onnx"
call :get "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" "eres2net_base.onnx"
call :get "wespeaker_zh_cnceleb_resnet34_LM.onnx" "wespeaker_resnet34.onnx"

echo.
echo ------------------------------------------------------------
echo Done. Files in %CD%\%DEST% :
dir /b "%DEST%"
echo ------------------------------------------------------------
pause
exit /b 0

:get
set "URL=https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/%~1"
echo Downloading %~2 ...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%URL%' -OutFile '%DEST%\%~2'; exit 0 } catch { exit 1 }"
if errorlevel 1 (echo   FAILED: %~2) else (echo   OK: %~2)
echo.
exit /b 0
