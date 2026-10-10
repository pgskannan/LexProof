<#
Creates or updates the Nebius Token Factory and optional Tavily secrets.

Reads NEBIUS_API_KEY (required) and TAVILY_API_KEY (optional) from backend\.env.
Secret values are piped to gcloud on stdin and are never printed.

Run from the repo root:
    powershell -ExecutionPolicy Bypass -File backend\deploy\create-nebius-secrets.ps1
#>
$ErrorActionPreference = "Continue"

function Read-DotEnv([string]$path) {
    $values = @{}
    foreach ($line in Get-Content $path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $value = $line -split '=', 2
        $value = $value.Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key.Trim()] = $value
    }
    return $values
}

function Write-SecretValue([string]$Name, [string]$Value) {
    $gcloudCmd = Join-Path (Split-Path (Get-Command gcloud).Source -Parent) "gcloud.cmd"
    if (-not (Test-Path $gcloudCmd)) { throw "gcloud.cmd was not found next to gcloud." }
    & $gcloudCmd secrets describe $Name *> $null
    $exists = $LASTEXITCODE -eq 0
    $arguments = if ($exists) {
        "secrets versions add $Name --data-file=-"
    } else {
        "secrets create $Name --replication-policy=automatic --data-file=-"
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $gcloudCmd
    $start.Arguments = $arguments
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($start)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $process.StandardInput.Close()
    $null = $process.StandardOutput.ReadToEnd()
    $null = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "gcloud could not write secret $Name (exit $($process.ExitCode)). The value was not printed."
    }
    if ($exists) { Write-Host "   added a new version of $Name" } else { Write-Host "   created $Name" }
}

if (-not (Test-Path "backend\.env")) { throw "Run this from the repo root. backend\.env was not found." }
& (Join-Path $PSScriptRoot "..\scripts\require-command.ps1") gcloud
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$envValues = Read-DotEnv "backend\.env"
$project = $envValues["GOOGLE_CLOUD_PROJECT"]
if (-not $project) { throw "GOOGLE_CLOUD_PROJECT is missing from backend\.env" }
if (-not $envValues["NEBIUS_API_KEY"]) { throw "NEBIUS_API_KEY is missing from backend\.env" }

& gcloud config set project $project
if ($LASTEXITCODE -ne 0) { throw "gcloud config set project failed" }
& gcloud services enable secretmanager.googleapis.com
if ($LASTEXITCODE -ne 0) { throw "could not enable secretmanager.googleapis.com" }

Write-Host "== Nebius Token Factory secrets (values are not printed)"
Write-SecretValue "lexproof-nebius-api-key" $envValues["NEBIUS_API_KEY"]
if ($envValues["TAVILY_API_KEY"]) {
    Write-SecretValue "lexproof-tavily-api-key" $envValues["TAVILY_API_KEY"]
} else {
    Write-Host "   TAVILY_API_KEY is not in backend\.env; skipping lexproof-tavily-api-key"
}