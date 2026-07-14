$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".env"

$SecureKey = Read-Host "Enter DeepSeek API Key (input is hidden)" -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)

try {
    $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    if ([string]::IsNullOrWhiteSpace($PlainKey)) {
        throw "API Key cannot be empty"
    }
    if ($PlainKey.Length -lt 20) {
        throw "API Key appears too short. Paste the complete key and try again."
    }

    $ModelInput = Read-Host "Model (press Enter for deepseek-v4-flash)"
    $Model = if ([string]::IsNullOrWhiteSpace($ModelInput)) {
        "deepseek-v4-flash"
    } else {
        $ModelInput.Trim()
    }

    $Existing = @()
    if (Test-Path -LiteralPath $EnvPath) {
        $Existing = Get-Content -LiteralPath $EnvPath -Encoding UTF8 |
            Where-Object {
                $_ -notmatch "^\s*DEEPSEEK_(API_KEY|BASE_URL|MODEL|THINKING)\s*="
            }
    }

    $Lines = @(
        $Existing
        "DEEPSEEK_API_KEY=$PlainKey"
        "DEEPSEEK_BASE_URL=https://api.deepseek.com"
        "DEEPSEEK_MODEL=$Model"
        "DEEPSEEK_THINKING=false"
    )
    [IO.File]::WriteAllLines(
        $EnvPath,
        [string[]]$Lines,
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host "DeepSeek configuration saved to: $EnvPath"
    Write-Host "Model: $Model"
    Write-Host "API Key length check passed: $($PlainKey.Length) characters"
} finally {
    if ($Pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }
    $PlainKey = $null
}
