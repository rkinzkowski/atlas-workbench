param([string]$DataDirectory)
$ErrorActionPreference = 'Stop'
$atlasDataDirectory = if ($DataDirectory) { [IO.Path]::GetFullPath($DataDirectory) } else { Join-Path $PSScriptRoot 'data' }
$pidFile = Join-Path $atlasDataDirectory 'server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No Atlas launcher process is recorded.'; exit }
$atlasProcessId = [int](Get-Content -LiteralPath $pidFile)
$atlasProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $atlasProcessId" -ErrorAction SilentlyContinue
$expectedScript = Join-Path $PSScriptRoot 'app.py'
if ($atlasProcess -and $atlasProcess.CommandLine.Contains($expectedScript)) {
    $result = Invoke-CimMethod -InputObject $atlasProcess -MethodName Terminate
    if ($result.ReturnValue -ne 0) { throw "Atlas could not be stopped (result $($result.ReturnValue))." }
    Write-Output 'Atlas stopped. Active requests will be marked interrupted on restart; review before retrying.'
} else { Write-Output 'The recorded process is no longer this Atlas application.' }
