# Windows installer for Clawdmeter daemon (Python + bleak + Task Scheduler).
# Mirrors install-mac.sh / install.sh but uses a per-user scheduled task.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
#
# What this does:
#   1. Verifies Python 3.9+ is on PATH
#   2. Creates daemon\.venv and installs bleak + httpx
#   3. Runs a priming scan so Windows surfaces the BLE permission prompt
#   4. Registers a per-user Scheduled Task that starts the daemon at logon
#      and restarts it if it crashes
#
# Uninstall:
#   schtasks /Delete /TN "ClaudeUsageDaemon" /F

$ErrorActionPreference = 'Stop'

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir     = Join-Path $ScriptDir 'daemon\.venv'
$DaemonPy    = Join-Path $ScriptDir 'daemon\claude_usage_daemon.py'
$PythonBin   = Join-Path $VenvDir 'Scripts\python.exe'
$PythonwBin  = Join-Path $VenvDir 'Scripts\pythonw.exe'
$TaskName    = 'ClaudeUsageDaemon'
$LogDir      = Join-Path $env:LOCALAPPDATA 'claude-usage-monitor\logs'

Write-Host '=== Clawdmeter Windows install ==='
Write-Host ''

# [1/5] Prerequisites
Write-Host '[1/5] Checking prerequisites...'
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Error 'Python 3.9+ not found on PATH. Install it from https://www.python.org/ (tick "Add to PATH"), then re-run.'
}
$pythonVersion = & $pythonCmd.Source --version 2>&1
Write-Host "  $pythonVersion"

$credPath = Join-Path $env:USERPROFILE '.claude\.credentials.json'
if (-not (Test-Path $credPath)) {
    Write-Warning "$credPath not found."
    Write-Host '  Sign in via Claude Code first, then re-run this installer.'
    Write-Host '  Continuing anyway - the daemon will retry on each poll.'
}
Write-Host '  OK'
Write-Host ''

# [2/5] Virtualenv
Write-Host '[2/5] Creating Python virtualenv at daemon\.venv ...'
if (-not (Test-Path $VenvDir)) {
    & $pythonCmd.Source -m venv $VenvDir
}
if (-not (Test-Path $PythonBin)) {
    Write-Error "venv creation failed: $PythonBin missing"
}
& $PythonBin -m pip install --quiet --upgrade pip
& $PythonBin -m pip install --quiet 'bleak>=0.22' 'httpx>=0.27'
Write-Host "  OK ($PythonBin)"
Write-Host ''

# [3/5] Log directory
Write-Host '[3/5] Preparing log directory...'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Write-Host "  $LogDir"
Write-Host ''

# [4/5] BLE permission priming
Write-Host '[4/5] Bluetooth permission check...'
Write-Host '  On Windows 10/11, BLE scanning requires the user to allow'
Write-Host '  "Apps can access your Bluetooth" under Settings -> Privacy & security'
Write-Host '  -> Bluetooth. We will run the daemon interactively once so any'
Write-Host '  prompt appears in your session. Press Ctrl+C after you see "Scanning..."'
Write-Host '  (or once a payload is sent) to continue.'
Write-Host ''
$ans = Read-Host 'Run a permission-priming scan now? [Y/n]'
if ($ans -notmatch '^[Nn]') {
    try {
        & $PythonBin $DaemonPy
    } catch {
        # Ctrl+C from the user; expected
    }
}
Write-Host ''

# [5/5] Scheduled Task
Write-Host '[5/5] Registering Scheduled Task...'
# Use pythonw.exe (no console window) for the background task; fall back to python.exe.
$runner = if (Test-Path $PythonwBin) { $PythonwBin } else { $PythonBin }
$logFile = Join-Path $LogDir 'daemon.log'

# Delete any existing task with the same name (idempotent re-install).
schtasks /Query /TN $TaskName >$null 2>&1
if ($LASTEXITCODE -eq 0) {
    schtasks /Delete /TN $TaskName /F | Out-Null
}

# Wrap the daemon in a hidden PowerShell so we can redirect stdout/stderr to a
# rotating-ish log file. pythonw.exe alone has no visible output; without this
# wrapper there'd be no way to see what the daemon is doing.
$psCommand = "& '$runner' '$DaemonPy' *>> '$logFile'"
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
    -Description 'Clawdmeter: polls Claude API usage and pushes it to the ESP32 over BLE.' | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "  Task '$TaskName' registered and started."
Write-Host ''

Write-Host '=== Done ==='
Write-Host ''
Write-Host 'First-time Bluetooth pairing (after firmware is flashed):'
Write-Host '  1. Power on the device.'
Write-Host '  2. Open Settings -> Bluetooth & devices -> Add device -> Bluetooth.'
Write-Host "  3. Pair 'Claude Controller'."
Write-Host '  4. The daemon will discover it within ~30 s and start polling.'
Write-Host ''
Write-Host 'Useful commands:'
Write-Host "  schtasks /Query /TN $TaskName /V /FO LIST    # task status"
Write-Host "  schtasks /End   /TN $TaskName                # stop"
Write-Host "  schtasks /Run   /TN $TaskName                # start"
Write-Host "  schtasks /Delete /TN $TaskName /F            # uninstall"
Write-Host ''
Write-Host 'Logs:'
Write-Host "  $logFile"
Write-Host '  (tail with:  Get-Content -Wait -Tail 50 ''<above>'')'
Write-Host ''
Write-Host 'To see live output, run the daemon interactively:'
Write-Host "  & '$PythonBin' '$DaemonPy'"
