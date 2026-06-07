<#
.SYNOPSIS
  Registers the Windows Scheduled Task that keeps cardex_supervisor alive 24/7:
  - trigger AT SYSTEM STARTUP (survives reboot)
  - trigger ONCE NOW repeating EVERY 5 MINUTES (healthcheck / crash recovery)
  Both run ensure.py, which launches the supervisor only if it is not already alive.

  Runs whether the user is logged on or not (survives logout/idle), as the current
  user. Pure Python underneath — zero Claude/tokens.

.NOTES
  Start:  powershell -ExecutionPolicy Bypass -File register_supervisor.ps1
  Stop:   powershell -ExecutionPolicy Bypass -File unregister_supervisor.ps1
#>
$ErrorActionPreference = 'Stop'
$TaskName  = 'CARDEX Supervisor'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Ensure    = Join-Path $ScriptDir 'ensure.py'

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw 'python not found on PATH.' }
if (-not (Test-Path $Ensure)) { throw "ensure.py not found: $Ensure" }

Write-Host "Python : $Python"
Write-Host "Ensure : $Ensure"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host 'removed previous task'
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Ensure`"" -WorkingDirectory (Split-Path -Parent $ScriptDir)

# Non-admin user: single Once+5-min-repetition trigger (the proven-working pattern;
# AtLogOn/AtStartup/S4U/unlimited-timeout all need admin and were denied). The 5-min
# healthcheck runs ensure.py (fast exit) which relaunches the detached supervisor if
# it died — surviving crashes/idle while the (always-on) PC is logged on. Repetition
# with StartWhenAvailable also resumes after a reboot+login.
$tPoll = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $tPoll `
    -Settings $settings -Principal $principal `
    -Description 'Keeps cardex_supervisor alive (5-min healthcheck). Governs all CARDEX workers.' | Out-Null

Write-Host 'Registered. Starting now...'
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 4
Write-Host ''
Write-Host '====================================================================='
Write-Host ' CARDEX Supervisor is ACTIVE (boot + every 5 min, survives logout).'
Write-Host "  State : $((Split-Path -Parent $ScriptDir))\supervisor\supervisor_state.json"
Write-Host "  Logs  : $ScriptDir\logs\"
Write-Host '  Stop  : powershell -ExecutionPolicy Bypass -File unregister_supervisor.ps1'
Write-Host '====================================================================='
