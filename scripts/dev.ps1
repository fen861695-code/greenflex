$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

$api = Start-Process -FilePath 'uv.exe' -ArgumentList 'run','uvicorn','greenflex.api:app','--reload','--host','127.0.0.1','--port','8000' -WorkingDirectory "$Root\backend" -WindowStyle Hidden -PassThru
$worker = Start-Process -FilePath 'uv.exe' -ArgumentList 'run','python','-m','greenflex.worker' -WorkingDirectory "$Root\backend" -WindowStyle Hidden -PassThru
$web = Start-Process -FilePath 'pnpm.cmd' -ArgumentList '--dir','apps/web','dev' -WorkingDirectory $Root -WindowStyle Hidden -PassThru

Write-Host "API PID: $($api.Id)"
Write-Host "Worker PID: $($worker.Id)"
Write-Host "Web PID: $($web.Id)"
Write-Host 'Open http://127.0.0.1:5173'

