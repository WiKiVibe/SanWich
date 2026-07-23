$ErrorActionPreference = "Stop"
$builder = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*build_zip.ps1" | Select-Object -First 1
if ($null -eq $builder) { throw "Release builder was not found." }
& $builder.FullName
exit $LASTEXITCODE
