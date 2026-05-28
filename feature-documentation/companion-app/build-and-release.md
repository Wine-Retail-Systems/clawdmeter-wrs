# Companion-App — Build & Release

Stand: 2026-05-28

## Lokaler Build (Entwicklung)

```bash
# 1. Daemon als PyInstaller-Single-File
python3 tools/build_daemon_bundle.py
# → companion/resources/daemon/clawdmeter-daemon-macos-arm64

# 2. Firmware-Binaries für alle drei Envs
pio run -d firmware -e wine-216
pio run -d firmware -e standard-216
pio run -d firmware -e standard-180
python3 tools/copy_firmware_to_companion.py
# → companion/resources/firmware/*.bin

# 3. Companion-App (Dev-Modus mit Hot-Reload)
cd companion
npm install
npm run tauri:dev
```

`npm run tauri:dev` startet Vite + Rust-Backend. Beim ersten Start werden
die Tauri-CLI und die Rust-Dependencies (~5 min) kompiliert.

## Release-Build lokal

```bash
cd companion
npm run tauri:build
# macOS:    src-tauri/target/release/bundle/dmg/Clawdmeter_0.1.0_aarch64.dmg
# Windows:  src-tauri\target\release\bundle\msi\Clawdmeter_0.1.0_x64_de-DE.msi
```

Beachte: ohne die Apple-Signing-Env-Vars produziert macOS einen
unsigned DMG, der beim ersten Start die Gatekeeper-Warnung auslöst.

## Apple-Signing & Notarization

Erforderliche Env-Vars (lokal in einer `.envrc`, in CI als
Repository-Secrets):

```bash
export APPLE_CERTIFICATE="<base64-encoded .p12>"
export APPLE_CERTIFICATE_PASSWORD="…"
export APPLE_SIGNING_IDENTITY="Developer ID Application: Jacques Krinke (TEAMID)"
export APPLE_ID="sascha@jacques.de"
export APPLE_PASSWORD="<app-specific-password>"
export APPLE_TEAM_ID="TEAMID"
```

Tauri sieht die Variablen automatisch, signiert das App-Bundle und reicht
es zur Notarization ein. Apple liefert das Ticket zurück, das in den DMG
gestapelt wird.

## Tauri-Updater — Signing-Key (Phase 8)

Einmalig generieren:

```bash
npx @tauri-apps/cli signer generate -w ~/.tauri/clawdmeter-updater.key
```

Den Public-Key in `companion/src-tauri/tauri.conf.json` →
`plugins.updater.pubkey` eintragen. Privatkey (+ optional Passwort) als
GitHub-Secrets `TAURI_SIGNING_PRIVATE_KEY` /
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD` hinterlegen. Der Build erzeugt eine
`latest.json` neben den Artifacts; die App pollt dagegen.

## CI-Workflow

`.github/workflows/release-companion.yml` deckt drei Phasen ab:

1. **build-daemon-bundles** — PyInstaller-Build auf macOS-14 und
   windows-latest. Artefakte: zwei Daemon-Binaries.
2. **build-firmware** — PlatformIO-Build aller drei Envs auf
   ubuntu-latest. Artefakte: drei `firmware.bin`.
3. **build-companion** — Tauri-Build auf macOS-14 (signed/notarized) und
   windows-latest (unsigned). Lädt die Artefakte aus Schritt 1+2,
   bündelt sie in `companion/resources/`, dann `npx tauri build`.

Trigger:

* Push eines Tags `companion-vX.Y.Z` → Vollrelease + GitHub-Release.
* `workflow_dispatch` → Smoke-Test ohne Release-Publish.

## Windows-Signing (geplant, nicht im MVP)

Sobald ein EV-Code-Signing-Cert beschafft ist, ergänzen wir den
`build-companion` Job um:

```yaml
- name: Sign MSI (Windows)
  if: matrix.os == 'windows-latest'
  run: |
    signtool sign /fd SHA256 /a /td SHA256 /tr http://timestamp.digicert.com \
      $env:GITHUB_WORKSPACE\companion\src-tauri\target\release\bundle\msi\*.msi
```

Bis dahin sehen Anwender beim ersten Start „Windows hat Ihren PC
geschützt" → „Weitere Informationen" → „Trotzdem ausführen".

## Versionierung

* App-Version: `companion/src-tauri/tauri.conf.json` → `version` +
  `companion/package.json` → `version`. Beide synchron halten.
* Daemon-Version: `daemon/clawdmeter_daemon/__init__.py` → `__version__`.
* Firmware-Version: implizit pro Git-Commit (über die PlatformIO-Builds
  des Tags).

Empfehlung: alle drei zusammen bumpen bei einem `companion-vX.Y.Z`-Tag,
damit ein App-Release stets ein konsistentes Bundle ist.

## Migration für bestehende User

Companion-App erkennt beim ersten Start eine vorhandene
`~/.config/clawdmeter/config.toml` und einen aktiven LaunchAgent. In dem
Fall:

* Wizard wird übersprungen (Status zeigt sofort die laufende
  Konfiguration).
* Ist der LaunchAgent von `install-mac.sh` aus dem Repo installiert,
  bleibt er aktiv. Service-Tausch (auf die gebündelte Daemon-Binary)
  geschieht nur, wenn der Nutzer explizit „Daemon neu installieren"
  klickt — wir wollen laufende Konfigurationen nicht überfahren.
