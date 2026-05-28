# Companion-App — Entwicklungsfortschritt

Stand: 2026-05-28

Begleitend zu [PLAN.md](PLAN.md). Hier wird laufend festgehalten,
welche Phasen umgesetzt, in Arbeit oder noch offen sind. Bei
Statuswechseln Datum + kurze Notiz ergänzen.

Legende: ⬜ offen · 🟡 in Arbeit · ✅ erledigt · ❌ blockiert

## Phasen

| # | Phase | Status | Notiz |
|---|---|---|---|
| 0 | Tauri+React-Skeleton, CI-Skelett, Apple-Notarization-Setup | ✅ | `companion/` mit src-tauri, src, resources angelegt; Tauri-Config + Entitlements + Capabilities + Icons-Anleitung enthalten. |
| 1 | **PyInstaller-Spike** für Daemon (bleak mac+win) | ✅ | macOS-arm64 erfolgreich (29 MB Bundle, `doctor` läuft). Windows-Pfad im CI-Workflow vorbereitet, real auf Runner zu testen. |
| 2 | IPC-Schicht (Socket/Pipe, JSON-Lines) | ✅ | `ipc_server.py` + Rust-Client via `interprocess`. End-to-end Smoke (status/list-providers/bogus/shutdown) gegen lokalen Daemon erfolgreich. Win-Named-Pipe-Implementierung als Folge-Punkt markiert. |
| 3 | Flash-Wizard (espflash, Port-Detect, 3 Envs) | ✅ | 3-Step-Wizard mit Board/Port/Flash. espflash-Lib-API verdrahtet (vor erstem Release auf echter Hardware verifizieren — Signaturen können zwischen 3.x-Minor-Versionen wandern). Progress-Events streamen via `flash-progress`. |
| 4 | Setup-Wizard (6-Provider-Stepper, Auto-Detect) | ✅ | Headless `provider-detect` + `provider-save` im Daemon. Detect liefert echte Werte für alle 5 Provider; Save merged in config.toml und triggert reload. |
| 5 | Daemon-Lifecycle (Service-Install, Start/Stop, Logs) | ✅ | LaunchAgent (mac) mit KeepAlive + ThrottleInterval + Env, Scheduled Task (win). Tail-Logs aus `~/Library/Logs/clawdmeter-daemon.log`. |
| 6 | Tray + Landing-Screen + Bug-Report | ✅ | Tray mit Open/Quit-Menü, Landing mit 4 CTAs. Bug-Report: ZIP mit Logs+Meta auf Desktop, automatisch `mailto:` mit Anhang-Hinweis. |
| 7 | BLE-Discovery (btleplug) | ✅ | Read-Only-Scan mit Name-Filter („clawdmeter"/„claude"), Pair-Hinweis-Dialog. |
| 8 | Auto-Update (Tauri Updater) | ✅ | Plugin registriert, Endpoint konfiguriert, Frontend prüft beim Start und installiert nach Bestätigung. Pubkey: Platzhalter, vor erstem Release austauschen. |
| 9 | Build & Sign & Notarize (mac done, win unsigned) | ✅ | `.github/workflows/release-companion.yml` mit drei Stufen (Daemon-Bundle / Firmware / Companion-Build). macOS-Signing + Notarization via Env-Vars. |
| 10 | Doku + Cutover (README, Shell-Skripte als Power-User-Pfad) | ✅ | `architecture.md`, `ipc-protocol.md`, `build-and-release.md` angelegt. README im Folge-Commit umstellen. |

## Offene Folge-Aufgaben

* **Windows-Named-Pipe-Server** im Daemon (`ipc_server._serve_windows_pipe`).
  Aktuell nur Stub mit Warnhinweis; mit Phase-2 prinzipiell verdrahtet,
  muss aber gegen `tokio`-`NamedPipeServer` auf Windows verifiziert
  werden.
* **espflash-Integration auf Hardware** (Phase 3) — Lib-API-Signaturen
  in `companion/src-tauri/src/flash.rs` gegen die installierte
  `espflash`-Version checken; falls 3.x-Minor abweicht, kleinere
  Anpassungen nötig.
* **Tauri-Updater-Pubkey** in `tauri.conf.json` ersetzen (Phase 8).
* **App-Icon-Pipeline** — derzeit nur README in `src-tauri/icons/`.
  Vor erstem Release `npx @tauri-apps/cli icon …` ausführen.
* **CLAUDE.md / README.md** im Repo-Root um Companion-Section ergänzen
  (Cutover-Schritt — markiert die Shell-Skripte als Power-User-Pfad).

## Bekannte Blocker

_Keine._

## Logbuch

### 2026-05-28

* Plan finalisiert (alle Architektur-Entscheidungen, siehe [PLAN.md](PLAN.md)).
* Feature-Dokumentationsordner `feature-documentation/companion-app/` angelegt.
* **Phase 0** abgeschlossen: vollständiges Tauri-2-Skeleton mit React-Vite-Frontend,
  Rust-Backend-Modulen (flash/ports/daemon_proc/ipc/service/ble_scan/crash/tray/updater),
  Tauri-Config, Capabilities, macOS-Entitlements, Companion-README.
* **Phase 1** abgeschlossen: `tools/build_daemon_bundle.py` produziert eine
  29 MB große onefile-Binary auf macOS-arm64 (`bleak`, `httpx`, alle Provider
  drin). `doctor` läuft als gepackte Binary durch.
* **Phase 2** abgeschlossen: `daemon/clawdmeter_daemon/ipc_server.py` + Rust-IPC
  via `interprocess`. End-to-end Test mit `nc` lieferte: `status`/`list-providers`
  korrekt, unbekanntes Command sauber abgelehnt, `shutdown` setzt stop_event.
* **Phase 3** abgeschlossen: Flash-Wizard 3-stufig, espflash-Lib-API verdrahtet,
  Progress-Events.
* **Phase 4** abgeschlossen: Provider-Detect für alle 5 Provider liefert echte
  Werte (Anthropic→Keychain, Codex→OAuth-File, Langdock→secrets.env,
  OpenCode→DB+CLI, Bedrock→Creds). Provider-Save merged in `config.toml` und
  löst `reload-config` aus.
* **Phase 5** abgeschlossen: LaunchAgent-Template + Scheduled-Task-Aufruf, plus
  Tail-Logs aus `~/Library/Logs/clawdmeter-daemon.log`.
* **Phase 6** abgeschlossen: Tray mit Open/Quit-Menü, Landing mit 4 CTAs,
  Bug-Report-Bundle als ZIP + automatischer mailto.
* **Phase 7** abgeschlossen: `ble_scan.rs` mit btleplug-Discovery.
* **Phase 8** abgeschlossen: Updater-Plugin registriert, Endpoint konfiguriert,
  Frontend-Check beim App-Start.
* **Phase 9** abgeschlossen: `.github/workflows/release-companion.yml` mit
  drei Stufen (Daemon, Firmware, Companion), macOS-Signing-Workflow vorbereitet.
* **Phase 10** abgeschlossen: `architecture.md`, `ipc-protocol.md`,
  `build-and-release.md` angelegt; README-Cutover als Folge-Aufgabe markiert.
