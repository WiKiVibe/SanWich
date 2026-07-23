$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "setup.log"
"SanWich setup started at $(Get-Date -Format o)" | Set-Content -LiteralPath $Log -Encoding UTF8

function Test-PythonCandidate {
    param([string] $Exe, [string[]] $Prefix = @())
    try {
        & $Exe @Prefix -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-PythonCandidate {
    foreach ($version in @("3.12", "3.11", "3.10", "3.13")) {
        if (Test-PythonCandidate "py.exe" @("-$version")) {
            return [pscustomobject]@{ Exe = "py.exe"; Prefix = @("-$version") }
        }
    }
    if (Test-PythonCandidate "python.exe") {
        return [pscustomobject]@{ Exe = "python.exe"; Prefix = @() }
    }
    $known = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if ((Test-Path -LiteralPath $known) -and (Test-PythonCandidate $known)) {
        return [pscustomobject]@{ Exe = $known; Prefix = @() }
    }
    return $null
}

Write-Host ""
Write-Host "SanWich 安裝程式"
Write-Host "將準備 Python、FFmpeg、PyTorch 與必要套件，約需 10 到 20 分鐘。"
if ($env:SANWICH_SETUP_TEST -ne "1") { [void](Read-Host "按 Enter 開始") }

$Python = Find-PythonCandidate
if ($null -eq $Python) {
    $bundled = Join-Path $Root "tools\python-3.12.9-amd64.exe"
    $installer = $bundled
    $downloadedInstaller = $false
    if (!(Test-Path -LiteralPath $installer)) {
        $installer = Join-Path $env:TEMP "SanWich_python312_installer.exe"
        Write-Host "正在從 python.org 下載 Python 3.12…"
        Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe" -OutFile $installer -UseBasicParsing
        $downloadedInstaller = $true
    }
    Write-Host "正在安裝 Python 3.12…"
    $process = Start-Process -FilePath $installer -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1", "Include_launcher=1", "Include_test=0"
    ) -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "Python 安裝失敗，代碼 $($process.ExitCode)。" }
    if ($downloadedInstaller) { Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue }
    $Python = Find-PythonCandidate
    if ($null -eq $Python) { throw "Python 已安裝，但目前程序仍找不到 Python。請重新開機後再執行安裝。" }
}

Write-Host "正在檢查 FFmpeg…"
$localFfmpeg = Join-Path $Root "tools\ffmpeg\bin\ffmpeg.exe"
if (!(Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -and !(Test-Path -LiteralPath $localFfmpeg)) {
    try {
        $ffZip = Join-Path $env:TEMP "SanWich_ffmpeg_win.zip"
        $ffExtract = Join-Path $env:TEMP "SanWich_ffmpeg_extract"
        Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile $ffZip -UseBasicParsing
        if (Test-Path -LiteralPath $ffExtract) {
            $resolvedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
            $resolvedExtract = [IO.Path]::GetFullPath($ffExtract)
            if (!$resolvedExtract.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) { throw "不安全的暫存路徑。" }
            Remove-Item -LiteralPath $ffExtract -Recurse -Force
        }
        Expand-Archive -LiteralPath $ffZip -DestinationPath $ffExtract -Force
        $candidate = Get-ChildItem -LiteralPath $ffExtract -Filter ffmpeg.exe -Recurse -File | Select-Object -First 1
        if ($null -ne $candidate) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $localFfmpeg) | Out-Null
            Copy-Item -LiteralPath $candidate.FullName -Destination $localFfmpeg -Force
        }
        Remove-Item -LiteralPath $ffZip -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "FFmpeg 下載失敗；WAV 仍可使用，其他格式可能無法轉換。"
        $_ | Out-String | Add-Content -LiteralPath $Log -Encoding UTF8
    }
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $VenvPython)) {
    Write-Host "正在建立 Python 虛擬環境…"
    & $Python.Exe @($Python.Prefix) -m venv (Join-Path $Root ".venv") *>> $Log
    if ($LASTEXITCODE -ne 0) { throw "虛擬環境建立失敗，請查看 $Log。" }
}

& $VenvPython -m pip install --upgrade pip setuptools wheel *>> $Log
if ($LASTEXITCODE -ne 0) { throw "pip 更新失敗，請查看 $Log。" }

$TorchSetup = if (Test-Path -LiteralPath (Join-Path $Root "scripts\install\setup_torch.py")) {
    Join-Path $Root "scripts\install\setup_torch.py"
} else { Join-Path $Root "setup_torch.py" }
if (!(Test-Path -LiteralPath $TorchSetup)) { throw "找不到 setup_torch.py。" }
Write-Host "正在安裝適合這台電腦的 PyTorch…"
& $VenvPython $TorchSetup
if ($LASTEXITCODE -ne 0) { throw "PyTorch 安裝失敗，請查看 gpu_detect_log.txt。" }

$Requirements = Join-Path $Root "requirements.txt"
if (!(Test-Path -LiteralPath $Requirements)) { throw "找不到 requirements.txt。" }
Write-Host "正在安裝 SanWich 套件…"
& $VenvPython -m pip install --upgrade -r $Requirements *>> $Log
if ($LASTEXITCODE -ne 0) { throw "套件安裝失敗，請查看 $Log。" }

& $VenvPython -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"

if ($env:SANWICH_SETUP_TEST -ne "1") {
    $shortcut = if (Test-Path -LiteralPath (Join-Path $Root "scripts\install\create_shortcuts.ps1")) {
        Join-Path $Root "scripts\install\create_shortcuts.ps1"
    } else { Join-Path $Root "create_shortcuts.ps1" }
    if (Test-Path -LiteralPath $shortcut) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $shortcut }
}

Write-Host ""
Write-Host "SanWich 安裝完成。第一次轉寫會另外下載語音模型。"
if ($env:SANWICH_SETUP_TEST -ne "1") {
    $launcher = Join-Path $Root "02_launch.ps1"
    if (!(Test-Path -LiteralPath $launcher)) { $launcher = Join-Path $Root "run_app.ps1" }
    if (Test-Path -LiteralPath $launcher) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher }
}
