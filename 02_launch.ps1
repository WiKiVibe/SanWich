$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $AppDir "app\SanWich.py")) { $AppDir = Join-Path $AppDir "app" }
$Python = Join-Path $AppDir ".venv\Scripts\pythonw.exe"
if (!(Test-Path -LiteralPath $Python)) { $Python = Join-Path $AppDir ".venv\Scripts\python.exe" }
if (!(Test-Path -LiteralPath $Python)) { throw "找不到 Python 執行環境，請先執行 01_setup.bat。" }
$App = Join-Path $AppDir "SanWich.py"
if (!(Test-Path -LiteralPath $App)) { throw "找不到 SanWich.py。" }
$LogDir = Join-Path $AppDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$process = Start-Process -FilePath $Python -ArgumentList @('"' + $App + '"') -WorkingDirectory $AppDir -RedirectStandardOutput (Join-Path $LogDir "main.log") -RedirectStandardError (Join-Path $LogDir "main_error.log") -PassThru
if ($env:SANWICH_LAUNCH_WAIT -eq "1") { $process.WaitForExit(); exit $process.ExitCode }
