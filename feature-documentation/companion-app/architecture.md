# Companion-App — Architektur

Stand: 2026-05-28

Die Companion-App ist eine native Desktop-Anwendung (Tauri 2 + React) für
macOS und Windows. Ziel: Endanwender kommen mit Shell/PowerShell und
PlatformIO **nie** in Berührung.

## Drei Verantwortungen, drei Module

```
┌────────────────────────────────────────────────────────────────────┐
│                        Companion-App (Tauri 2)                     │
│  ┌───────────────────────┐    ┌───────────────────────────────┐    │
│  │ React-UI (Vite)       │←──▶│ Rust-Backend (src-tauri)      │    │
│  │  Landing/Flash/Setup  │    │  flash.rs  ports.rs  ble_scan │    │
│  │  Pair/Status          │    │  service.rs  daemon_proc.rs   │    │
│  └───────────────────────┘    └─────────────┬─────────────────┘    │
│                                             │                      │
│           ┌─────────────────────────────────┼─────────────────┐    │
│           │              IPC (JSON-Lines)   │                 │    │
│           │ Unix-Socket / Named-Pipe        │                 │    │
│           └─────────────────────────────────┼─────────────────┘    │
└─────────────────────────────────────────────┼──────────────────────┘
                                              │
                          ┌───────────────────▼───────────────────┐
                          │ Python-Daemon (PyInstaller-onefile)   │
                          │  polling.py  ipc_server.py            │
                          │  providers/  ble.py  config.py        │
                          └───────────────────┬───────────────────┘
                                              │  BLE
                                              ▼
                                  ┌────────────────────────┐
                                  │ ESP32-S3 Clawdmeter    │
                                  │ (Firmware unverändert) │
                                  └────────────────────────┘
```

### 1. Flashen

Rust holt die Liste der Serial-Ports via `serialport`-Crate, filtert auf
USB-VID `0x303A` (Espressif). Das Wizard-UI lässt den Nutzer ein Board
wählen (Default `wine-216`) und einen Port. `flash.rs` lädt die passende
`resources/firmware/<env>.bin` und schreibt sie via `espflash`-Lib-API.
Progress kommt als `flash-progress`-Event ins Frontend.

### 2. Daemon-Lifecycle

Beim ersten App-Start legt `service.rs` einen LaunchAgent
(`~/Library/LaunchAgents/de.jacques.clawdmeter.daemon.plist`) bzw. einen
Scheduled Task an, der auf die mitgebündelte
`resources/daemon/clawdmeter-daemon-<platform>`-Binary verweist. Start /
Stop / Restart laufen über `launchctl` resp. `schtasks`. Logs werden aus
`~/Library/Logs/clawdmeter-daemon.log` getailt.

### 3. Setup & Status

Die App spricht den Daemon über einen lokalen Endpoint (Unix-Socket bzw.
Named-Pipe) im JSON-Lines-Format an. Details:
[`ipc-protocol.md`](ipc-protocol.md). Der Setup-Wizard nutzt
`provider-detect` für Auto-Detect aller 5 Provider und `provider-save`
zum headless Persistieren in `config.toml`. Der Status-Screen tailt Logs
über `daemon_tail_logs` und kann Bug-Report-Bundles erzeugen
(`crash.rs` → ZIP mit Logs + Meta auf Desktop, dann `mailto:`).

## Warum diese Splittung

* **Provider-Logik bleibt Python.** ~3000 LoC bestehender, getesteter
  Code (Provider-Abstraktion, Secrets, Polling-Loop, BLE-Auth). Den in
  Rust nachzubauen wäre 1–2 Monate Zeitverlust für null Nutzergewinn.
* **Rust-Backend bleibt schlank.** Nur Glue: Port-Discovery, Flash,
  Service-Plumbing, BLE-Discovery, IPC-Client, Tray. Kein Provider-Code,
  keine Secrets, keine API-Aufrufe.
* **JSON-Lines-IPC** statt embedding: jeder Teil kann unabhängig restartet
  werden. Daemon kann auch ohne App laufen (System-Service); App kann
  auch ohne Daemon laufen (Setup-Bildschirm zeigt Fehlerstatus).

## Wichtige Dateien

| Datei | Zuständig für |
|---|---|
| `companion/src-tauri/src/lib.rs` | Tauri-Bootstrap, Tray-Install, Command-Registry |
| `companion/src-tauri/src/flash.rs` | espflash-Wrapper, Progress-Events |
| `companion/src-tauri/src/ports.rs` | Serial-Port-Discovery, VID-0x303A-Filter |
| `companion/src-tauri/src/daemon_proc.rs` | Daemon-Status-Query + Lifecycle-Commands |
| `companion/src-tauri/src/service.rs` | LaunchAgent / Scheduled Task |
| `companion/src-tauri/src/ipc.rs` | JSON-Lines-Client zum Daemon |
| `companion/src-tauri/src/ble_scan.rs` | btleplug-Discovery |
| `companion/src-tauri/src/crash.rs` | Bug-Report-Bundle |
| `companion/src/lib/ipc.ts` | Typisierte invoke()-Wrapper |
| `companion/src/lib/strings.de.ts` | Sämtliche UI-Strings (Deutsch, i18n-ready) |
| `companion/src/routes/` | Landing, Flash, Setup, Pair, Status |
| `daemon/clawdmeter_daemon/ipc_server.py` | Async Socket-Server im Daemon |
| `tools/build_daemon_bundle.py` | PyInstaller-Wrapper |
| `tools/copy_firmware_to_companion.py` | FW-Binaries → `companion/resources/firmware/` |
| `.github/workflows/release-companion.yml` | Multi-Plattform-Release |

## Plattform-Eigenheiten

| Aspekt | macOS | Windows |
|---|---|---|
| Endpoint | Unix-Socket `~/Library/Application Support/clawdmeter/daemon.sock` | Named-Pipe `\\.\pipe\clawdmeter-daemon` |
| Service | LaunchAgent (User-Domain) | Scheduled Task (ONLOGON, LIMITED) |
| Installation | App in `/Applications`, Daemon-Bin als Resource | Per-User in `%LOCALAPPDATA%`, kein UAC |
| Signing | Developer-ID + Notarization ab Tag 1 | Vorerst unsigned (SmartScreen-Warnung) |
| Bluetooth-Permission | App + Daemon brauchen je `NSBluetoothAlwaysUsageDescription` (Entitlements) | implizit über User-Session |
| Auto-Update | DMG-Replace via Tauri-Updater | NSIS-Update via Tauri-Updater |

## Was bewusst NICHT in der App lebt

* **Provider-API-Aufrufe** — bleiben im Daemon.
* **Secrets** — werden im Daemon gelesen, niemals über IPC zur App
  transportiert.
* **BLE-Pairing** — übernimmt das OS. App scannt nur zur visuellen
  Bestätigung.
* **Firmware-Compile** — fertige `.bin`s werden vom CI-Workflow gebaut
  und ins App-Bundle eingebettet. PlatformIO ist kein End-User-Tool.

## Sicherheitsmodell

* IPC-Endpoint nur für UID des Users erreichbar (`chmod 600` bzw.
  default-DACL der Named-Pipe).
* Daemon liest Tokens aus Keychain / `~/.codex/auth.json` /
  `~/.config/clawdmeter/secrets.env`. Tokens verlassen den Daemon
  niemals — die IPC liefert höchstens menschenlesbare Quellangaben wie
  „macOS Keychain".
* App-Bundle ist auf macOS Notarized; Windows zunächst unsigned (siehe
  PLAN.md, „Top-Risiken").

## Erweiterungen, die später folgen können

* Linux-Build (`platform-espressif32` + `.deb`/`.AppImage`)
* OTA-Firmware-Update via BLE (Phase 2 nach MVP)
* Sprachumschalter (`strings.de.ts` → i18n-Modul)
* Telemetry-Opt-in
