$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

New-Item -ItemType Directory -Force -Path "$Root\backend\data", "$Root\artifacts", 'D:\GreenFlex\models' | Out-Null

Push-Location "$Root\backend"
try {
    uv sync --all-groups
    uv run alembic upgrade head
    uv run python -m greenflex.seed
}
finally {
    Pop-Location
}

Push-Location $Root
try {
    pnpm.cmd install --frozen-lockfile
}
finally {
    Pop-Location
}

Write-Host 'Bootstrap complete.' -ForegroundColor Green
