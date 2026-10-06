<#
Creates or updates the PayPal sandbox secrets in Secret Manager.

Reads PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, and the optional PAYPAL_WEBHOOK_ID
from backend\.env. Values are written with `gcloud secrets ... --data-file=-`
and are never printed.

Run from the repo root:
    powershell -ExecutionPolicy Bypass -File backend\deploy\create-paypal-secrets.ps1
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
foreach ($required in @("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")) {
    if (-not $envValues[$required]) { throw "$required is missing from backend\.env" }
}

& gcloud config set project $project
if ($LASTEXITCODE -ne 0) { throw "gcloud config set project failed" }
& gcloud services enable secretmanager.googleapis.com
if ($LASTEXITCODE -ne 0) { throw "could not enable secretmanager.googleapis.com" }

Write-Host "== PayPal sandbox secrets (values are not printed)"
Write-SecretValue "lexproof-paypal-client-id" $envValues["PAYPAL_CLIENT_ID"]
Write-SecretValue "lexproof-paypal-client-secret" $envValues["PAYPAL_CLIENT_SECRET"]
if ($envValues["PAYPAL_WEBHOOK_ID"]) {
    Write-SecretValue "lexproof-paypal-webhook-id" $envValues["PAYPAL_WEBHOOK_ID"]
} else {
    Write-Host "   PAYPAL_WEBHOOK_ID is not in backend\.env; skipping lexproof-paypal-webhook-id"
}
