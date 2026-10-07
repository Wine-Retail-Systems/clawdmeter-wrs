# Companion-App — Plan

Stand: 2026-05-28

Eine native Desktop-App für macOS und Windows, die das Onboarding,
Flashen und den Daemon-Lifecycle kapselt, sodass Anwender nicht mehr
mit Shell oder PowerShell in Berührung kommen müssen. Die existierenden
Shell-Skripte (`install-mac.sh`, `install-windows.ps1`, `flash-*.sh`)
bleiben als Power-User-Pfad erhalten.

## Ziele

- **macOS + Windows aus einer Codebase**, ein Download pro Plattform.
- Anwender lädt eine `.dmg` (mac) bzw. `.msi` (win), doppelklickt, fertig.
- Kein Python-Setup, kein PlatformIO-Setup, keine Shell-Kenntnisse nötig.
- Die App übernimmt drei Jobs: **Flashen**, **Daemon-Lifecycle**, **Setup/Status**.
- Brand-neutral als „Clawdmeter" — Wine Edition ist lediglich die Default-Auswahl
  im Flash-Wizard (wie heute in `flash-mac.sh` / `flash.sh`).

## Non-Ziele (MVP)

- Linux-Build (Tauri kann's, aber nicht im ersten Wurf).
- Reimplementierung der Provider-Adapter in Rust — wir behalten den Python-Daemon
  bei und frieren ihn nur ein.
- Sprachumschalter — vorerst nur Deutsch (analog zur Firmware-UI).
- Cloud-Telemetry — nur lokale Crash-Logs + Bug-Report-Button.
- OTA-Firmware-Update via BLE — Phase 2 nach MVP.

## Entscheidungs-Stack

| Bereich | Entscheidung | Begründung |
|---|---|---|
| App-Framework | **Tauri 2** + React + Vite | ~15 MB Bundle, mac+win+linux aus einer Codebase, native Tray-Support, Rust-Backend liefert `espflash` und `serialport` als First-Class-Crates |
| Form-Faktor | Menubar/Tray + öffenbares Fenster | Passt zum „läuft im Hintergrund"-Charakter des Daemons, Mac-Standard für Companion-Apps |
| Daemon-Auslieferung | **PyInstaller-Onefile** des bestehenden Python-Daemons | Provider-Abstraktion, Auto-Detect, Setup-Wizard-Logik bleiben unverändert — kein Re-Write |
| IPC App ↔ Daemon | **Unix-Socket / Named-Pipe** (Rust-Crate `interprocess`) | Bidirektional, sicher (kein offener Port), debugbar mit `nc -U` bzw. `\\.\pipe\…` |
| App-Branding | Neutral „Clawdmeter" — keine separate Wine-App | Reduziert Build-Matrix; Brand-Theme ist Firmware-Concern, nicht App-Concern |
| Firmware-Auswahl | Im Flash-Wizard, alle 3 Envs sichtbar, **Default `wine-216`** | Spiegelt heutiges Verhalten der Shell-Skripte |
| Firmware-Bundling | **Eingebettet** im App-Bundle (`resources/firmware/*.bin`) | Offline-fähig, atomares App+FW-Release, ~+3 MB Bundle-Größe |
| Sprache | Nur Deutsch (MVP) | Konsistent zur Firmware-UI; EN später nachrüstbar |
| Provider-Scope | **Alle 5** (Anthropic, Bedrock, Codex, Langdock, LLM Gateway/Bifrost; OpenCode seit 2026-10-07 entfernt) | 1:1-Feature-Parität mit dem Python-Setup-Wizard |
| OAuth-Tokens | **Auto-Detect** aus claude/codex CLI | Wie heute: macOS-Keychain für Claude, `~/.codex/auth.json` für Codex |
| BLE-Pairing | **Hybrid** — Discovery in App, Pairing im OS | Tauri-App scannt zur Bestätigung, eigentliches Pairing macht weiter macOS/Windows |
| macOS-Signing | **Notarized ab Tag 1** | Apple Developer Account vorhanden |
| Windows-Signing | Vorerst **unsigned**, Cert später nachziehen | Entkoppelt Cert-Beschaffung vom MVP-Release; Anwender muss SmartScreen wegklicken |
| Auto-Update | **Tauri Updater** gegen GitHub Releases | Signierte Updates, Delta-fähig, eingebaut |
| Win-Installation | **Per-User** (`%LOCALAPPDATA%`) | Kein UAC-Prompt, schnellste Onboarding-UX |
| Onboarding | **Landing-Screen** mit prominentem „Gerät einrichten"-CTA | Sowohl Erst-Setup als auch Re-Setup gut bedienbar |
| Telemetry | **Keine** Cloud — lokale Crash-Logs + „Bug melden"-Button | Konsistent zur „eigenes Device, eigene Daten"-Linie |

## Repo-Layout (Soll)

```
clawdmeter/
├── firmware/                              # unverändert
├── daemon/                                # unverändert — per PyInstaller eingefroren
├── companion/                             # ← NEU
│   ├── src-tauri/                         # Rust-Backend
│   │   ├── src/
│   │   │   ├── main.rs                    # Tauri-Bootstrap + Tray
│   │   │   ├── flash.rs                   # espflash-Wrapper
│   │   │   ├── ports.rs                   # serialport (USB-VID 0x303A filter)
│   │   │   ├── daemon_proc.rs             # Daemon-Child-Process Spawn/Kill
│   │   │   ├── ipc.rs                     # Socket/Pipe via `interprocess`
│   │   │   ├── service.rs                 # LaunchAgent (mac) / Scheduled Task (win)
│   │   │   ├── ble_scan.rs                # btleplug (readonly Discovery)
│   │   │   ├── crash.rs                   # lokale Crash-Logs
│   │   │   └── updater.rs                 # Tauri Updater Setup
│   │   ├── tauri.conf.json
│   │   ├── icons/                         # Tray-Icons (3 States: ok/warn/error)
│   │   └── Cargo.toml
│   ├── src/                               # React + Vite
│   │   ├── routes/
│   │   │   ├── Landing.tsx
│   │   │   ├── flash/                     # 3-Step-Wizard
│   │   │   ├── setup/                     # 6-Provider-Stepper
│   │   │   ├── pair/                      # BLE-Discovery + OS-Dialog-Hinweis
│   │   │   └── status/                    # Daemon-Status, Logs, Bug-Report
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── ipc.ts                     # invoke-Wrapper für Rust-Backend
│   │   │   └── strings.de.ts              # zentralisierte DE-Strings
│   │   └── main.tsx
│   ├── resources/                         # eingebettete Assets
│   │   ├── firmware/
│   │   │   ├── wine-216.bin
│   │   │   ├── standard-216.bin
│   │   │   └── standard-180.bin
│   │   └── daemon/
│   │       ├── clawdmeter-daemon-macos-arm64
│   │       └── clawdmeter-daemon-win-x64.exe
│   ├── tests/
│   └── package.json
├── tools/
│   └── build_companion.py                 # ← NEU: PyInstaller + FW-Build + Tauri-Build
├── .github/workflows/
│   └── release-companion.yml              # ← NEU: mac-arm64 + win-x64, Sign, Notarize
└── feature-documentation/
    └── companion-app/                     # ← diese Dokumentation
        ├── PLAN.md                        # ← du bist hier
        ├── PROGRESS.md
        ├── architecture.md                # später
        ├── ipc-protocol.md                # später
        └── build-and-release.md           # später
```

## Phasenplan

| Phase | Inhalt | Aufwand | Risiko |
|---|---|---|---|
| 0 | Tauri+React-Skeleton, CI-Skelett, Apple-Notarization-Setup | 1–2 d | niedrig |
| 1 | **PyInstaller-Spike** für Daemon — höchstes technisches Risiko (bleak auf Windows) | 1 d | **hoch** |
| 2 | IPC-Schicht — Socket/Pipe-Server in Python, Client in Rust, JSON-Protokoll | 1–2 d | mittel |
| 3 | Flash-Wizard — Board-Auswahl, Port-Detect (VID 0x303A), espflash mit Progress | 2 d | mittel |
| 4 | Setup-Wizard — 6-Provider-Stepper, Auto-Detect-Logik via Daemon-IPC | 3 d | niedrig |
| 5 | Daemon-Lifecycle — Service-Install (LaunchAgent/Task), Start/Stop/Restart, Live-Logs | 2 d | mittel |
| 6 | Tray + Landing-Screen — Status-Indikator, Bug-Report-Flow, Crash-Log-Sammlung | 1–2 d | niedrig |
| 7 | BLE-Discovery — btleplug-Scan, Pair-Hinweis-Dialog | 1 d | niedrig |
| 8 | Auto-Update — Tauri Updater gegen GitHub Releases | 1 d | niedrig |
| 9 | Build & Sign & Notarize — macOS-Pipeline komplett, Windows unsigned (vorerst) | 2 d | mittel |
| 10 | Doku + Cutover — Feature-Docs, README umstellen, Shell-Skripte als Power-User-Pfad markieren | 1 d | niedrig |

**Netto:** ~15–18 Arbeitstage.

## Top-Risiken

1. **PyInstaller × bleak auf Windows.** WinRT-Bindings werden manchmal nicht
   automatisch mitgepackt. Lösung wenn's klemmt:
   `--hidden-import bleak.backends.winrt.*` + ggf. `--collect-all bleak`.
   Wenn auch das nicht reicht, Fallback-Plan: Daemon in Rust reimplementieren
   (verschiebt MVP um ~2 Wochen). Phase 1 ist deshalb expliziter Spike.
2. **CoreBluetooth-Permissions auf macOS.** App und Daemon-Binary brauchen je
   eigene `NSBluetoothAlwaysUsageDescription` + Entitlements. Reihenfolge:
   App fragt zuerst beim ersten Daemon-Start, sonst zeigt macOS den
   Permission-Dialog ohne App-Kontext.
3. **espflash × ESP32-S3 USB-JTAG.** Reset-Sequenz unterscheidet sich von
   klassischem USB-zu-Serial. Auf echtem Mac und in Windows-VM gegen-testen,
   bevor wir Anwendern Flash-Funktionalität versprechen.
4. **Service-Pfad-Migration bei App-Update.** LaunchAgent/Task referenziert
   absoluten Pfad zur Daemon-Binary. App-Update muss den Service neu schreiben
   oder einen stabilen Symlink/Wrapper-Pfad benutzen.
5. **Named-Pipe-ACLs auf Windows.** Daemon-Task läuft im User-Kontext, App
   ebenfalls — sollte funktionieren, aber explizit testen.

## Schnittstellen-Vertrag (IPC, vorläufig)

Detaillierte Definition kommt in [`ipc-protocol.md`](ipc-protocol.md) sobald Phase 2 anläuft. Grobskizze:

- Socket-Pfad macOS: `~/Library/Application Support/clawdmeter/daemon.sock`
- Pipe-Name Windows: `\\.\pipe\clawdmeter-daemon`
- Protokoll: JSON-Lines, Request/Response mit `id`-Feld
- Commands: `status`, `reload-config`, `trigger-poll`, `subscribe-events`, `shutdown`
- Events (Push): `device-connected`, `device-disconnected`, `poll-success`, `poll-error`, `config-changed`

## Cutover-Strategie

Die existierenden Shell-Skripte (`install-mac.sh`, `install-windows.ps1`,
`flash-mac.sh`, `flash.sh`) bleiben **bestehen** und werden in der README
als „Power-User-Pfad" markiert. Companion-App wird neue Default-Empfehlung
für Endanwender.

Migration für bestehende User: Companion-App erkennt eine vorhandene
`config.toml`/Service-Installation beim ersten Start und übernimmt sie,
statt erneut durch das Onboarding zu zwingen.
