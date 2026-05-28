# Companion ↔ Daemon — IPC-Protokoll

Stand: 2026-05-28 (Phase 2)

Bidirektionales JSON-Lines-Protokoll. Die Companion-App (Rust) ist Client,
der Python-Daemon ist Server.

## Transport

| Plattform | Endpoint                                                                   |
|-----------|---------------------------------------------------------------------------|
| macOS     | Unix-Socket: `~/Library/Application Support/clawdmeter/daemon.sock` (Mode 0600) |
| Linux     | Unix-Socket: `~/.config/clawdmeter/daemon.sock` (Mode 0600)               |
| Windows   | Named-Pipe: `\\.\pipe\clawdmeter-daemon`                                  |

Auf macOS/Linux gilt: Daemon und App laufen unter derselben UID — keine
weiteren ACL-Maßnahmen nötig. Auf Windows liegt die Pipe im default-DACL
des Users, der den Daemon-Task startet.

## Frame-Format

Jeder Frame ist genau eine Zeile UTF-8 JSON, terminiert mit `\n`.

### Request

```json
{"id": "r42", "command": "status", "args": {}}
```

* `id`       — String, frei wählbar; muss in der Antwort unverändert zurückkommen.
* `command`  — String, eine der unten aufgelisteten Commands.
* `args`     — Objekt; Inhalt kommandospezifisch.

### Response

```json
{"id": "r42", "ok": true, "result": {...}}
```

```json
{"id": "r42", "ok": false, "error": "unknown command: 'foo'"}
```

* `ok=true`  → `result` ist ein Objekt (kann leer sein).
* `ok=false` → `error` ist ein menschenlesbarer String. Kein Stack-Trace.

### Event (vom Daemon gepusht)

```json
{"event": "device-connected", "data": {"address": "AA:BB:CC:DD:EE:FF"}}
```

Events tragen kein `id`. Sie kommen nur auf Verbindungen, die zuvor das
Command `subscribe-events` aufgerufen haben.

## Commands

### `status`

Liefert den aktuellen Daemon-Status.

Request-Args: keine.

Response-`result`:

```json
{
  "reachable": true,
  "running": true,
  "device_connected": true,
  "last_poll_at": "2026-05-28T01:12:30+02:00",
  "active_provider": "anthropic",
  "providers": ["anthropic", "codex", "langdock", "opencode"],
  "snapshots": [...],
  "message": null
}
```

### `reload-config`

Triggert ein Re-Read von `config.toml`. Antwort kommt sofort; der Tausch
geschieht im nächsten Tick.

### `trigger-poll`

Erzwingt eine sofortige Vollpoll-Runde aller aktivierten Provider.

### `shutdown`

Beendet den Daemon sauber.

### `provider-detect`

Args: `{"id": "anthropic"|"codex"|...}`.

Response-`result`:

```json
{ "id": "anthropic", "detected": true, "source": "macOS Keychain", "notes": null }
```

`source` ist ein menschenlesbarer Hinweis, kein Token-Inhalt. Der Daemon
liest niemals Secrets im Klartext über die IPC.

### `provider-save`

Args: `{"id": "...", "fields": {...}}`. Schreibt einen Provider-Eintrag in
`config.toml`. **Phase 4** — aktuell antwortet der Daemon mit
`{"saved": false, "reason": "..."}`, weil die Setup-Wizard-Logik noch
interaktiv ist und auf Headless umgebaut wird.

### `secret-write`

Args: `{"key": "LANGDOCK_API_KEY", "value": "lk_..."}`.

Persistiert einen API-Key/Secret in `~/.config/clawdmeter/secrets.env`
(chmod 600). `value=""` löscht den Eintrag. Zusätzlich wird `os.environ[key]`
im laufenden Daemon-Prozess gesetzt, damit der Polling-Loop ohne Neustart
greift; anschließend wird `reload-config` ausgelöst.

Response-`result`:

```json
{ "saved": true, "path": "~/.config/clawdmeter/secrets.env", "masked": "lk_…1234" }
```

Bei Fehler: `{ "saved": false, "reason": "..." }` — Gründe sind „key fehlt"
oder Schreibfehler (z. B. Berechtigungen).

### `list-providers`

Antwort: `{ "providers": [{"slot_id": "...", "kind": "...", "poll_seconds": 60}, ...] }`.

### `subscribe-events`

Markiert die aktuelle Verbindung als Event-Subscriber. Folgende Events
werden gepusht:

| Event                  | `data`                                              |
|------------------------|-----------------------------------------------------|
| `device-connecting`    | `{ "address": "..." }`                              |
| `device-connected`     | `{ "address": "..." }`                              |
| `device-disconnected`  | `{ "address": "...", "clean": true }`               |
| `poll-success`         | `{ "provider": "anthropic", "at": "..." }`          |
| `poll-error`           | `{ "provider": "anthropic", "error": "..." }`       |
| `config-changed`       | `{ "providers": 4 }`                                |

## Versionierung

Beim Verbinden sendet der Client als erstes ein `hello`-Command, sobald
der Server eine Version-Negotiation braucht. Solange Protokoll v1 stabil
ist, ist `hello` optional und wird vom Daemon mit
`{"version": "1.0", "commands": [...]}` beantwortet.

## Sicherheits-Eckpunkte

* Keine Auth — der Endpoint ist auf UID-Ebene geschützt.
* Keine Secrets im Klartext über die IPC — nur Quell-Hinweise wie
  „macOS Keychain" oder Pfade.
* Kein offener TCP-Port. Sollte Phase 2 auf Windows-Named-Pipe
  Schwierigkeiten machen, ist die Antwort **nicht** TCP, sondern eine
  ProactorEventLoop-Integration; siehe `ipc_server._serve_windows_pipe`.
