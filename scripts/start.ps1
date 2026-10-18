param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
docker compose --profile cloud up -d cloud-sql-proxy
if ($LASTEXITCODE -ne 0) { throw 'Cloud SQL proxy did not start. Verify Docker Desktop, ADC and Cloud SQL provisioning.' }
if (-not $SkipInstall) {
    uv sync --extra cloud
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed. Install Python 3.12 or allow uv to download it.' }
    Push-Location frontend
    try {
        npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    } finally { Pop-Location }
}
Write-Host 'Start the API in one terminal: uv run uvicorn backend.main:app --reload'
Write-Host 'Start React in another: cd frontend; npm.cmd run dev'
Write-Host 'Open http://localhost:5173'
