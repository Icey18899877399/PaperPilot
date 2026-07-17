param(
    [int]$Port = 8001,
    [string]$VenvPath = ".venv-mineru"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$mineruApi = Join-Path $projectRoot "$VenvPath\Scripts\mineru-api.exe"

if (-not (Test-Path -LiteralPath $mineruApi)) {
    throw "MinerU is not installed. Run scripts\install-mineru.ps1 first."
}

$env:MINERU_FORMULA_ENABLE = "true"
$env:MINERU_TABLE_ENABLE = "true"
$env:MINERU_PROCESSING_WINDOW_SIZE = "4"
$env:MINERU_API_MAX_CONCURRENT_REQUESTS = "1"

Write-Host "Starting MinerU API at http://127.0.0.1:$Port"
Write-Host "CPU pipeline is selected by this project's MINERU_BACKEND=pipeline setting."
& $mineruApi --host 127.0.0.1 --port $Port
