<#
.SYNOPSIS
  Stops and removes the CARDEX dashboard auto-refresh scheduled task.

.NOTES
  Run: powershell -ExecutionPolicy Bypass -File unregister_refresh.ps1
#>

$ErrorActionPreference = 'Stop'
$TaskName = 'CARDEX Dashboard Refresh'

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "No task named '$TaskName' is registered. Nothing to do."
    return
}

try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Stopped and removed '$TaskName'. Auto-refresh is OFF."
Write-Host 'The last generated cardex_control.html is left in place; it simply stops updating.'
