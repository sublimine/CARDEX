@echo off
REM CARDEX Entity API + delta consumer — durable launcher (run by Scheduled Task
REM "CARDEX-EntityServices", ONLOGON). Idempotent: frees port 8088 then starts both
REM processes detached via `start /b`, so they survive the launching shell.
cd /d C:\Users\elias\projects\cardex-delta
set DATABASE_URL=postgresql://cardex:cardex_dev_only@localhost:5432/cardex
set REDIS_URL=redis://localhost:56390
set PYTHONIOENCODING=utf-8
set PYTHONPATH=C:\Users\elias\projects\cardex-delta
set PY=C:\Users\elias\AppData\Local\Programs\Python\Python311\python.exe
if not exist logs mkdir logs

REM free port 8088 (idempotent restart)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8088" ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1

REM 1) per-entity inventory API (read-only over canonical Postgres)
start "cardex-entity-api" /b "%PY%" -m uvicorn services.entity_api.app:app --app-dir C:\Users\elias\projects\cardex-delta --host 127.0.0.1 --port 8088 --log-level warning >> logs\entity_api.log 2>&1

REM 2) always-on delta consumer (applies SEEN/GONE in real time)
start "cardex-delta-worker" /b "%PY%" -m scrapers.delta.delta_worker >> logs\delta_worker.log 2>&1
