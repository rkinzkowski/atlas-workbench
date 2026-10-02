param([int]$Port = 8765, [switch]$Restart, [string]$DataDirectory)
$ErrorActionPreference = 'Stop'
$appDirectory = $PSScriptRoot
$dataDirectory = if ($DataDirectory) { [IO.Path]::GetFullPath($DataDirectory) } else { Join-Path $appDirectory 'data' }
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $bundledPython) { $pythonExecutable = $bundledPython }
elseif ($pythonCommand) { $pythonExecutable = $pythonCommand.Source }
else { throw 'Python 3.11 or later is required. Install Python, then run this launcher again.' }
$address = "http://127.0.0.1:$Port"
if ($Restart) { & (Join-Path $appDirectory 'Stop-Atlas.ps1') -DataDirectory $dataDirectory }
try {
    $existing = Invoke-RestMethod -Uri "$address/api/state" -TimeoutSec 2
    if ($existing.csrf -and $null -ne $existing.sources) { Start-Process $address; exit }
    throw "Port $Port is used by another program. Choose a different port."
} catch {
    if ($_.Exception.Message -like '*another program*') { throw }
}
New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
$arguments = @('"' + (Join-Path $appDirectory 'app.py') + '"', '--port', "$Port", '--data', '"' + $dataDirectory + '"')
$process = Start-Process -FilePath $pythonExecutable -ArgumentList $arguments -WorkingDirectory $appDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dataDirectory 'server.log') -RedirectStandardError (Join-Path $dataDirectory 'server-error.log')
$process.Id | Set-Content -LiteralPath (Join-Path $dataDirectory 'server.pid')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) { throw 'Atlas could not start. See data/server-error.log.' }
    try {
        $state = Invoke-RestMethod -Uri "$address/api/state" -TimeoutSec 1
        if ($state.csrf) { Start-Process $address; exit }
    } catch { }
}
throw 'Atlas did not become ready. See data/server-error.log.'
