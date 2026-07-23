param(
    [Parameter(Mandatory = $true)][string] $PackagePath,
    [Parameter(Mandatory = $true)][string] $InstallRoot,
    [Parameter(Mandatory = $true)][int] $ParentPid,
    [Parameter(Mandatory = $true)][string] $RelaunchPath,
    [Parameter(Mandatory = $true)][string] $ResultPath
)

$ErrorActionPreference = "Stop"
$ExtractRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("SanWich_update_apply_" + [guid]::NewGuid().ToString("N"))
$BackupRoot = Join-Path $ExtractRoot "backup"
$PayloadRoot = Join-Path $ExtractRoot "payload"
$CopiedTargets = New-Object System.Collections.Generic.List[string]

function Write-Result {
    param([string] $Status, [string] $Message, [string] $Version = "")
    $parent = Split-Path -Parent $ResultPath
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [ordered]@{
        status = $Status
        message = $Message
        version = $Version
        completed_at = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8
}

function Resolve-SafeTarget {
    param([string] $RelativePath)
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath)) {
        throw "Invalid update path."
    }
    $normalized = $RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar)
    if ($normalized.Split([IO.Path]::DirectorySeparatorChar) -contains '..') {
        throw "Update path escapes install root."
    }
    $root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath((Join-Path $InstallRoot $normalized))
    if (!$target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Update path escapes install root."
    }
    return $target
}

try {
    $PackagePath = (Resolve-Path -LiteralPath $PackagePath).Path
    $InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
    New-Item -ItemType Directory -Force -Path $ExtractRoot, $BackupRoot | Out-Null

    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (!(Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
        throw "SanWich did not close before the update timeout."
    }

    Expand-Archive -LiteralPath $PackagePath -DestinationPath $ExtractRoot -Force
    $ManifestPath = Join-Path $ExtractRoot "update-manifest.json"
    if (!(Test-Path -LiteralPath $ManifestPath)) { throw "Update manifest is missing." }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.format -ne 1 -or !$Manifest.version -or !$Manifest.files) { throw "Update manifest is invalid." }

    foreach ($File in $Manifest.files) {
        $RelativePath = [string]$File.path
        $ExpectedHash = ([string]$File.sha256).ToUpperInvariant()
        if ($ExpectedHash -notmatch '^[0-9A-F]{64}$') { throw "Invalid file digest in manifest." }
        $Source = Join-Path $PayloadRoot $RelativePath.Replace('/', '\')
        if (!(Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Update payload file is missing." }
        $ActualHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($ActualHash -ne $ExpectedHash) { throw "Update payload verification failed." }
        [void](Resolve-SafeTarget $RelativePath)
    }

    foreach ($File in $Manifest.files) {
        $RelativePath = [string]$File.path
        $Source = Join-Path $PayloadRoot $RelativePath.Replace('/', '\')
        $Target = Resolve-SafeTarget $RelativePath
        $Backup = Join-Path $BackupRoot $RelativePath.Replace('/', '\')
        if (Test-Path -LiteralPath $Target -PathType Leaf) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Backup) | Out-Null
            Copy-Item -LiteralPath $Target -Destination $Backup -Force
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Target -Force
        $CopiedTargets.Add($Target)
    }

    Write-Result "success" "Update installed successfully." ([string]$Manifest.version)
} catch {
    if ($null -ne $Manifest -and $null -ne $Manifest.files) {
        foreach ($File in $Manifest.files) {
            $Relative = [string]$File.path
            $Target = Resolve-SafeTarget $Relative
            if (!$CopiedTargets.Contains($Target)) { continue }
            $Backup = Join-Path $BackupRoot $Relative.Replace('/', '\')
            if (Test-Path -LiteralPath $Backup -PathType Leaf) {
                Copy-Item -LiteralPath $Backup -Destination $Target -Force
            } elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                Remove-Item -LiteralPath $Target -Force
            }
        }
    }
    Write-Result "failed" $_.Exception.Message
} finally {
    try {
        if (Test-Path -LiteralPath $RelaunchPath -PathType Leaf) {
            if ([IO.Path]::GetExtension($RelaunchPath) -ieq '.vbs') {
                Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\wscript.exe') -ArgumentList ('"' + $RelaunchPath + '"') -WorkingDirectory (Split-Path -Parent $RelaunchPath) -WindowStyle Hidden
            } else {
                Start-Process -FilePath $RelaunchPath -WorkingDirectory (Split-Path -Parent $RelaunchPath) -WindowStyle Hidden
            }
        }
    } catch {}
    try { Remove-Item -LiteralPath $ExtractRoot -Recurse -Force } catch {}
}
