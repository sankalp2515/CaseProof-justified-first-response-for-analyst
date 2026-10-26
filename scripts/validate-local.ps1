param([switch]$SkipBuild, [switch]$SkipRecovery, [switch]$SkipBrowser)
# Validates the local Compose microservice stack: build, start, backend regression,
# browser acceptance against the frontend service and fault injection.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace
New-Item -ItemType Directory -Path 'var/local-validation' -Force | Out-Null

function Invoke-Checked {
    param([string]$Exe, [string[]]$CommandArgs)
    & $Exe @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Validation failed: $Exe $($CommandArgs -join ' ')"
    }
}

if (-not $SkipBuild) {
    Invoke-Checked docker @('compose', 'build')
    Invoke-Checked docker @('compose', '--profile', 'validation', 'build', 'tests')
}
Invoke-Checked docker @('compose', 'up', '-d', '--wait')
Invoke-Checked docker @('compose', '--profile', 'validation', 'run', '--rm', '--no-deps', 'tests')
if (-not $SkipBrowser) {
    Push-Location frontend
    try { Invoke-Checked node @('scripts/acceptance-browser.mjs') } finally { Pop-Location }
}
if (-not $SkipRecovery) {
    Invoke-Checked docker @('compose', '--profile', 'validation', 'run', '--rm', '--no-deps', 'recovery-check')
}
Write-Host 'Local validation passed. Open http://127.0.0.1:8080/app/#/entry'
Write-Host 'Reports: var/frontend-validation/quality and var/local-validation'
