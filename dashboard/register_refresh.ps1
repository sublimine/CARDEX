<#
.SYNOPSIS
  Registers a Windows Scheduled Task that regenerates the CARDEX control
  dashboard every 15 minutes, reading the live database on the HOST.

.DESCRIPTION
  This is the auto-refresh engine. It runs ON THE HOST (not inside any
  container and NOT via Cowork's scheduler, which is sandboxed and cannot
  reach the local database). The task calls `python generate.py`, which queries
  PostgreSQL / Redis / SQLite / Docker and rewrites cardex_control.html.

  Safe to re-run: it removes any prior task with the same name first.

.NOTES
  Start:  powershell -ExecutionPolicy Bypass -File register_refresh.ps1
  Stop:   powershell -ExecutionPolicy Bypass -File unregister_refresh.ps1
#>

$ErrorActionPreference = 'Stop'

$TaskName  = 'CARDEX Dashboard Refresh'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Generator = Join-Path $ScriptDir 'generate.py'

# Resolve an absolute python path so the task does not depend on PATH at run time.
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw 'python not found on PATH. Install Python 3 or adjust this script.' }

if (-not (Test-Path $Generator)) { throw "Generator not found: $Generator" }

Write-Host "Python    : $Python"
Write-Host "Generator : $Generator"
Write-Host "Task name : $TaskName"

# Remove any existing task with this name (idempotent re-register).
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host 'Removing previous task...'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Generator`"" -WorkingDirectory $ScriptDir

# Repeat every 15 minutes, starting now, for ~10 years (effectively indefinite;
# TimeSpan.MaxValue produces an out-of-range XML duration that Task Scheduler
# rejects). The repetition is passed as a parameter because the trigger object
# does not expose a settable RepetitionInterval property on PowerShell 5.1.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

# Run as the current interactive user so it inherits docker access.
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Regenerates the CARDEX owner control dashboard from the live DB every 15 minutes.' | Out-Null

Write-Host ''
Write-Host 'Registered. Running once now to produce the first dashboard...'
Start-ScheduledTask -TaskName $TaskName

Start-Sleep -Seconds 2
$html = Join-Path $ScriptDir 'cardex_control.html'
Write-Host ''
Write-Host '====================================================================='
Write-Host ' CARDEX dashboard auto-refresh is ACTIVE (every 15 minutes).'
Write-Host ''
Write-Host "  Open the dashboard:  $html"
Write-Host '  Stop auto-refresh :  powershell -ExecutionPolicy Bypass -File unregister_refresh.ps1'
Write-Host '  View task         :  Get-ScheduledTask -TaskName ''CARDEX Dashboard Refresh'''
Write-Host '====================================================================='
