param(
    [string]$VenvPath = ".venv-mineru"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $projectRoot $VenvPath

Write-Host "MinerU installation can require 20GB+ disk space."
Write-Host "Creating isolated environment: $venv"
python -m venv $venv
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip uv
& $python -m uv pip install --python $python -U "mineru[all]"

Write-Host "MinerU installed. Start it with scripts\start-mineru.ps1"
