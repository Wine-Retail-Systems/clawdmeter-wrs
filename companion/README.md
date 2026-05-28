# Clawdmeter Companion-App

Native Desktop-App für macOS und Windows. Onboarding, Firmware-Flash und
Daemon-Lifecycle in einer Oberfläche.

Stack: **Tauri 2 + React + Vite**, Rust-Backend, Python-Daemon (PyInstaller).

Spezifikation: [`../feature-documentation/companion-app/PLAN.md`](../feature-documentation/companion-app/PLAN.md).
Fortschritt: [`../feature-documentation/companion-app/PROGRESS.md`](../feature-documentation/companion-app/PROGRESS.md).

## Voraussetzungen

- Node.js ≥ 20 (`node -v`)
- Rust ≥ 1.77 (`rustc --version`) — installiere via [rustup](https://rustup.rs)
- Tauri-System-Deps: <https://v2.tauri.app/start/prerequisites/>
  - macOS: nur Xcode-CLT (`xcode-select --install`)
  - Windows: WebView2 (i.d.R. vorinstalliert) + MSVC-Buildtools
- Python ≥ 3.10 für den Daemon-Build (PyInstaller)

## Dev-Workflow

```bash
cd companion
npm install                  # einmalig — installiert tauri-cli und Frontend-Deps
npm run tauri:dev            # öffnet Desktop-Fenster mit Hot-Reload
```

Für UI-Entwicklung ohne laufenden Daemon:

```bash
VITE_MOCK_IPC=1 npm run dev  # Frontend nur, alle IPC-Calls liefern Mock-Daten
```

## Daemon-Bundle bauen

PyInstaller-Build des bestehenden Python-Daemons:

```bash
python3 tools/build_daemon_bundle.py
# → companion/resources/daemon/clawdmeter-daemon-{macos-arm64,win-x64.exe}
```

## Firmware-Binaries einbetten

```bash
pio run -d firmware -e wine-216
pio run -d firmware -e standard-216
pio run -d firmware -e standard-180
python3 tools/copy_firmware_to_companion.py
# → companion/resources/firmware/*.bin
```

Vor `npm run tauri:build` müssen beide Resource-Bundles vorhanden sein, sonst
schlägt Tauri mit „resource not found" fehl.

## Release-Build

```bash
npm run tauri:build
# macOS:    src-tauri/target/release/bundle/dmg/Clawdmeter_*.dmg
# Windows:  src-tauri\target\release\bundle\msi\Clawdmeter_*.msi
```

CI-Pipeline siehe `../.github/workflows/release-companion.yml`.

## Architektur kurz

```
companion/
├── src/                React + Vite UI
│   ├── routes/         Landing, Flash, Setup, Pair, Status
│   ├── components/
│   └── lib/            ipc.ts, strings.de.ts
└── src-tauri/          Rust-Backend
    ├── src/
    │   ├── flash.rs        espflash-Wrapper
    │   ├── ports.rs        serialport (VID 0x303A)
    │   ├── daemon_proc.rs  Lifecycle
    │   ├── service.rs      LaunchAgent / Scheduled Task
    │   ├── ipc.rs          Socket/Pipe ↔ Python-Daemon
    │   ├── ble_scan.rs     btleplug
    │   ├── crash.rs        Bug-Report-Bundle
    │   ├── tray.rs         Menubar-Icon
    │   └── updater.rs      Tauri-Updater
    ├── tauri.conf.json
    └── Cargo.toml
```

Sämtliche IPC-Aufrufe gehen über `src/lib/ipc.ts` → `invoke()` → Rust-Command
in `src-tauri/src/lib.rs`. Rust ist dünn; alle Domänen-Logik (Polling,
Provider, Secrets) bleibt im Python-Daemon. Vollständige IPC-Spezifikation:
`../feature-documentation/companion-app/ipc-protocol.md` (folgt in Phase 2).
