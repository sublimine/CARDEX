<#
.SYNOPSIS
  Regenerates the CARDEX dashboard from the live DB right now and opens it
  in the default browser. Use this for an on-demand, up-to-the-second view
  (independent of the 15-minute auto-refresh).

.NOTES
  Run: powershell -ExecutionPolicy Bypass -File open_dashboard.ps1
#>

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Generator = Join-Path $ScriptDir 'generate.py'
$Html      = Join-Path $ScriptDir 'cardex_control.html'

$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw 'python not found on PATH.' }

Write-Host 'Generating dashboard from live database...'
& $Python $Generator
if ($LASTEXITCODE -ne 0) { throw "Generation failed (exit $LASTEXITCODE)." }

Write-Host "Opening $Html"
Invoke-Item $Html
