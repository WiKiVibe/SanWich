param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Release = Join-Path $Root "release"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Release, $LogDir | Out-Null
$Log = Join-Path $LogDir "build_main_zip.log"

"============================================================" | Set-Content -Encoding UTF8 $Log
"SanWich light package" | Add-Content -Encoding UTF8 $Log
"Started at $(Get-Date)" | Add-Content -Encoding UTF8 $Log
"Folder: $Root" | Add-Content -Encoding UTF8 $Log
"============================================================" | Add-Content -Encoding UTF8 $Log

function Write-CleanConfig {
    param([string] $Path)
    $cfg = [ordered]@{
        api_provider = "gemini"
        api_key = ""
        model = "gemini-2.5-flash"
        use_llm = $false
        use_text_fix = $false
        output_srt_enabled = $true
        output_txt_enabled = $true
    }
    $cfg | ConvertTo-Json | Set-Content -Encoding UTF8 $Path
}

function Copy-IfExists {
    param(
        [string] $Source,
        [string] $Destination
    )
    if (Test-Path -LiteralPath $Source) {
        $destDir = Split-Path -Parent $Destination
        if ($destDir) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

$MainPy = Get-ChildItem -LiteralPath $Root -Filter *.py |
    Where-Object { $_.Name -like '*SanWich*.py' -and $_.Name -notlike '*build*' } |
    Select-Object -First 1
$CorePy = Get-ChildItem -LiteralPath (Join-Path $Root 'core') -Filter *.py | Select-Object -First 1
$SetupBat = Get-ChildItem -LiteralPath $Root -Filter *.bat |
    Where-Object { $_.Name -like '*setup.bat' } |
    Select-Object -First 1
$ApiDoc = Get-ChildItem -LiteralPath $Root -Filter *.md |
    Where-Object { $_.Name -like '*API*Key*' } |
    Select-Object -First 1
$LogoIco = Join-Path $Root "assets\images\_LOGO.ico"
$LogoPng = Join-Path $Root "assets\images\_LOGO.png"
$SettingPng = Join-Path $Root "assets\images\_setting.png"
$SettingIco = Join-Path $Root "assets\images\_setting.ico"
$BubbleTeaPng = Join-Path $Root "assets\images\_Bubble-tea.png"
$WikiVibeQrPng = Join-Path $Root "assets\images\_portaly_wikivibe.png"
$PythonInstaller = Join-Path $Root "tools\python-3.12.9-amd64.exe"

$SetupTorch = Join-Path $Root "setup_torch.py"
if (!(Test-Path -LiteralPath $SetupTorch)) { throw "Missing required file: setup_torch.py" }
foreach ($item in @($MainPy, $CorePy, $SetupBat)) {
    if ($null -eq $item) {
        throw "Missing required source files for the main package."
    }
}
foreach ($path in @($LogoIco, $LogoPng, $SettingPng, $SettingIco, $BubbleTeaPng, $WikiVibeQrPng)) {
    if (!(Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}

Write-Host ""
Write-Host "Cleaning __pycache__ folders before staging..."
Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq '__pycache__' } |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
            Write-Host "  removed: $($_.FullName)"
        } catch {
            Write-Host "  skip:    $($_.FullName) ($($_.Exception.Message))"
        }
    }

$StageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("SanWich_main_build_" + [guid]::NewGuid().ToString("N"))
$Stage = Join-Path $StageRoot "SanWich"
$AppDir = Join-Path $Stage "app"
$AppAssets = Join-Path $AppDir "assets"
$AppCore = Join-Path $AppDir "core"
New-Item -ItemType Directory -Force -Path $Stage, $AppDir, $AppAssets, $AppCore | Out-Null

Copy-IfExists $MainPy.FullName (Join-Path $AppDir "SanWich.py")
Copy-IfExists (Join-Path $Root "core\SanWich_legacy_core.py") (Join-Path $AppCore "SanWich_legacy_core.py")
Copy-IfExists (Join-Path $Root "core\diarization.py") (Join-Path $AppCore "diarization.py")
Copy-IfExists (Join-Path $Root "core\personal_rules.py") (Join-Path $AppCore "personal_rules.py")
Copy-IfExists (Join-Path $Root "core\features.py") (Join-Path $AppCore "features.py")
Copy-IfExists (Join-Path $Root "core\license_manager.py") (Join-Path $AppCore "license_manager.py")
Copy-IfExists $SetupBat.FullName (Join-Path $AppDir "setup_internal.bat")
Copy-IfExists (Join-Path $Root "requirements.txt") (Join-Path $AppDir "requirements.txt")
Copy-IfExists $SetupTorch (Join-Path $AppDir "setup_torch.py")
Copy-IfExists (Join-Path $Root "core\models\diarization\seg-pyannote-segmentation-3.onnx") (Join-Path $AppCore "models\diarization\seg-pyannote-segmentation-3.onnx")
Copy-IfExists (Join-Path $Root "core\models\diarization\3dspeaker_eres2net_base_zh.onnx") (Join-Path $AppCore "models\diarization\3dspeaker_eres2net_base_zh.onnx")
Copy-IfExists (Join-Path $Root "download_diar_models.bat") (Join-Path $AppDir "download_diar_models.bat")
if (Test-Path -LiteralPath $ApiDoc) {
    Copy-IfExists $ApiDoc.FullName (Join-Path $AppDir $ApiDoc.Name)
}
if (Test-Path -LiteralPath $PythonInstaller) {
    Copy-IfExists $PythonInstaller (Join-Path $AppDir "tools\python-3.12.9-amd64.exe")
    Write-Host "Bundled Python installer: included"
    "Bundled Python installer: included" | Add-Content -Encoding UTF8 $Log
} else {
    Write-Host "Bundled Python installer: missing (setup will download Python if needed)"
    "Bundled Python installer: missing" | Add-Content -Encoding UTF8 $Log
}

Copy-IfExists $LogoIco (Join-Path $AppAssets "images\_LOGO.ico")
Copy-IfExists $LogoPng (Join-Path $AppAssets "images\_LOGO.png")
Copy-IfExists $SettingPng (Join-Path $AppAssets "images\_setting.png")
Copy-IfExists $SettingIco (Join-Path $AppAssets "images\_setting.ico")
Copy-IfExists $BubbleTeaPng (Join-Path $AppAssets "images\_Bubble-tea.png")
Copy-IfExists $WikiVibeQrPng (Join-Path $AppAssets "images\_portaly_wikivibe.png")

Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\NotoSansTC-VariableFont_wght.ttf") (Join-Path $AppAssets "fonts\Noto_Sans_TC\NotoSansTC-VariableFont_wght.ttf")
Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\README.txt") (Join-Path $AppAssets "fonts\Noto_Sans_TC\README.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\OFL.txt") (Join-Path $AppAssets "fonts\Noto_Sans_TC\OFL.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\TASAExplorer-VariableFont_wght.ttf") (Join-Path $AppAssets "fonts\TASA_Explorer\TASAExplorer-VariableFont_wght.ttf")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\README.txt") (Join-Path $AppAssets "fonts\TASA_Explorer\README.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\OFL.txt") (Join-Path $AppAssets "fonts\TASA_Explorer\OFL.txt")

Write-CleanConfig (Join-Path $AppDir "config.example.json")

$InternalRunText = @(
    '@echo off',
    'setlocal',
    'cd /d "%~dp0"',
    'if not exist "logs" mkdir "logs"',
    'set "PYTHON_EXE="',
    'if exist ".venv\Scripts\pythonw.exe" set "PYTHON_EXE=.venv\Scripts\pythonw.exe"',
    'if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"',
    'if not defined PYTHON_EXE (',
    '  echo Python runtime not found. Please run ..\01_setup.bat first.',
    '  echo.',
    '  echo Expected: .venv\Scripts\python.exe',
    '  pause',
    '  exit /b 1',
    ')',
    'set "APP_PY=SanWich.py"',
    'if exist "%APP_PY%" goto found_app',
    'set "APP_PY="',
    'for %%F in ("*SanWich*.py") do (',
    '  if exist "%%~fF" (',
    '    set "APP_PY=%%~fF"',
    '    goto found_app',
    '  )',
    ')',
    ':found_app',
    'if not defined APP_PY (',
    '  echo Main app file not found.',
    '  pause',
    '  exit /b 1',
    ')',
    '"%PYTHON_EXE%" "%APP_PY%" 1>"logs\main.log" 2>"logs\main_error.log"',
    'if errorlevel 1 (',
    '  echo.',
    '  echo SanWich failed. See app\logs\main_error.log',
    '  if exist "logs\main_error.log" type "logs\main_error.log"',
    '  echo.',
    '  pause',
    '  exit /b 1',
    ')',
    'exit /b 0'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $AppDir "run_app.bat") -Value $InternalRunText

$ShortcutScriptText = @'
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDir = Split-Path -Parent $AppDir
$Target = Join-Path $AppDir "run_app.bat"
$Icon = Join-Path $AppDir "assets\images\_LOGO.ico"

if (!(Test-Path -LiteralPath $Target)) {
    throw "Shortcut target not found: $Target"
}

$Shell = New-Object -ComObject WScript.Shell

function New-SanWichShortcut {
    param([string] $Path)

    $Shortcut = $Shell.CreateShortcut($Path)
    $Shortcut.TargetPath = $Target
    $Shortcut.WorkingDirectory = $AppDir
    $Shortcut.Description = "SanWich"
    if (Test-Path -LiteralPath $Icon) {
        $Shortcut.IconLocation = $Icon
    }
    $Shortcut.Save()
}

$Desktop = [Environment]::GetFolderPath("DesktopDirectory")
if ([string]::IsNullOrWhiteSpace($Desktop) -or !(Test-Path -LiteralPath $Desktop)) {
    $Desktop = $Shell.SpecialFolders.Item("Desktop")
}

New-SanWichShortcut (Join-Path $PackageDir "SanWich.lnk")
New-SanWichShortcut (Join-Path $Desktop "SanWich.lnk")

Write-Host "Shortcuts created:"
Write-Host "  $PackageDir\SanWich.lnk"
Write-Host "  $Desktop\SanWich.lnk"
'@
Set-Content -Encoding ASCII (Join-Path $AppDir "create_shortcuts.ps1") -Value $ShortcutScriptText

$InstallText = @(
    '@echo off',
    'setlocal',
    'cd /d "%~dp0"',
    'attrib +h "app" >nul 2>&1',
    'if exist "app\assets" attrib +h "app\assets" /s /d >nul 2>&1',
    'if exist "app\core" attrib +h "app\core" /s /d >nul 2>&1',
    'call "app\setup_internal.bat"'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $Stage "01_setup.bat") -Value $InstallText

$LaunchText = @(
    '@echo off',
    'setlocal',
    'cd /d "%~dp0"',
    'attrib +h "app" >nul 2>&1',
    'if exist "app\assets" attrib +h "app\assets" /s /d >nul 2>&1',
    'if exist "app\core" attrib +h "app\core" /s /d >nul 2>&1',
    'call "app\run_app.bat"'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $Stage "02_launch.bat") -Value $LaunchText

$ReadmeBase64 = "6IGy5paH5Y67U2FuV2ljaCDlronoo53ljIUNClNhbldpY2ggaW5zdGFsbGVyIHBhY2thZ2UNCg0K6KuL5YWI6Kej5aOT57iu5pW05YCL6LOH5paZ5aS+77yM5YaN5Z+36KGMIDAxX3NldHVwLmJhdOOAgg0KRXh0cmFjdCB0aGUgd2hvbGUgZm9sZGVyIGZpcnN0LCB0aGVuIHJ1biAwMV9zZXR1cC5iYXQuDQoNCuWuieijneWujOaIkOW+jO+8jOiri+W+nuahjOmdouaNt+W+keaIluacrOizh+aWmeWkvuWFp+eahCBTYW5XaWNoLmxuayDplovllZ/nqIvlvI/jgIINCkFmdGVyIHNldHVwIGZpbmlzaGVzLCBvcGVuIFNhbldpY2ggZnJvbSB0aGUgZGVza3RvcCBzaG9ydGN1dCBvciBTYW5XaWNoLmxuayBpbiB0aGlzIGZvbGRlci4NCg0KMDJfbGF1bmNoLmJhdCDku43kv53nlZnngrrlgpnnlKjllZ/li5XlmajjgIINCjAyX2xhdW5jaC5iYXQgaXMgc3RpbGwgaW5jbHVkZWQgYXMgYSBmYWxsYmFjayBsYXVuY2hlci4NCg0K6YCZ5YCL5a6J6KOd5YyF5LiN5YyF5ZCr5L2g55qEIEFQSSBLZXnjgIHlgIvkurroqK3lrprjgIHmqKHlnovlv6vlj5bmiJbmmqvlrZjmqpTjgIINClRoaXMgcGFja2FnZSBkb2VzIG5vdCBpbmNsdWRlIHlvdXIgQVBJIGtleSwgcGVyc29uYWwgY29uZmlnLCBtb2RlbCBjYWNoZSwgb3IgdGVtcCBmaWxlcy4NCg0K5aaC5p6c6Zu76IWm5rKS5pyJIFB5dGhvbu+8jOWuieijneeoi+W8j+acg+WEquWFiOS9v+eUqCBhcHBcdG9vbHNccHl0aG9uLTMuMTIuOS1hbWQ2NC5leGXjgIINCklmIFB5dGhvbiBpcyBub3QgaW5zdGFsbGVkLCBzZXR1cCBmaXJzdCB1c2VzIGFwcFx0b29sc1xweXRob24tMy4xMi45LWFtZDY0LmV4ZS4NCg0K5aaC5p6c5YyF5YWn5rKS5pyJIFB5dGhvbiDlronoo53mqpTvvIzlronoo53nqIvlvI/mnIPlvp4gcHl0aG9uLm9yZyDkuIvovInjgIINCklmIHRoZSBidW5kbGVkIFB5dGhvbiBpbnN0YWxsZXIgaXMgbWlzc2luZywgc2V0dXAgZG93bmxvYWRzIFB5dGhvbiBmcm9tIHB5dGhvbi5vcmcuDQoNCkZGbXBlZyDoiIfln7fooYzmiYDpnIDlpZfku7bmnIPlnKjlronoo53mmYLkvp3pnIDopoHkuIvovInjgIINCkZGbXBlZyBhbmQgcnVudGltZSBkZXBlbmRlbmNpZXMgd2lsbCBiZSBkb3dubG9hZGVkIGR1cmluZyBzZXR1cCB3aGVuIG5lZWRlZC4NCg0K56ys5LiA5qyh55yf5q2j6L2J5a+r5pmC5pyD5LiL6LyJIEJyZWV6ZS1BU1ItMjUg5qih5Z6L77yM57SEIDMtNCBHQuOAgg0KQnJlZXplLUFTUi0yNSB3aWxsIGRvd25sb2FkIG9uIHRoZSBmaXJzdCByZWFsIHRyYW5zY3JpcHRpb24sIGFib3V0IDMtNCBHQi4NCg0K5aaC5p6c6KaB5L2/55SoIEFJIOagoeWwje+8jOiri+WcqOioreWumumggeWhq+WFpeS9oOiHquW3seeahCBBUEkgS2V544CCDQpQdXQgeW91ciBvd24gQVBJIGtleSBpbiB0aGUgc2V0dGluZ3MgcGFnZSBpZiB5b3Ugd2FudCBBSSBwcm9vZnJlYWRpbmcuDQoNCmFwcCDos4fmlpnlpL7mmK/lhafpg6jmqpTmoYjvvIzkuIDoiKzkuI3pnIDopoHmiZPplovjgIINClRoZSBhcHAgZm9sZGVyIGNvbnRhaW5zIGludGVybmFsIGZpbGVzIGFuZCBub3JtYWxseSBkb2VzIG5vdCBuZWVkIHRvIGJlIG9wZW5lZC4="
[System.IO.File]::WriteAllText(
    (Join-Path $Stage "README.txt"),
    [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ReadmeBase64)),
    [System.Text.UTF8Encoding]::new($true)
)

$Zip = Join-Path $Release "SanWich_setup.zip"
if (Test-Path -LiteralPath $Zip) {
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Zip = Join-Path $Release "SanWich_setup_$Stamp.zip"
    "Existing SanWich_setup.zip found; writing $Zip instead." | Add-Content -Encoding UTF8 $Log
}
Compress-Archive -Path $Stage -DestinationPath $Zip

$Summary = [pscustomobject]@{
    ZipPath = $Zip
    ZipSizeMB = [math]::Round((Get-Item -LiteralPath $Zip).Length / 1MB, 2)
    BundledPythonInstaller = (Test-Path -LiteralPath $PythonInstaller)
}
$Summary | Format-List | Out-String | Add-Content -Encoding UTF8 $Log

try {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
} catch {
    "Warning: could not remove staging folder $StageRoot ($($_.Exception.Message))" | Add-Content -Encoding UTF8 $Log
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Done"
Write-Host "  ZIP: release\SanWich_setup.zip"
Write-Host "============================================================"
Write-Host ""
