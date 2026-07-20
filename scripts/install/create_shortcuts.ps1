$ErrorActionPreference = "Stop"

# Source-checkout helper. Release packages receive their own generated copy.
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageDir = (Resolve-Path (Join-Path $AppDir '..\..')).Path

$HiddenTarget = Join-Path $PackageDir "run_hidden.vbs"
$FallbackTarget = Join-Path $PackageDir "02_launch.bat"
$Target = if (Test-Path -LiteralPath $HiddenTarget) { $HiddenTarget } else { $FallbackTarget }
$Icon = Join-Path $PackageDir "assets\images\_LOGO.ico"

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
    $Shortcut.WorkingDirectory = $PackageDir
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
