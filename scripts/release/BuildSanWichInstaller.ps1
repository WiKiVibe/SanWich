param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$MainScript = Join-Path $ProjectRoot "SanWich.py"
$SpecFile = Join-Path $PSScriptRoot "SanWichInstaller.nsi"
$PyInstallerSpec = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.spec" -File | Select-Object -First 1 -ExpandProperty FullName
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
$NsisCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"),
    (Join-Path $env:ProgramFiles "NSIS\makensis.exe")
)
$MakeNsis = $NsisCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Project Python is missing." }
if (!(Test-Path -LiteralPath $PyInstaller -PathType Leaf)) { throw "PyInstaller is missing." }
if (!$PyInstallerSpec) { throw "PyInstaller spec is missing." }
if (!$MakeNsis) { throw "NSIS makensis.exe is missing." }

$VersionMatch = [regex]::Match((Get-Content -LiteralPath $MainScript -Raw -Encoding UTF8), 'APP_VERSION\s*=\s*"([^"]+)"')
if (!$VersionMatch.Success) { throw "Cannot determine APP_VERSION." }
$Version = $VersionMatch.Groups[1].Value
if ($Version -notmatch '^\d+\.\d+(?:\.\d+)?$') { throw "APP_VERSION is not installer-compatible." }
$Parts = @($Version.Split('.'))
while ($Parts.Count -lt 4) { $Parts += '0' }
$FileVersion = ($Parts[0..3] -join '.')

Push-Location $ProjectRoot
try {
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

    & $PyInstaller --clean --noconfirm $PyInstallerSpec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    & $MakeNsis "/DAPP_VERSION=$Version" "/DAPP_FILE_VERSION=$FileVersion" $SpecFile
    if ($LASTEXITCODE -ne 0) { throw "NSIS build failed." }

    $Output = Join-Path $ProjectRoot ("release\SanWich_Setup_v" + $Version + ".exe")
    if (!(Test-Path -LiteralPath $Output -PathType Leaf)) { throw "Installer output is missing." }
    Get-Item -LiteralPath $Output | Select-Object FullName, Length, LastWriteTime
    Get-FileHash -LiteralPath $Output -Algorithm SHA256
} finally {
    Pop-Location
}
