param([string]$Python = 'python')

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$frontend = Join-Path $root 'frontend'
$vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'
$logs = Join-Path $root 'data/local-run'
$owned = @()

function Get-HttpStatus([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -SkipHttpErrorCheck -TimeoutSec 3).StatusCode }
    catch { return 0 }
}

try {
    & (Join-Path $PSScriptRoot 'check-local.ps1') -Python $Python
    if ($LASTEXITCODE -ne 0) { throw '本地依赖或模型检查未通过' }
    if (!(Test-Path -LiteralPath $vite)) { throw '缺少 frontend/node_modules，请先在 frontend 目录安装 npm 依赖' }
    $node = (Get-Command node -ErrorAction Stop).Source
    New-Item -ItemType Directory -Path $logs -Force | Out-Null

    if ((Get-HttpStatus 'http://127.0.0.1:8000/health') -eq 0) {
        $backend = Start-Process -FilePath $Python -ArgumentList @('-m', 'uvicorn', 'backend.src.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'backend.stdout.log') -RedirectStandardError (Join-Path $logs 'backend.stderr.log')
        $owned += $backend
        Write-Output "backend_started_pid=$($backend.Id)"
    } else { Write-Output 'backend_existing=True' }

    if ((Get-HttpStatus 'http://127.0.0.1:5173/') -eq 0) {
        $web = Start-Process -FilePath $node -ArgumentList @($vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'frontend.stdout.log') -RedirectStandardError (Join-Path $logs 'frontend.stderr.log')
        $owned += $web
        Write-Output "frontend_started_pid=$($web.Id)"
    } else { Write-Output 'frontend_existing=True' }

    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if ((Get-HttpStatus 'http://127.0.0.1:8000/health/ready') -eq 200 -and (Get-HttpStatus 'http://127.0.0.1:5173/') -eq 200) { break }
        foreach ($process in $owned) {
            $process.Refresh()
            if ($process.HasExited) { throw "子进程提前退出（PID $($process.Id)），请查看 data/local-run 日志" }
        }
        Start-Sleep -Seconds 1
    }
    if ((Get-HttpStatus 'http://127.0.0.1:8000/health/ready') -ne 200 -or (Get-HttpStatus 'http://127.0.0.1:5173/') -ne 200) { throw '服务未在 120 秒内就绪，请查看 data/local-run 日志' }
    Write-Output 'local_ready=True frontend=http://127.0.0.1:5173/ backend=http://127.0.0.1:8000/'
    Write-Output '按 Ctrl+C 退出；只会停止由本脚本启动的进程。'
    while ($true) {
        foreach ($process in $owned) {
            $process.Refresh()
            if ($process.HasExited) { throw "子进程已退出（PID $($process.Id)）" }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    foreach ($process in $owned) {
        $process.Refresh()
        if (!$process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    }
}
