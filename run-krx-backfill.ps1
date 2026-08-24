[CmdletBinding()]
param(
    [string]$StartDate,
    [string]$EndDate
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryRoot = $PSScriptRoot
$envPath = Join-Path $repositoryRoot ".env"

function Assert-IsoDate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    try {
        return [DateTime]::ParseExact(
            $Value,
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    catch {
        throw "$Name must use YYYY-MM-DD format: $Value"
    }
}

function Assert-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $entry = Get-Content -LiteralPath $envPath | Where-Object {
        $_ -match "^\s*$([Regex]::Escape($Name))\s*="
    } | Select-Object -First 1
    if (-not $entry) {
        throw "$Name is missing from .env"
    }

    $value = $entry.Substring($entry.IndexOf("=") + 1).Trim()
    if (-not $value -or $value -in @('""', "''")) {
        throw "$Name is empty in .env"
    }
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw ".env was not found at $envPath"
}

$parsedEndDate = if ($EndDate) {
    Assert-IsoDate -Value $EndDate -Name "EndDate"
}
else {
    (Get-Date).Date
}
$EndDate = $parsedEndDate.ToString("yyyy-MM-dd")

$parsedStartDate = if ($StartDate) {
    Assert-IsoDate -Value $StartDate -Name "StartDate"
}
else {
    $parsedEndDate.AddYears(-5)
}
$StartDate = $parsedStartDate.ToString("yyyy-MM-dd")

if ($parsedStartDate -gt $parsedEndDate) {
    throw "StartDate must not be after EndDate"
}

Assert-DotEnvValue -Name "DATABASE_URL"
Assert-DotEnvValue -Name "KRX_AUTH_KEY"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install and start Docker Desktop first."
}

& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not running. Start Docker Desktop and run this command again."
}

Push-Location $repositoryRoot
try {
    Write-Host "KRX database backfill: $StartDate through $EndDate"
    Write-Host "Raw Blob upload is skipped; this command only updates the PostgreSQL serving tables."
    Write-Host "The operation is idempotent. If it stops, run the same command again."

    & docker compose --profile data run --rm --no-deps --build data `
        python -m scripts.sync_krx `
        --start-date $StartDate `
        --end-date $EndDate `
        --skip-blob
    if ($LASTEXITCODE -ne 0) {
        throw "KRX backfill failed with exit code $LASTEXITCODE"
    }

    & docker compose --profile data run --rm --no-deps data `
        python -m scripts.verify_krx_backfill `
        --start-date $StartDate `
        --end-date $EndDate
    if ($LASTEXITCODE -ne 0) {
        throw "KRX backfill verification failed with exit code $LASTEXITCODE"
    }

    Write-Host "KRX backfill and verification completed successfully."
}
finally {
    Pop-Location
}
