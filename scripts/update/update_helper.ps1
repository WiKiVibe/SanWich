param(
    [Parameter(Mandatory = $true)][string] $PackagePath,
    [Parameter(Mandatory = $true)][string] $InstallRoot,
    [Parameter(Mandatory = $true)][int] $ParentPid,
    [Parameter(Mandatory = $true)][string] $RelaunchPath,
    [Parameter(Mandatory = $true)][string] $ResultPath,
    [switch] $DeleteSelf
)

$ErrorActionPreference = "Stop"
$Status = "failed"
$Message = "Update did not complete."
$BackupRoot = $null

function Write-Result {
    param([string] $ResultStatus, [string] $ResultMessage)
    $parent = Split-Path -Parent $ResultPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [ordered]@{
        status = $ResultStatus
        message = $ResultMessage
        completed_at = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

try {
    $PackagePath = (Resolve-Path -LiteralPath $PackagePath).Path
    $InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
    $RelaunchPath = [IO.Path]::GetFullPath($RelaunchPath)
    if (!(Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        throw "Setup package is missing."
    }
    $driveRoot = [IO.Path]::GetPathRoot($InstallRoot).TrimEnd('\')
    if ($InstallRoot.TrimEnd('\') -eq $driveRoot) {
        throw "Install root cannot be a drive root."
    }
    if ($RelaunchPath -ne (Join-Path $InstallRoot "SanWich.exe")) {
        throw "Relaunch path does not match the SanWich install root."
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (!(Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        throw "SanWich did not close before the update timeout."
    }

    if (!(Test-Path -LiteralPath $RelaunchPath -PathType Leaf)) {
        throw "Installed SanWich executable is missing before update."
    }
    $BackupRoot = Join-Path ([IO.Path]::GetTempPath()) ("SanWich_update_backup_" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $BackupRoot | Out-Null
    Copy-Item -Path (Join-Path $InstallRoot "*") -Destination $BackupRoot -Recurse -Force

    $arguments = @('/S', '/UPDATE=1', ('/D=' + $InstallRoot))
    $installer = Start-Process -FilePath $PackagePath -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    if ($installer.ExitCode -ne 0) {
        throw "Setup exited with code $($installer.ExitCode)."
    }
    if (!(Test-Path -LiteralPath $RelaunchPath -PathType Leaf)) {
        throw "Updated SanWich executable is missing."
    }

    $Status = "success"
    $Message = "Setup update installed successfully."
} catch {
    $Message = $_.Exception.Message
    if ($BackupRoot -and (Test-Path -LiteralPath (Join-Path $BackupRoot "SanWich.exe") -PathType Leaf)) {
        try {
            Remove-Item -LiteralPath (Join-Path $InstallRoot "SanWich.exe") -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath (Join-Path $InstallRoot "_internal") -Recurse -Force -ErrorAction SilentlyContinue
            Copy-Item -Path (Join-Path $BackupRoot "*") -Destination $InstallRoot -Recurse -Force
            $Message += " Previous version restored."
        } catch {
            $Message += " Automatic restore failed: $($_.Exception.Message)"
        }
    }
} finally {
    try { Write-Result $Status $Message } catch {}
    try {
        if (Test-Path -LiteralPath $RelaunchPath -PathType Leaf) {
            Start-Process -FilePath $RelaunchPath -WorkingDirectory (Split-Path -Parent $RelaunchPath) -WindowStyle Hidden
        }
    } catch {}
    if ($BackupRoot) {
        try { Remove-Item -LiteralPath $BackupRoot -Recurse -Force } catch {}
    }
    try { Remove-Item -LiteralPath $PackagePath -Force } catch {}
    if ($DeleteSelf) {
        try { Remove-Item -LiteralPath $PSCommandPath -Force } catch {}
    }
}
