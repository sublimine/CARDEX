@echo off
REM Stop the persistent CARDEX Entity API + delta consumer.
REM Kills the uvicorn listening on 8088 and the delta_worker python process.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8088" ^| findstr LISTENING') do taskkill /F /PID %%p
wmic process where "name='python.exe' and commandline like '%%scrapers.delta.delta_worker%%'" call terminate >nul 2>&1
echo CARDEX entity services stopped.
