param([int]$Port = 8765, [string]$DataDirectory)
& (Join-Path $PSScriptRoot 'Start-Atlas.ps1') -Restart -Port $Port -DataDirectory $DataDirectory
