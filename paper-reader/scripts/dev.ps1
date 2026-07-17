$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

$BackendOut = Join-Path $Root "dev-backend.out.log"
$BackendErr = Join-Path $Root "dev-backend.err.log"
$FrontendOut = Join-Path $Root "dev-frontend.out.log"
$FrontendErr = Join-Path $Root "dev-frontend.err.log"

Remove-Item -LiteralPath $BackendOut, $BackendErr, $FrontendOut, $FrontendErr -ErrorAction SilentlyContinue

Start-Process -FilePath (Join-Path $Root "backend\.venv\Scripts\python.exe") -ArgumentList @(
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000"
) -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Hidden -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr

Start-Process -FilePath "npm.cmd" -ArgumentList @(
    "run",
    "dev",
    "--",
    "--host",
    "127.0.0.1",
    "--port",
    "5173"
) -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden -RedirectStandardOutput $FrontendOut -RedirectStandardError $FrontendErr

Write-Host "Backend: http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:5173"
Write-Host "Backend logs: $BackendOut / $BackendErr"
Write-Host "Frontend logs: $FrontendOut / $FrontendErr"
