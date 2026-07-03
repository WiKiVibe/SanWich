param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Release = Join-Path $Root "release"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Release, $LogDir | Out-Null
$Log = Join-Path $LogDir "build_main_zip.log"

"============================================================" | Set-Content -Encoding UTF8 $Log
"聲文去SanWich light package" | Add-Content -Encoding UTF8 $Log
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

foreach ($item in @($MainPy, $CorePy, $SetupBat)) {
    if ($null -eq $item) {
        throw "Missing required source files for the main package."
    }
}
foreach ($path in @($LogoIco, $LogoPng, $SettingPng, $SettingIco)) {
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

Copy-IfExists $MainPy.FullName (Join-Path $AppDir $MainPy.Name)
Copy-IfExists $CorePy.FullName (Join-Path $AppCore "SanWich_legacy_core.py")
Copy-IfExists $SetupBat.FullName (Join-Path $AppDir "setup_internal.bat")
if (Test-Path -LiteralPath $ApiDoc) {
    Copy-IfExists $ApiDoc.FullName (Join-Path $AppDir $ApiDoc.Name)
}

Copy-IfExists $LogoIco (Join-Path $AppAssets "images\_LOGO.ico")
Copy-IfExists $LogoPng (Join-Path $AppAssets "images\_LOGO.png")
Copy-IfExists $SettingPng (Join-Path $AppAssets "images\_setting.png")
Copy-IfExists $SettingIco (Join-Path $AppAssets "images\_setting.ico")

Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\NotoSansTC-VariableFont_wght.ttf") (Join-Path $AppAssets "fonts\Noto_Sans_TC\NotoSansTC-VariableFont_wght.ttf")
Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\README.txt") (Join-Path $AppAssets "fonts\Noto_Sans_TC\README.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\Noto_Sans_TC\OFL.txt") (Join-Path $AppAssets "fonts\Noto_Sans_TC\OFL.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\TASAExplorer-VariableFont_wght.ttf") (Join-Path $AppAssets "fonts\TASA_Explorer\TASAExplorer-VariableFont_wght.ttf")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\README.txt") (Join-Path $AppAssets "fonts\TASA_Explorer\README.txt")
Copy-IfExists (Join-Path $Root "assets\fonts\TASA_Explorer\OFL.txt") (Join-Path $AppAssets "fonts\TASA_Explorer\OFL.txt")

Write-CleanConfig (Join-Path $AppDir "config.json")

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
    'set "APP_PY="',
    'for %%F in ("%~dp0*SanWich*.py") do (',
    '  set "APP_PY=%%~fF"',
    '  goto found_app',
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

$ReadmeText = @(
    'SanWich main light package',
    '',
    'Please follow this order:',
    '1. Run 01_setup.bat',
    '2. When setup is done, run 02_launch.bat',
    '',
    'Notes:',
    '- This package does not include your API key, personal config, model cache, or temp files.',
    '- Python, FFmpeg, and runtime dependencies will be downloaded during setup.',
    '- Breeze-ASR-25 will download on the first real transcription, about 3-4 GB.',
    '- Put your own API key in the settings page if you want AI proofreading.',
    '- The app folder contains internal files and normally does not need to be opened.'
) -join "`r`n"
Set-Content -Encoding UTF8 (Join-Path $Stage "README.txt") -Value $ReadmeText

$Zip = Join-Path $Release "SanWich_setup.zip"
if (Test-Path -LiteralPath $Zip) {
    Remove-Item -LiteralPath $Zip -Force
}
Compress-Archive -Path $Stage -DestinationPath $Zip

$Summary = [pscustomobject]@{
    ZipPath = $Zip
    ZipSizeMB = [math]::Round((Get-Item -LiteralPath $Zip).Length / 1MB, 2)
}
$Summary | Format-List | Out-String | Add-Content -Encoding UTF8 $Log

Remove-Item -LiteralPath $StageRoot -Recurse -Force

Write-Host ""
Write-Host "============================================================"
Write-Host "  Done"
Write-Host "  ZIP: release\SanWich_setup.zip"
Write-Host "============================================================"
Write-Host ""
