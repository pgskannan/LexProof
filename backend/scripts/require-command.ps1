<#
.SYNOPSIS
Exit 127 when a required executable is not on PATH.

PowerShell's CommandNotFoundException does not set $LASTEXITCODE, so a later
check of $LASTEXITCODE treats a missing binary (docker, gcloud, ...) as success.
#>
param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Name
)

$missing = @()
foreach ($command in $Name) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        $missing += $command
    }
}
if ($missing.Count -gt 0) {
    [Console]::Error.WriteLine("missing command: $($missing -join ', ')")
    exit 127
}
exit 0
