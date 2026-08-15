$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

# Kill any existing processes on our ports
$ports = @(8000, 5173)
foreach ($port in $ports) {
    $procs = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $procs) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "Killed stale process $procId on port $port"
        } catch {}
    }
}

# Also kill any lingering uvicorn/uv/pnpm processes from previous runs
Get-Process -Name 'uv','uvicorn','node' -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdLine -and ($cmdLine -match 'greenflex|uvicorn|vite|pnpm')) {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Seconds 1

$api = Start-Process -FilePath 'uv.exe' -ArgumentList 'run','uvicorn','greenflex.api:app','--reload','--host','127.0.0.1','--port','8000' -WorkingDirectory "$Root\backend" -WindowStyle Hidden -PassThru
$worker = Start-Process -FilePath 'uv.exe' -ArgumentList 'run','python','-m','greenflex.worker' -WorkingDirectory "$Root\backend" -WindowStyle Hidden -PassThru
$web = Start-Process -FilePath 'pnpm.cmd' -ArgumentList '--dir','apps/web','dev' -WorkingDirectory $Root -WindowStyle Hidden -PassThru

Write-Host "API PID: $($api.Id)"
Write-Host "Worker PID: $($worker.Id)"
Write-Host "Web PID: $($web.Id)"
Write-Host 'Open http://127.0.0.1:5173'
