$ErrorActionPreference = "Stop"

# Works in both layouts:
#   repo root  : run_app target = 02_launch.bat (this folder)
#   zip app dir: run_app.bat exists next to this script
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDir = Split-Path -Parent $AppDir

$Target = Join-Path $AppDir "run_app.bat"
if (!(Test-Path -LiteralPath $Target)) {
    $Target = Join-Path $AppDir "02_launch.bat"
    $PackageDir = $AppDir
}
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
