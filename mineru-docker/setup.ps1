$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Path "home", "output" -Force | Out-Null

docker compose build
if (-not (Test-Path -LiteralPath (Join-Path $root "home\mineru.json"))) {
    docker compose run --rm `
        -e MINERU_MODEL_SOURCE=modelscope `
        mineru-api `
        mineru-models-download -s modelscope -m pipeline
} else {
    Write-Host "Existing pipeline models detected; skipping model download."
}
docker compose up -d
docker compose ps
