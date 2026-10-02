param([Parameter(Mandatory=$true)][string]$Backup, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$atlasBundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (Test-Path -LiteralPath $atlasBundledPython) { $atlasPython = $atlasBundledPython }
else { $atlasPython = (Get-Command python -ErrorAction Stop).Source }
& $atlasPython (Join-Path $PSScriptRoot 'restore_backup.py') $Backup $Destination
if ($LASTEXITCODE -ne 0) { throw 'Backup restore did not complete.' }
Write-Host 'Start the restored workspace with Start-Atlas.ps1 -DataDirectory <destination> -Port 8766.'
