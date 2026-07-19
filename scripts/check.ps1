$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$Root = Split-Path -Parent $PSScriptRoot

Push-Location "$Root\backend"
try {
    uv run ruff check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run ruff format --check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run mypy src
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run pytest --cov=greenflex --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    uv run pip-audit --skip-editable
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Push-Location $Root
try {
    pnpm.cmd lint:web
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pnpm.cmd test:web
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pnpm.cmd build:web
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pnpm.cmd audit --audit-level high
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Host 'All checks passed.' -ForegroundColor Green
