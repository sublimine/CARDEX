# CARDEX Entity API + delta consumer — persistent launcher.
# Started by the Windows Scheduled Task "CARDEX-EntityAPI" so the processes survive the
# Claude session (they are spawned by Task Scheduler, not the agent's job object).
# Idempotent: frees port 8088 first, then (re)starts the API + delta_worker detached.
$ErrorActionPreference = 'SilentlyContinue'

$WT   = 'C:\Users\elias\projects\cardex-delta'
$py   = 'C:\Users\elias\AppData\Local\Programs\Python\Python311\python.exe'
$logs = Join-Path $WT 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null

$env:DATABASE_URL    = 'postgresql://cardex:cardex_dev_only@localhost:5432/cardex'  # canonical PG (real data)
$env:REDIS_URL       = 'redis://localhost:56390'                                    # host-reachable redis
$env:PYTHONIOENCODING = 'utf-8'                                                      # cp1252 console crashes on unicode
$env:PYTHONPATH      = $WT

# Idempotent restart: free 8088
Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# 1) Per-entity inventory API (read-only over Postgres)
Start-Process -FilePath $py -WorkingDirectory $WT -WindowStyle Hidden `
  -ArgumentList '-m','uvicorn','services.entity_api.app:app','--app-dir',$WT,
                '--host','127.0.0.1','--port','8088','--log-level','warning' `
  -RedirectStandardOutput (Join-Path $logs 'entity_api.out.log') `
  -RedirectStandardError  (Join-Path $logs 'entity_api.err.log')

# 2) Always-on delta consumer (applies SEEN/GONE in real time)
Start-Process -FilePath $py -WorkingDirectory $WT -WindowStyle Hidden `
  -ArgumentList '-m','scrapers.delta.delta_worker' `
  -RedirectStandardOutput (Join-Path $logs 'delta_worker.out.log') `
  -RedirectStandardError  (Join-Path $logs 'delta_worker.err.log')
