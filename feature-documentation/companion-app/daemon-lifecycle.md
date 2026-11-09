# Daemon-Lebenszyklus: Einzelinstanz, Stop und Waisenschutz

Stand: 2026-11-09

Regelt, wie genau ein Daemon den IPC-Socket besitzt und wie er sich auch dann
beendet, wenn BLE hängt. Code: `daemon/clawdmeter_daemon/ipc_server.py`,
`daemon/clawdmeter_daemon/polling.py`. Tests: `daemon/tests/test_ipc_socket.py`,
`daemon/tests/test_shutdown.py`.

## Vorfall (2026-10-30 bis 2026-11-09)

1. Der Daemon hing nach dem Ruhezustand in `BleakClient.connect()`
   (CoreBluetooth kehrte nie zurück).
2. launchd schickte SIGTERM. Der Handler setzte nur `stop_event`, das der
   hängende `connect()` nicht beachtete.
3. launchd beendete den PyInstaller-Bootloader (Elternprozess) per SIGKILL.
   Der Python-Kindprozess lief als Waise weiter (PPID 1) und hielt
   `daemon.sock`.
4. Jeder neue Daemon fand den Socket per `connect()` „lebendig“ und schaltete
   sein IPC ab. Die Companion-App sprach mit dem Waisen, der jede Verbindung
   sofort schloss (`stop_event` gesetzt). Ergebnis: Polling lief, IPC war tot.

## Regeln

### Socket-Übernahme (`ipc_server._serve_unix`)

- Ein bestehender Socket gilt nur dann als belegt, wenn `_daemon_responds()`
  auf `status` innerhalb von `PROBE_TIMEOUT` (2 s) eine Antwort mit
  `ok: true` und `running: true` bekommt.
- Nimmt der Socket Verbindungen an, antwortet aber nicht (hängt, stoppt),
  wird er ersetzt. Log: `nimmt Verbindungen an, antwortet aber nicht`.
- Die Probe ist asynchron, damit ein Server im selben Event-Loop (Tests)
  antworten kann.
- `[ipc] listening on …` wird erst nach erfolgreichem Binden geloggt.
- `stop()` löscht den Pfad weiterhin nur, wenn er auf den eigenen Socket
  zeigt (`st_dev`/`st_ino`).

### BLE-Verbindungsaufbau (`polling._connect_or_stop`)

- `connect()` läuft gegen `stop_event` und `CONNECT_TIMEOUT` (30 s).
- Stop während des Aufbaus: `connect_and_run` gibt `True` zurück, ohne
  den Adress-Cache zu verwerfen.
- Timeout: `asyncio.TimeoutError` → regulärer Pfad `Connection failed`.

### Stop-Frist (`polling._start_shutdown_deadline`)

- Das erste SIGTERM/SIGINT startet einen Thread-Timer. Ist der Prozess nach
  `SHUTDOWN_GRACE` (10 s, unter launchds `ExitTimeOut` von 20 s) noch da,
  beendet `os._exit(1)` ihn hart. Der Timer läuft im eigenen Thread, damit ein
  blockierter Event-Loop ihn nicht aufhält.

### Elternprozess-Überwachung (`polling._watch_parent`)

- Ist beim Start die PPID ≠ 1 (onefile-Bootloader), prüft eine Task alle
  `PARENT_CHECK_INTERVAL` (5 s), ob sie sich ändert. Wechselt sie, setzt sie
  `stop_event`. Log: `Elternprozess beendet — Daemon stoppt`.
- Direkt von launchd gestartet (PPID 1) und unter Windows inaktiv.

## Diagnose

```bash
pgrep -fl clawdmeter-daemon          # erwartet: genau ein Paar Bootloader→Kind
lsof -U | grep clawdmeter/daemon.sock # Besitzer des Sockets
```

Ein einzelner Prozess mit PPID 1 ohne Bootloader-Partner ist ein Waise.
