# Windows installer for Clawdmeter daemon (Python + bleak + Task Scheduler).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
#
# Uninstall:
#   schtasks /Delete /TN "ClawdmeterDaemon" /F

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir     = Join-Path $ScriptDir 'daemon\.venv'
$DaemonPy    = Join-Path $ScriptDir 'daemon\clawdmeter_daemon.py'
$PythonBin   = Join-Path $VenvDir 'Scripts\python.exe'
$PythonwBin  = Join-Path $VenvDir 'Scripts\pythonw.exe'
$TaskName    = 'ClawdmeterDaemon'
$LogDir      = Join-Path $env:LOCALAPPDATA 'clawdmeter\logs'

Write-Host '=== Clawdmeter Windows install ==='
Write-Host ''

# [1/6] Prerequisites
Write-Host '[1/6] Checking prerequisites...'
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error 'Python 3.9+ not found on PATH. Install it from https://www.python.org/ (tick "Add to PATH"), then re-run.'
}
$pythonVersion = & $pythonCmd.Source --version 2>&1
Write-Host "  $pythonVersion"
Write-Host '  OK'
Write-Host ''

# [2/6] Virtualenv
Write-Host '[2/6] Creating Python virtualenv at daemon\.venv ...'
if (-not (Test-Path $VenvDir)) {
    & $pythonCmd.Source -m venv $VenvDir
}
if (-not (Test-Path $PythonBin)) {
    Write-Error "venv creation failed: $PythonBin missing"
}
& $PythonBin -m pip install --quiet --upgrade pip
& $PythonBin -m pip install --quiet 'bleak>=0.22' 'httpx>=0.27' "tomli>=2.0;python_version<'3.11'"
Write-Host "  OK ($PythonBin)"
Write-Host ''

# [3/6] Optional provider dependencies
Write-Host '[3/6] Optional provider dependencies'
Write-Host '  AWS Bedrock-Adapter ist aktuell deaktiviert (kein IAM-Pfad konfiguriert).'
Write-Host '  Falls du ihn spater reaktivierst, installiere boto3 mit:'
Write-Host "    & '$PythonBin' -m pip install 'boto3>=1.34'"
Write-Host ''

# [4/6] Setup wizard
Write-Host '[4/6] Running interactive setup wizard...'
& $PythonBin $DaemonPy setup
Write-Host ''

# [5/6] Log directory
Write-Host '[5/6] Preparing log directory...'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-Host "  $LogDir"
Write-Host ''

# [6/6] Scheduled Task
Write-Host '[6/6] Registering Scheduled Task...'
$runner = if (Test-Path $PythonwBin) { $PythonwBin } else { $PythonBin }
$logFile = Join-Path $LogDir 'daemon.log'

schtasks /Query /TN $TaskName >$null 2>&1
if ($LASTEXITCODE -eq 0) {
    schtasks /Delete /TN $TaskName /F | Out-Null
}

$psCommand = "& '$runner' '$DaemonPy' run *>> '$logFile'"
$action    = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"$psCommand`"" `
    -WorkingDirectory $ScriptDir

$trigger   = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Clawdmeter: polls LLM providers and pushes usage to the ESP32 over BLE.' | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "  Task '$TaskName' registered and started."
Write-Host ''

Write-Host '=== Done ==='
Write-Host ''
Write-Host 'Useful commands:'
Write-Host "  & '$PythonBin' '$DaemonPy' doctor             # config + enabled providers"
Write-Host "  & '$PythonBin' '$DaemonPy' setup              # re-run setup wizard"
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST     # task status"
Write-Host "  schtasks /End   /TN $TaskName                 # stop"
Write-Host "  schtasks /Run   /TN $TaskName                 # start"
Write-Host "  schtasks /Delete /TN $TaskName /F             # uninstall"
Write-Host ''
Write-Host 'Logs:'
Write-Host "  $logFile"
Write-Host '  (tail with:  Get-Content -Wait -Tail 50 ''<above>'')'
Write-Host ''
Write-Host 'First-time Bluetooth pairing (after firmware is flashed):'
Write-Host '  1. Power on the device.'
Write-Host '  2. Open Settings -> Bluetooth & devices -> Add device -> Bluetooth.'
Write-Host "  3. Pair 'Clawdmeter'."
Write-Host '  4. The daemon will discover it within ~30 s and start polling.'
Write-Host ''
