<#
.SYNOPSIS  Stops and removes the CARDEX Supervisor scheduled task, and stops the
           running supervisor (governed workers keep their last state).
.NOTES     powershell -ExecutionPolicy Bypass -File unregister_supervisor.ps1
#>
$ErrorActionPreference = 'Stop'
$TaskName = 'CARDEX Supervisor'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed task '$TaskName'"
} else {
    Write-Host "no task '$TaskName'"
}
$pidFile = Join-Path $ScriptDir 'pids\supervisor.pid'
if (Test-Path $pidFile) {
    $sp = Get-Content $pidFile
    try { Stop-Process -Id $sp -Force -ErrorAction SilentlyContinue; Write-Host "stopped supervisor pid=$sp" } catch {}
}
Write-Host 'Supervisor OFF. Re-arm with register_supervisor.ps1.'
