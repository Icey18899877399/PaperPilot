param(
    [string]$BaseUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"
$response = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/health" -Method Get
$response | ConvertTo-Json -Depth 5
