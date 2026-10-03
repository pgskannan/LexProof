<#
Deploys the LexProof API to Cloud Run.

Run from the repo root (C:\Projects\LexProof):
    powershell -ExecutionPolicy Bypass -File backend\deploy\deploy-cloud-run.ps1

What it does:
  1. Enables the Google Cloud APIs Cloud Run needs.
  2. Creates a dedicated runtime service account with only the roles the API uses.
  3. Copies ETHEREUM_PRIVATE_KEY and ETHEREUM_RPC_URL from backend\.env into Secret Manager.
     The values never appear on screen and are not baked into the image.
  4. Builds backend\ with Cloud Build and deploys it as the "lexproof-api" service.
  5. Prints the service URL and checks /health.

Safe to re-run: existing APIs, accounts and secrets are reused, and secrets get a new version.
#>
param(
    [string]$Region = "us-central1",
    [string]$Service = "lexproof-api",
    [string]$CorsOrigins = "https://lexproof-pied.vercel.app,http://localhost:3000",
    [int]$MinInstances = 0,
    [string]$ReadOnlyUids = "demo-judge-1"
)
# "Continue", not "Stop": gcloud writes progress to stderr, which Windows PowerShell 5.1
# would otherwise turn into a terminating error. Failures are caught via $LASTEXITCODE.
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

function Invoke-Gcloud {
    & gcloud @args
    if ($LASTEXITCODE -ne 0) { throw "gcloud $($args -join ' ') failed (exit $LASTEXITCODE)" }
}

if (-not (Test-Path "backend\Dockerfile")) { throw "Run this from the repo root (C:\Projects\LexProof)." }
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { throw "gcloud CLI not found. Install it from https://cloud.google.com/sdk/docs/install and run 'gcloud auth login'." }

$envValues = Read-DotEnv "backend\.env"
$Project = $envValues["GOOGLE_CLOUD_PROJECT"]
if (-not $Project) { throw "GOOGLE_CLOUD_PROJECT is missing from backend\.env" }
foreach ($required in "ETHEREUM_PRIVATE_KEY", "ETHEREUM_RPC_URL", "ETHEREUM_CONTRACT_ADDRESS", "ETHEREUM_PASSPORT_REGISTRY_ADDRESS") {
    if (-not $envValues[$required]) { throw "$required is missing from backend\.env" }
}

Write-Host "== Project $Project, region $Region, service $Service" -ForegroundColor Cyan
Invoke-Gcloud config set project $Project

Write-Host "== 1/5 Enabling APIs (first run takes a minute)" -ForegroundColor Cyan
Invoke-Gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
    secretmanager.googleapis.com aiplatform.googleapis.com firestore.googleapis.com identitytoolkit.googleapis.com

Write-Host "== 2/5 Runtime service account" -ForegroundColor Cyan
$SaName = "lexproof-api"
$Sa = "$SaName@$Project.iam.gserviceaccount.com"
& gcloud iam service-accounts describe $Sa *> $null
if ($LASTEXITCODE -ne 0) {
    Invoke-Gcloud iam service-accounts create $SaName --display-name "LexProof API (Cloud Run)"
    Start-Sleep -Seconds 10   # let the new account propagate before granting roles
}
$roles = @(
    "roles/datastore.user",              # Firestore
    "roles/aiplatform.user",             # Gemini on Vertex AI
    "roles/firebaseauth.admin",          # verify tokens, set role claims
    "roles/storage.objectAdmin",         # contract file uploads
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter"
)
foreach ($role in $roles) {
    Invoke-Gcloud projects add-iam-policy-binding $Project --member "serviceAccount:$Sa" --role $role --condition None --quiet *> $null
    Write-Host "   granted $role"
}

# Source deploys build with the Compute Engine default service account; newer projects
# don't give it build permissions by default.
$ProjectNumber = (& gcloud projects describe $Project --format "value(projectNumber)").Trim()
foreach ($buildRole in "roles/run.builder", "roles/cloudbuild.builds.builder") {
    Invoke-Gcloud projects add-iam-policy-binding $Project --member "serviceAccount:$ProjectNumber-compute@developer.gserviceaccount.com" --role $buildRole --condition None --quiet *> $null
    Write-Host "   granted $buildRole to the build service account"
}
Start-Sleep -Seconds 60   # new IAM grants take a minute to reach Cloud Build

Write-Host "== 3/5 Secrets (values read from backend\.env, never printed)" -ForegroundColor Cyan
$secrets = @{ "ETHEREUM_PRIVATE_KEY" = "lexproof-ethereum-private-key"; "ETHEREUM_RPC_URL" = "lexproof-ethereum-rpc-url" }
foreach ($envName in $secrets.Keys) {
    $secretName = $secrets[$envName]
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmp, $envValues[$envName])   # no trailing newline
        & gcloud secrets describe $secretName *> $null
        if ($LASTEXITCODE -ne 0) {
            Invoke-Gcloud secrets create $secretName --replication-policy automatic --data-file $tmp *> $null
            Write-Host "   created $secretName"
        } else {
            Invoke-Gcloud secrets versions add $secretName --data-file $tmp *> $null
            Write-Host "   added a new version of $secretName"
        }
    } finally {
        Remove-Item $tmp -Force
    }
}

# Optional: SMTP password for trial/demo request emails (backend\.env SMTP_PASSWORD).
$smtpSecret = $null
if ($envValues["SMTP_PASSWORD"] -and $envValues["SMTP_USERNAME"]) {
    $smtpSecret = "lexproof-smtp-password"
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmp, $envValues["SMTP_PASSWORD"])
        & gcloud secrets describe $smtpSecret *> $null
        if ($LASTEXITCODE -ne 0) {
            Invoke-Gcloud secrets create $smtpSecret --replication-policy automatic --data-file $tmp *> $null
            Write-Host "   created $smtpSecret"
        } else {
            Invoke-Gcloud secrets versions add $smtpSecret --data-file $tmp *> $null
            Write-Host "   added a new version of $smtpSecret"
        }
    } finally {
        Remove-Item $tmp -Force
    }
} else {
    Write-Host "   SMTP_USERNAME/SMTP_PASSWORD not in backend\.env: trial/demo request emails stay off"
}

Write-Host "== 4/5 Build and deploy (Cloud Build, about 5-8 minutes)" -ForegroundColor Cyan
$plain = [ordered]@{
    GOOGLE_CLOUD_PROJECT               = $Project
    FIREBASE_PROJECT_ID                = $(if ($envValues["FIREBASE_PROJECT_ID"]) { $envValues["FIREBASE_PROJECT_ID"] } else { $Project })
    GOOGLE_CLOUD_LOCATION              = $(if ($envValues["GOOGLE_CLOUD_LOCATION"]) { $envValues["GOOGLE_CLOUD_LOCATION"] } else { "us-central1" })
    GEMINI_MODEL                       = $envValues["GEMINI_MODEL"]
    GEMINI_TEMPERATURE                 = $envValues["GEMINI_TEMPERATURE"]
    GEMINI_MAX_OUTPUT_TOKENS           = $envValues["GEMINI_MAX_OUTPUT_TOKENS"]
    FIREBASE_STORAGE_BUCKET            = $envValues["FIREBASE_STORAGE_BUCKET"]
    ETHEREUM_CHAIN_ID                  = $(if ($envValues["ETHEREUM_CHAIN_ID"]) { $envValues["ETHEREUM_CHAIN_ID"] } else { "11155111" })
    ETHEREUM_CONTRACT_ADDRESS          = $envValues["ETHEREUM_CONTRACT_ADDRESS"]
    ETHEREUM_PASSPORT_REGISTRY_ADDRESS = $envValues["ETHEREUM_PASSPORT_REGISTRY_ADDRESS"]
    LEXPROOF_CORS_ORIGINS              = $CorsOrigins
    LEXPROOF_READ_ONLY_UIDS            = $ReadOnlyUids
    SMTP_USERNAME                      = $envValues["SMTP_USERNAME"]
    SMTP_HOST                          = $envValues["SMTP_HOST"]
    SMTP_PORT                          = $envValues["SMTP_PORT"]
    TRIAL_NOTIFY_TO                    = $envValues["TRIAL_NOTIFY_TO"]
}
# Written to a YAML file rather than --set-env-vars: the CORS list contains commas, and
# gcloud.cmd runs through cmd.exe, which mangles the usual "^|^" delimiter escape.
$envFile = Join-Path ([System.IO.Path]::GetTempPath()) "lexproof-cloud-run-env.yaml"
$yaml = ($plain.GetEnumerator() | Where-Object { $_.Value } | ForEach-Object { "$($_.Key): '$($_.Value -replace "'", "''")'" }) -join "`n"
[System.IO.File]::WriteAllText($envFile, $yaml + "`n")
$secretArg = "ETHEREUM_PRIVATE_KEY=lexproof-ethereum-private-key:latest,ETHEREUM_RPC_URL=lexproof-ethereum-rpc-url:latest"
if ($smtpSecret) { $secretArg += ",SMTP_PASSWORD=${smtpSecret}:latest" }

Invoke-Gcloud run deploy $Service `
    --source backend `
    --region $Region `
    --service-account $Sa `
    --allow-unauthenticated `
    --memory 1Gi --cpu 1 --timeout 300 `
    --min-instances $MinInstances --max-instances 1 `
    --env-vars-file $envFile `
    --set-secrets $secretArg `
    --quiet
Remove-Item $envFile -Force -ErrorAction SilentlyContinue

Write-Host "== 5/5 Checking the service" -ForegroundColor Cyan
$url = (& gcloud run services describe $Service --region $Region --format "value(status.url)").Trim()
Write-Host "   Service URL: $url" -ForegroundColor Green
try {
    $health = Invoke-RestMethod "$url/health" -TimeoutSec 60
    Write-Host "   /health -> $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "   /health failed: $($_.Exception.Message). Check logs: gcloud run services logs read $Service --region $Region --limit 50" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Next: in Vercel set NEXT_PUBLIC_API_URL=$url and redeploy; in Firebase Auth add lexproof-pied.vercel.app under Authorized domains."
