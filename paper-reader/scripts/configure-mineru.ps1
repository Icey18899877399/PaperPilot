param(
    [string]$BaseUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $envPath
}

$updates = [ordered]@{
    MINERU_API_URL = $BaseUrl.TrimEnd('/')
    MINERU_BACKEND = "pipeline"
    MINERU_LANGUAGE = "ch"
    MINERU_TIMEOUT_SECONDS = "3600"
}
$lines = [System.Collections.Generic.List[string]]::new()
Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object { $lines.Add($_) }
foreach ($name in $updates.Keys) {
    $replacement = "$name=$($updates[$name])"
    $matched = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^$([regex]::Escape($name))=") {
            $lines[$index] = $replacement
            $matched = $true
            break
        }
    }
    if (-not $matched) { $lines.Add($replacement) }
}
[IO.File]::WriteAllLines(
    $envPath,
    [string[]]$lines,
    [Text.UTF8Encoding]::new($false)
)
Write-Host "MinerU configuration saved to $envPath"
Write-Host "MINERU_API_URL=$($updates.MINERU_API_URL)"
