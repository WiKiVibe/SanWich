param()

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root

$Release = Join-Path $Root "release"
$LogDir = Join-Path $Root "logs"
$ForbiddenPackageDirectories = @("test_footage")
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
        api_provider = "local"
        api_key = ""
        model = "Breeze-7B-Instruct v1.0 (Local Q4_K_M)"
        use_llm = $false
        use_text_fix = $true
        txt_diarization_enabled = $false
        srt_diarization_enabled = $false
        diarization_num_speakers = 3
        srt_max_chars_per_line = ""
        output_srt_enabled = $true
        output_txt_enabled = $false
        use_personal_rules = $true
        personal_rules_domain = "通用"
        use_domain_prompt = $true
        prompt_template_domain = "通用"
        use_custom_dictionary = $true
        use_project_context = $true
        license_product_id = "sanwich"
        license_api_base_url = "https://wikivibe-license-server.wikivibe.workers.dev"
        license_issuer = "https://wikivibe-license-server.wikivibe.workers.dev"
        license_public_key_spki = "MCowBQYDK2VwAyEAkSWQwsY0BGQ5CUYgTuY8cy3VyF1L5a-_3o4mRnVb9rU"
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

$MainPy = Get-Item -LiteralPath (Join-Path $Root 'SanWich.py')
$CorePy = Get-ChildItem -LiteralPath (Join-Path $Root 'core') -Filter *.py | Select-Object -First 1
$AudioPreviewPy = Get-Item -LiteralPath (Join-Path $Root 'core\audio_preview.py')
$LocalLlmPy = Get-Item -LiteralPath (Join-Path $Root 'core\local_llm.py')
$SetupPs1 = Get-Item -LiteralPath (Join-Path $Root '01_setup.ps1')
$LaunchPs1 = Get-Item -LiteralPath (Join-Path $Root '02_launch.ps1')
$ApiDoc = Get-ChildItem -LiteralPath (Join-Path $Root 'docs') -Filter '*.md' |
    Where-Object { $_.Name -like '*API*Key*' } |
    Select-Object -First 1 -ExpandProperty FullName
$LogoIco = Join-Path $Root "assets\images\_LOGO.ico"
$LogoPng = Join-Path $Root "assets\images\_LOGO.png"
$SettingPng = Join-Path $Root "assets\images\_setting.png"
$SettingIco = Join-Path $Root "assets\images\_setting.ico"
$BubbleTeaPng = Join-Path $Root "assets\images\_Bubble-tea.png"
$WikiVibeQrPng = Join-Path $Root "assets\images\_portaly_wikivibe.png"
$PythonInstaller = Join-Path $Root "tools\python-3.12.9-amd64.exe"

$SetupTorch = Join-Path $Root "scripts\install\setup_torch.py"
if (!(Test-Path -LiteralPath $SetupTorch)) { throw "Missing required file: setup_torch.py" }
foreach ($item in @($MainPy, $CorePy, $AudioPreviewPy, $LocalLlmPy, $SetupPs1, $LaunchPs1)) {
    if ($null -eq $item) {
        throw "Missing required source files for the main package."
    }
}
$VersionMatch = [regex]::Match(
    (Get-Content -LiteralPath $MainPy.FullName -Raw -Encoding UTF8),
    'APP_VERSION\s*=\s*"([^"]+)"'
)
if (!$VersionMatch.Success) {
    throw "Cannot determine APP_VERSION from $($MainPy.FullName)."
}
$AppVersion = $VersionMatch.Groups[1].Value
foreach ($path in @($LogoIco, $LogoPng, $SettingPng, $SettingIco, $BubbleTeaPng, $WikiVibeQrPng)) {
    if (!(Test-Path -LiteralPath $path)) {
        throw "Missing required file: $path"
    }
}

Write-Host ""
Write-Host "Cleaning __pycache__ folders before staging..."
Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq '__pycache__' -and
        $_.FullName -notlike (Join-Path $Root '.venv\*')
    } |
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
Copy-IfExists (Join-Path $Root "core\learning.py") (Join-Path $AppCore "learning.py")
Copy-IfExists (Join-Path $Root "core\prompt_templates.py") (Join-Path $AppCore "prompt_templates.py")
Copy-IfExists (Join-Path $Root "core\experiments.py") (Join-Path $AppCore "experiments.py")
Copy-IfExists (Join-Path $Root "core\features.py") (Join-Path $AppCore "features.py")
Copy-IfExists (Join-Path $Root "core\license_manager.py") (Join-Path $AppCore "license_manager.py")
Copy-IfExists (Join-Path $Root "core\license_service.py") (Join-Path $AppCore "license_service.py")
Copy-IfExists (Join-Path $Root "core\updater.py") (Join-Path $AppCore "updater.py")
Copy-IfExists (Join-Path $Root "core\audio_preview.py") (Join-Path $AppCore "audio_preview.py")
Copy-IfExists (Join-Path $Root "core\local_llm.py") (Join-Path $AppCore "local_llm.py")
Copy-IfExists $SetupPs1.FullName (Join-Path $AppDir "setup_internal.ps1")
Copy-IfExists $LaunchPs1.FullName (Join-Path $AppDir "run_app.ps1")
Copy-IfExists (Join-Path $Root "requirements.txt") (Join-Path $AppDir "requirements.txt")
Copy-IfExists $SetupTorch (Join-Path $AppDir "setup_torch.py")
Copy-IfExists (Join-Path $Root "scripts\update\apply_update.ps1") (Join-Path $AppDir "update_helper.ps1")
Copy-IfExists (Join-Path $Root "core\models\diarization\seg-pyannote-segmentation-3.onnx") (Join-Path $AppCore "models\diarization\seg-pyannote-segmentation-3.onnx")
Copy-IfExists (Join-Path $Root "core\models\diarization\3dspeaker_eres2net_base_zh.onnx") (Join-Path $AppCore "models\diarization\3dspeaker_eres2net_base_zh.onnx")
Copy-IfExists (Join-Path $Root "scripts\install\download_diar_models.bat") (Join-Path $AppDir "download_diar_models.bat")
Copy-IfExists (Join-Path $Root "scripts\install\download_diar_models.ps1") (Join-Path $AppDir "download_diar_models.ps1")
if (Test-Path -LiteralPath $ApiDoc) {
    # PowerShell 5.1 Compress-Archive may corrupt non-ASCII entry names.
    # Keep the UTF-8 content, but use a stable ASCII filename in the public ZIP.
    Copy-IfExists $ApiDoc (Join-Path $AppDir "API_Key_Guide.md")
    Write-Host "API Key guide: included"
    "API Key guide: included" | Add-Content -Encoding UTF8 $Log
} else {
    throw "Missing required file: $ApiDoc"
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
    'cd /d "%~dp0"',
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_app.ps1"'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $AppDir "run_app.bat") -Value $InternalRunText

$InternalVbsText = @'
Option Explicit
Dim fso, shell, baseDir, launcher, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(baseDir, "run_app.bat")
command = Chr(34) & launcher & Chr(34)
shell.Run command, 0, False
'@
Set-Content -Encoding ASCII (Join-Path $AppDir "run_hidden.vbs") -Value $InternalVbsText

$ShortcutScriptText = @'
$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDir = Split-Path -Parent $AppDir
$HiddenTarget = Join-Path $AppDir "run_hidden.vbs"
$FallbackTarget = Join-Path $AppDir "run_app.bat"
$Target = if (Test-Path -LiteralPath $HiddenTarget) { $HiddenTarget } else { $FallbackTarget }
$Icon = Join-Path $AppDir "assets\images\_LOGO.ico"

if (!(Test-Path -LiteralPath $Target)) {
    throw "Shortcut target not found: $Target"
}

$Shell = New-Object -ComObject WScript.Shell

function New-SanWichShortcut {
    param([string] $Path)

    $Shortcut = $Shell.CreateShortcut($Path)
    if ([IO.Path]::GetExtension($Target) -ieq '.vbs') {
        $Shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
        $Shortcut.Arguments = '"' + $Target + '"'
    } else {
        $Shortcut.TargetPath = $Target
    }
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
    'cd /d "%~dp0"',
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp001_setup.ps1"'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $Stage "01_setup.bat") -Value $InstallText
$InstallPs1Text = @'
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
attrib +h (Join-Path $Root "app") 2>$null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "app\setup_internal.ps1")
exit $LASTEXITCODE
'@
[System.IO.File]::WriteAllText((Join-Path $Stage "01_setup.ps1"), $InstallPs1Text, [System.Text.UTF8Encoding]::new($true))

$LaunchText = @(
    '@echo off',
    'cd /d "%~dp0"',
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp002_launch.ps1"'
) -join "`r`n"
Set-Content -Encoding ASCII (Join-Path $Stage "02_launch.bat") -Value $LaunchText
$LaunchPs1Text = @'
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
attrib +h (Join-Path $Root "app") 2>$null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "app\run_app.ps1")
exit $LASTEXITCODE
'@
[System.IO.File]::WriteAllText((Join-Path $Stage "02_launch.ps1"), $LaunchPs1Text, [System.Text.UTF8Encoding]::new($true))

$ReadmeBase64 = "6IGy5paH5Y67U2FuV2ljaCDlronoo53ljIUNClNhbldpY2ggaW5zdGFsbGVyIHBhY2thZ2UNCg0K6KuL5YWI6Kej5aOT57iu5pW05YCL6LOH5paZ5aS+77yM5YaN5Z+36KGMIDAxX3NldHVwLmJhdOOAgg0KRXh0cmFjdCB0aGUgd2hvbGUgZm9sZGVyIGZpcnN0LCB0aGVuIHJ1biAwMV9zZXR1cC5iYXQuDQoNCuWuieijneWujOaIkOW+jO+8jOiri+W+nuahjOmdouaNt+W+keaIluacrOizh+aWmeWkvuWFp+eahCBTYW5XaWNoLmxuayDplovllZ/nqIvlvI/jgIINCkFmdGVyIHNldHVwIGZpbmlzaGVzLCBvcGVuIFNhbldpY2ggZnJvbSB0aGUgZGVza3RvcCBzaG9ydGN1dCBvciBTYW5XaWNoLmxuayBpbiB0aGlzIGZvbGRlci4NCg0KMDJfbGF1bmNoLmJhdCDku43kv53nlZnngrrlgpnnlKjllZ/li5XlmajjgIINCjAyX2xhdW5jaC5iYXQgaXMgc3RpbGwgaW5jbHVkZWQgYXMgYSBmYWxsYmFjayBsYXVuY2hlci4NCg0K6YCZ5YCL5a6J6KOd5YyF5LiN5YyF5ZCr5L2g55qEIEFQSSBLZXnjgIHlgIvkurroqK3lrprjgIHmqKHlnovlv6vlj5bmiJbmmqvlrZjmqpTjgIINClRoaXMgcGFja2FnZSBkb2VzIG5vdCBpbmNsdWRlIHlvdXIgQVBJIGtleSwgcGVyc29uYWwgY29uZmlnLCBtb2RlbCBjYWNoZSwgb3IgdGVtcCBmaWxlcy4NCg0K5aaC5p6c6Zu76IWm5rKS5pyJIFB5dGhvbu+8jOWuieijneeoi+W8j+acg+WEquWFiOS9v+eUqCBhcHBcdG9vbHNccHl0aG9uLTMuMTIuOS1hbWQ2NC5leGXjgIINCklmIFB5dGhvbiBpcyBub3QgaW5zdGFsbGVkLCBzZXR1cCBmaXJzdCB1c2VzIGFwcFx0b29sc1xweXRob24tMy4xMi45LWFtZDY0LmV4ZS4NCg0K5aaC5p6c5YyF5YWn5rKS5pyJIFB5dGhvbiDlronoo53mqpTvvIzlronoo53nqIvlvI/mnIPlvp4gcHl0aG9uLm9yZyDkuIvovInjgIINCklmIHRoZSBidW5kbGVkIFB5dGhvbiBpbnN0YWxsZXIgaXMgbWlzc2luZywgc2V0dXAgZG93bmxvYWRzIFB5dGhvbiBmcm9tIHB5dGhvbi5vcmcuDQoNCkZGbXBlZyDoiIfln7fooYzmiYDpnIDlpZfku7bmnIPlnKjlronoo53mmYLkvp3pnIDopoHkuIvovInjgIINCkZGbXBlZyBhbmQgcnVudGltZSBkZXBlbmRlbmNpZXMgd2lsbCBiZSBkb3dubG9hZGVkIGR1cmluZyBzZXR1cCB3aGVuIG5lZWRlZC4NCg0K56ys5LiA5qyh55yf5q2j6L2J5a+r5pmC5pyD5LiL6LyJIEJyZWV6ZS1BU1ItMjUg5qih5Z6L77yM57SEIDMtNCBHQuOAgg0KQnJlZXplLUFTUi0yNSB3aWxsIGRvd25sb2FkIG9uIHRoZSBmaXJzdCByZWFsIHRyYW5zY3JpcHRpb24sIGFib3V0IDMtNCBHQi4NCg0K5aaC5p6c6KaB5L2/55SoIEFJIOagoeWwje+8jOiri+WcqOioreWumumggeWhq+WFpeS9oOiHquW3seeahCBBUEkgS2V544CCDQpQdXQgeW91ciBvd24gQVBJIGtleSBpbiB0aGUgc2V0dGluZ3MgcGFnZSBpZiB5b3Ugd2FudCBBSSBwcm9vZnJlYWRpbmcuDQoNCmFwcCDos4fmlpnlpL7mmK/lhafpg6jmqpTmoYjvvIzkuIDoiKzkuI3pnIDopoHmiZPplovjgIINClRoZSBhcHAgZm9sZGVyIGNvbnRhaW5zIGludGVybmFsIGZpbGVzIGFuZCBub3JtYWxseSBkb2VzIG5vdCBuZWVkIHRvIGJlIG9wZW5lZC4="
[System.IO.File]::WriteAllText(
    (Join-Path $Stage "README.txt"),
    [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ReadmeBase64)),
    [System.Text.UTF8Encoding]::new($true)
)

$ReadmeV25 = @'
聲文去 SanWich v2.5 安裝包

1. 請先完整解壓縮整個資料夾，再執行 01_setup.bat。
2. 安裝完成後，請使用桌面或資料夾內的 SanWich.lnk 啟動。
3. 捷徑會隱形啟動程式；若啟動失敗，請查看 app\logs\main_error.log。
4. 第一次轉寫會下載 Breeze-ASR-25，約 3 至 4 GB。
5. 若在設定中選擇「本機私密 AI」，第一次使用會另外下載約 4.54 GB 的 Breeze-7B GGUF 與 llama.cpp 執行核心。
6. 本機私密 AI 不需要 API Key，字幕校對只送往這台電腦的 127.0.0.1。
7. 模型、runtime、個人設定、API Key 與波形快取都不包含在分享 ZIP 內。

本機 AI 首次下載至少需要 7 GB 可用空間，建議預留 10 GB。下載途中關閉程式，下次可以從 .part 檔續傳。

SanWich v2.5 installer package

Extract the whole folder, run 01_setup.bat, then launch SanWich.lnk.
Local Private AI downloads its model on first use and does not require an API key.
'@
[System.IO.File]::WriteAllText(
    (Join-Path $Stage "README.txt"),
    $ReadmeV25,
    [System.Text.UTF8Encoding]::new($true)
)

$ZipBaseName = "SanWich_setup_v$AppVersion"
$Zip = Join-Path $Release "$ZipBaseName.zip"
if (Test-Path -LiteralPath $Zip) {
    Remove-Item -LiteralPath $Zip -Force
    "Existing $ZipBaseName.zip removed before deterministic rebuild." | Add-Content -Encoding UTF8 $Log
}

foreach ($directoryName in $ForbiddenPackageDirectories) {
    $forbiddenPaths = Get-ChildItem -LiteralPath $Stage -Directory -Recurse -Force |
        Where-Object { $_.Name -ieq $directoryName }
    if ($forbiddenPaths) {
        throw "Copyrighted local test footage must not be packaged: $($forbiddenPaths.FullName -join ', ')"
    }
}
"Copyrighted local test footage: excluded" | Add-Content -Encoding UTF8 $Log

Compress-Archive -Path $Stage -DestinationPath $Zip

$UpdateStage = Join-Path $StageRoot "update"
$UpdatePayload = Join-Path $UpdateStage "payload\app"
New-Item -ItemType Directory -Force -Path $UpdatePayload | Out-Null
$UpdateManifestFiles = @()
$UpdateExcludes = @('tools\', '.venv\', 'logs\', 'core\models\', 'assets\fonts\')
Get-ChildItem -LiteralPath $AppDir -Recurse -File -Force | ForEach-Object {
    $Relative = $_.FullName.Substring($AppDir.Length + 1)
    $Excluded = $false
    foreach ($Prefix in $UpdateExcludes) {
        if ($Relative.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
            $Excluded = $true
            break
        }
    }
    if (!$Excluded) {
        $Destination = Join-Path $UpdatePayload $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
        $UpdateManifestFiles += [ordered]@{
            path = ('app/' + $Relative.Replace('\', '/'))
            sha256 = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
}
$UpdateManifest = [ordered]@{
    format = 1
    version = $AppVersion
    files = $UpdateManifestFiles
}
$UpdateManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $UpdateStage 'update-manifest.json') -Encoding UTF8
$UpdateZip = Join-Path $Release ("SanWich_update_v" + $AppVersion + ".zip")
if (Test-Path -LiteralPath $UpdateZip) { Remove-Item -LiteralPath $UpdateZip -Force }
Compress-Archive -Path (Join-Path $UpdateStage '*') -DestinationPath $UpdateZip

$Summary = [pscustomobject]@{
    ZipPath = $Zip
    AppVersion = $AppVersion
    ZipSizeMB = [math]::Round((Get-Item -LiteralPath $Zip).Length / 1MB, 2)
    UpdateZipPath = $UpdateZip
    UpdateZipSizeMB = [math]::Round((Get-Item -LiteralPath $UpdateZip).Length / 1MB, 2)
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
Write-Host "  ZIP: $Zip"
Write-Host "  UPDATE: $UpdateZip"
Write-Host "============================================================"
Write-Host ""
