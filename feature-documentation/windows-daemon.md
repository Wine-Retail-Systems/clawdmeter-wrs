# Windows-Daemon

Portierung des Host-Daemons auf Windows 10/11. Nutzt denselben Python-Daemon
wie macOS — die Cross-Platform-Bibliothek `bleak` wählt den
Backend (WinRT auf Windows, CoreBluetooth auf macOS) automatisch.

## Komponenten

- [`daemon/claude_usage_daemon.py`](../daemon/claude_usage_daemon.py) — geteilter Python-Daemon (macOS + Windows). Plattformweichen sind:
  - **Token-Quelle:** `read_token()` ruft auf macOS `security find-generic-password` auf, sonst `_read_token_file()`. Unter Windows liest dieser dieselbe Datei wie auf Linux: `Path.home() / ".claude" / ".credentials.json"` löst zu `%USERPROFILE%\.claude\.credentials.json` auf. Der Pfad ist via Env-Var `CLAUDE_CONFIG_DIR` überschreibbar.
  - **State-Cache:** `_state_dir()` legt die BLE-Adresse unter Windows in `%LOCALAPPDATA%\claude-usage-monitor\`, unter Linux/macOS in `~/.config/claude-usage-monitor/` ab.
- [`install-windows.ps1`](../install-windows.ps1) — Installer. Legt `daemon\.venv` an, installiert `bleak>=0.22` + `httpx>=0.27`, primt die BLE-Permission durch interaktiven Start, registriert einen per-User Scheduled Task `ClaudeUsageDaemon` mit `AtLogOn`-Trigger und Auto-Restart (`RestartCount=999`, `RestartInterval=1min`).

## Service-Mechanismus

**Task Scheduler** statt Windows Service, weil BLE-Scanning auf Windows an die User-Session gebunden ist. `LogonType Interactive` + `RunLevel Limited` lässt den Daemon im User-Kontext laufen, ohne Admin-Rechte.

Die Action ist nicht direkt `pythonw.exe`, sondern ein `powershell.exe -WindowStyle Hidden -Command "& '<pythonw>' '<daemon>' *>> '<logfile>'"`-Wrapper. Grund: `pythonw.exe` verwirft stdout, also würde sonst keine Diagnose möglich sein. Der Wrapper redirected alle Streams (`*>>`) in `%LOCALAPPDATA%\claude-usage-monitor\logs\daemon.log`.

## Voraussetzungen

- Windows 10 Build 1903+ oder Windows 11 (für WinRT-BLE)
- Python 3.9+ auf `PATH`
- BLE-fähiger Adapter
- Erstmaliges Pairing über *Einstellungen → Bluetooth & Geräte → Gerät hinzufügen → Bluetooth*

## Bekannte Limitationen

- **Kein graceful SIGTERM:** Windows kennt das Signal nur als Konstante. Beim `schtasks /End` wird der Prozess hart beendet — kein sauberes BLE-Disconnect. Ist akzeptabel, weil der Daemon bei Verlust der Verbindung sowieso reconnecten muss.
- **Hidden-PowerShell flackert beim Login kurz auf:** Lebensdauer ~200 ms. Eleganter wäre ein VBS-Wrapper über `wscript.exe`, aber der Mehraufwand lohnt nicht.
- **Adapter-Pairing:** Beim Austausch der ESP-Hardware muss der alte Eintrag manuell aus den Bluetooth-Einstellungen entfernt werden, sonst gibt es eine Phase, in der zwei „Claude Controller" sichtbar sind und der Daemon ggf. den toten zuerst probiert. Der Cache-Invalidierungs-Pfad in `claude_usage_daemon.py` löscht dann zumindest die gecachte Adresse und scannt frisch.
