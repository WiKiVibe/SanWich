$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$App = Join-Path $Root "SanWich.py"
if (!(Test-Path -LiteralPath $Python)) { throw "找不到 .venv\Scripts\python.exe。" }
if (!(Test-Path -LiteralPath $App)) { throw "找不到 SanWich.py。" }
$env:SANWICH_MAIN_RELAUNCHED = "1"
$env:PYTHONUTF8 = "1"
& $Python $App
if ($Host.Name -notmatch "ServerRemoteHost") { [void](Read-Host "程式已結束，按 Enter 關閉") }
