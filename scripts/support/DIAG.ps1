$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Log = Join-Path $Root "diag_log.txt"
"SanWich diagnostic`r`nTime: $(Get-Date -Format o)`r`nFolder: $Root" | Set-Content -LiteralPath $Log -Encoding UTF8
"`r`n--- root files ---" | Add-Content -LiteralPath $Log -Encoding UTF8
Get-ChildItem -LiteralPath $Root -Force | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize | Out-String | Add-Content -LiteralPath $Log -Encoding UTF8
$AppDir = if (Test-Path -LiteralPath (Join-Path $Root "app")) { Join-Path $Root "app" } else { $Root }
$Python = Join-Path $AppDir ".venv\Scripts\python.exe"
"`r`n--- Python ---" | Add-Content -LiteralPath $Log -Encoding UTF8
if (Test-Path -LiteralPath $Python) {
    & $Python -c "import sys; print(sys.version)" *>> $Log
} else {
    "Virtual environment not found." | Add-Content -LiteralPath $Log -Encoding UTF8
}
Write-Host "診斷完成：$Log"
if ($Host.Name -notmatch "ServerRemoteHost") { [void](Read-Host "按 Enter 關閉") }
