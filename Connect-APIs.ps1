param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$atlasProviders = @(
    @{ Name='OSINT Industries'; Variables=@('OSINT_INDUSTRIES_API_KEY') },
    @{ Name='ScrapeCreators'; Variables=@('SCRAPECREATORS_API_KEY') },
    @{ Name='Serper'; Variables=@('SERPER_API_KEY') },
    @{ Name='People Data Labs'; Variables=@('PDL_API_KEY') },
    @{ Name='Twilio Lookup'; Variables=@('TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN') },
    @{ Name='Have I Been Pwned'; Variables=@('HIBP_API_KEY') },
    @{ Name='BuiltWith'; Variables=@('BUILTWITH_API_KEY') },
    @{ Name='SecurityTrails'; Variables=@('SECURITYTRAILS_API_KEY') },
    @{ Name='IPinfo Core'; Variables=@('IPINFO_TOKEN') },
    @{ Name='AbuseIPDB'; Variables=@('ABUSEIPDB_API_KEY') },
    @{ Name='SerpApi'; Variables=@('SERPAPI_API_KEY') },
    @{ Name='TinEye'; Variables=@('TINEYE_API_KEY') },
    @{ Name='Sightengine'; Variables=@('SIGHTENGINE_API_USER','SIGHTENGINE_API_SECRET') },
    @{ Name='Google Web Risk'; Variables=@('GOOGLE_WEBRISK_API_KEY') },
    @{ Name='OpenAI (optional reports, questions and web corroboration)'; Variables=@('OPENAI_API_KEY') }
)
Write-Host 'Atlas API connections'
Write-Host 'Keys are entered privately and passed to the local server. This script does not save them to a file.'
Write-Host 'Start with 1,2,3,4. Other services add specific capabilities described in API-SETUP.md.'
for ($atlasIndex = 0; $atlasIndex -lt $atlasProviders.Count; $atlasIndex++) {
    Write-Host ('{0}. {1}' -f ($atlasIndex + 1), $atlasProviders[$atlasIndex].Name)
}
$atlasSelection = Read-Host 'Provider numbers, separated by commas (blank exits)'
if ([string]::IsNullOrWhiteSpace($atlasSelection)) { return }
$atlasChoices = @($atlasSelection.Split(',') | ForEach-Object { [int]$_.Trim() } | Select-Object -Unique)
if (@($atlasChoices | Where-Object { $_ -lt 1 -or $_ -gt $atlasProviders.Count }).Count) { throw 'Choose provider numbers from the displayed list.' }
$atlasOriginalEnvironment = @{}
try {
    foreach ($atlasChoice in $atlasChoices) {
        $atlasProvider = $atlasProviders[$atlasChoice - 1]
        Write-Host $atlasProvider.Name
        foreach ($atlasVariable in $atlasProvider.Variables) {
            $atlasSecret = Read-Host "$atlasVariable (blank keeps the current setting)" -AsSecureString
            if ($atlasSecret.Length -eq 0) { $atlasSecret.Dispose(); continue }
            $atlasOriginalEnvironment[$atlasVariable] = [Environment]::GetEnvironmentVariable($atlasVariable, 'Process')
            $atlasPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($atlasSecret)
            try { [Environment]::SetEnvironmentVariable($atlasVariable, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($atlasPointer), 'Process') }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($atlasPointer); $atlasSecret.Dispose() }
        }
        if ($atlasChoice -eq 15) {
            $atlasModel = Read-Host 'OpenAI model ID available to your account (blank keeps current setting)'
            if (-not [string]::IsNullOrWhiteSpace($atlasModel)) {
                $atlasOriginalEnvironment['OPENAI_MODEL'] = [Environment]::GetEnvironmentVariable('OPENAI_MODEL', 'Process')
                [Environment]::SetEnvironmentVariable('OPENAI_MODEL', $atlasModel.Trim(), 'Process')
            }
        }
    }
    & (Join-Path $PSScriptRoot 'Start-Atlas.ps1') -Port $Port -Restart
} finally {
    foreach ($atlasVariable in $atlasOriginalEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($atlasVariable, $atlasOriginalEnvironment[$atlasVariable], 'Process')
    }
}
