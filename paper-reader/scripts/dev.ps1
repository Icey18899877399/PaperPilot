$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$Root\backend'; uvicorn app.main:app --reload"
)

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$Root\frontend'; npm run dev"
)

Write-Host "后端：http://localhost:8000/docs"
Write-Host "前端：http://localhost:5173"

