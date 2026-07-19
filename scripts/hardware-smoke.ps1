$ErrorActionPreference = 'Stop'

$gpu = & nvidia-smi --query-gpu=name,power.draw,utilization.gpu,memory.used --format=csv,noheader,nounits
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA telemetry is unavailable.' }
Write-Host "NVIDIA: $gpu" -ForegroundColor Green

try {
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
}
catch {
    throw 'Ollama is not reachable at http://127.0.0.1:11434.'
}

$required = @('qwen2.5:0.5b', 'qwen2.5:1.5b', 'qwen2.5:3b')
$installed = @($tags.models | ForEach-Object { $_.name })
$missing = @($required | Where-Object { $_ -notin $installed })
if ($missing.Count -gt 0) {
    throw "Missing models: $($missing -join ', ')"
}
Write-Host 'Ollama and all GreenFlex models are ready.' -ForegroundColor Green
