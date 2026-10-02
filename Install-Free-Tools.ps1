param([switch]$LoginGHunt)
$ErrorActionPreference = 'Stop'
$atlasPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $atlasPython)) { $atlasPython = 'python' }
$atlasSetup = Join-Path $PSScriptRoot 'setup_free_tools.py'
if ($LoginGHunt) { & $atlasPython $atlasSetup --login-ghunt } else { & $atlasPython $atlasSetup }
if ($LASTEXITCODE -ne 0) { throw 'Free tools setup did not complete. Review the error above.' }
