param(
    [string]$CachePath = 'D:\GreenFlex\models'
)

$ErrorActionPreference = 'Stop'
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    throw 'Ollama is not installed. Install the official Ollama.Ollama winget package first.'
}

New-Item -ItemType Directory -Force -Path $CachePath | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $CachePath, 'User')
$env:OLLAMA_MODELS = $CachePath

$models = @('qwen2.5:0.5b', 'qwen2.5:1.5b', 'qwen2.5:3b')
foreach ($model in $models) {
    Write-Host "Pulling $model..." -ForegroundColor Cyan
    & $ollama.Source pull $model
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull $model."
    }
}

Write-Host "Models are stored in $CachePath" -ForegroundColor Green
& $ollama.Source list
