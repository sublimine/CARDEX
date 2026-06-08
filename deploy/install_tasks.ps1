# Install durable Scheduled Tasks for the CARDEX Entity API + delta consumer.
# Direct python actions (no launcher layer) — survive the Claude session because Task
# Scheduler owns them. Defaults in app.py / delta_worker already point at the canonical
# Postgres (localhost:5432) and the host-reachable Redis (localhost:56390), so no env needed.
$WT     = 'C:\Users\elias\projects\cardex-delta'
$py     = 'C:\Users\elias\AppData\Local\Programs\Python\Python311\python.exe'
$status = Join-Path $WT 'logs\install_status.txt'
New-Item -ItemType Directory -Force (Split-Path $status) | Out-Null
"START $(Get-Date -Format o)" | Out-File $status -Encoding utf8

try {
    Unregister-ScheduledTask -TaskName 'CARDEX-EntityAPI'   -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName 'CARDEX-DeltaWorker' -Confirm:$false -ErrorAction SilentlyContinue

    $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 5 -RestartInterval ([TimeSpan]::FromMinutes(1)) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $trg = New-ScheduledTaskTrigger -AtLogOn

    $a1 = New-ScheduledTaskAction -Execute $py -WorkingDirectory $WT `
        -Argument ('-m uvicorn services.entity_api.app:app --app-dir {0} --host 127.0.0.1 --port 8088 --log-level warning' -f $WT)
    Register-ScheduledTask -TaskName 'CARDEX-EntityAPI' -Action $a1 -Trigger $trg -Settings $set -RunLevel Limited -Force | Out-Null
    "registered API" | Out-File $status -Append -Encoding utf8

    $a2 = New-ScheduledTaskAction -Execute $py -WorkingDirectory $WT -Argument '-m scrapers.delta.delta_worker'
    Register-ScheduledTask -TaskName 'CARDEX-DeltaWorker' -Action $a2 -Trigger $trg -Settings $set -RunLevel Limited -Force | Out-Null
    "registered worker" | Out-File $status -Append -Encoding utf8

    Start-ScheduledTask -TaskName 'CARDEX-EntityAPI'
    Start-ScheduledTask -TaskName 'CARDEX-DeltaWorker'
    "started both" | Out-File $status -Append -Encoding utf8
}
catch {
    "ERROR: $($_.Exception.Message)" | Out-File $status -Append -Encoding utf8
}
"DONE $(Get-Date -Format o)" | Out-File $status -Append -Encoding utf8
