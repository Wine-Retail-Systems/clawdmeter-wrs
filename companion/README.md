# Clawdmeter Companion-App

Native Desktop-App für macOS und Windows. Onboarding, Firmware-Flash und
Daemon-Lifecycle in einer Oberfläche.

Stack: **Tauri 2 + React + Vite**, Rust-Backend, Python-Daemon (PyInstaller).

Spezifikation: [`../feature-documentation/companion-app/PLAN.md`](../feature-documentation/companion-app/PLAN.md).
Fortschritt: [`../feature-documentation/companion-app/PROGRESS.md`](../feature-documentation/companion-app/PROGRESS.md).
Architektur-Detail: [`../feature-documentation/companion-app/architecture.md`](../feature-documentation/companion-app/architecture.md).
CI- und Release-Sicht: [`../feature-documentation/companion-app/build-and-release.md`](../feature-documentation/companion-app/build-and-release.md).
Lokales Cross-Build-Tooling: [`../feature-documentation/companion-app/local-build.md`](../feature-documentation/companion-app/local-build.md).

---

## Inhaltsverzeichnis

1. [Quickstart](#quickstart)
2. [Voraussetzungen](#voraussetzungen)
3. [Projekt-Layout](#projekt-layout)
4. [Dev-Workflow](#dev-workflow)
5. [Bauen — Schritt für Schritt](#bauen--schritt-für-schritt)
   1. [Firmware-Binaries einbetten](#1-firmware-binaries-einbetten)
   2. [Daemon-Bundle bauen](#2-daemon-bundle-bauen)
   3. [Signing-Credentials einrichten](#3-signing-credentials-einrichten)
   4. [macOS-Release-Bundle](#4-macos-release-bundle-aarch64)
   5. [Windows-Release-Bundle (Cross-Build vom Mac)](#5-windows-release-bundle-cross-build-vom-mac)
6. [One-Shot-Release via Skript](#one-shot-release-via-skript)
7. [Tauri-Updater einrichten](#tauri-updater-einrichten)
8. [Versionierung](#versionierung)
9. [CI / GitHub Actions](#ci--github-actions)
10. [Troubleshooting](#troubleshooting)
11. [Architektur kurz](#architektur-kurz)

---

## Quickstart

```bash
# Einmalig — installiert alle Build-Abhängigkeiten (mac + win-cross)
./tools/install_release_deps.sh

# Signing-Credentials einrichten (siehe Abschnitt 3)
cp companion/.env.local.example companion/.env.local
$EDITOR companion/.env.local
direnv allow   # falls direnv installiert

# Vollständiges Release bauen — DMG + NSIS-Installer
./tools/release-companion.sh --pull-win-daemon --full
ls dist/
```

`dist/` enthält danach:

* `Clawdmeter_<version>_aarch64.dmg` — signed + notarized macOS-Bundle
* `Clawdmeter_<version>_x64-setup.exe` — Windows NSIS-Installer (unsigned)

Für reine Entwicklung ohne Release-Bundle reicht:

```bash
cd companion
npm install
npm run tauri:dev
```

---

## Voraussetzungen

### Basis (Dev & macOS-Build)

| Tool | Mindestversion | Wozu | Install |
|---|---|---|---|
| Node.js | ≥ 20 | Frontend-Build (Vite, React) | `brew install node` oder via nvm |
| npm / pnpm | aktuell | Package-Manager (npm reicht) | optional: `corepack enable && corepack prepare pnpm@latest --activate` |
| Rust | ≥ 1.77 (stable) | Tauri-Backend | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Python | ≥ 3.11 | Daemon + PyInstaller | `brew install python@3.13` |
| Xcode CLT | aktuell | clang, codesign, notarytool | `xcode-select --install` |
| PlatformIO | ≥ 6 | Firmware-Builds | `pipx install platformio` oder `brew install platformio` |
| Tauri-System-Deps | — | siehe <https://v2.tauri.app/start/prerequisites/> | i.d.R. durch Xcode CLT abgedeckt |
| direnv (optional) | — | `.env.local` automatisch laden | `brew install direnv` |

### Zusätzlich für Windows-Cross-Build vom Mac

| Tool | Wozu | Install |
|---|---|---|
| Rust-Target `x86_64-pc-windows-msvc` | Cross-Target | `rustup target add x86_64-pc-windows-msvc` |
| `cargo-xwin` | MSVC-SDK-Header-Bridge | `cargo install --locked cargo-xwin` |
| NSIS | Windows-Installer-Bundler | `brew install nsis` |
| `gh` CLI | nur bei `--pull-win-daemon` | `brew install gh && gh auth login` |

> **MSI-Format**: Der WiX-basierte `.msi`-Bau auf Mac ist fragil. Lokal bauen
> wir **nur NSIS** (`.exe`-Installer). Die CI baut zusätzlich MSI auf einem
> echten Windows-Runner — push einen `companion-vX.Y.Z`-Tag, wenn du beides
> brauchst.

> Auf Windows nativ: WebView2 ist i.d.R. vorinstalliert. MSVC-Buildtools via
> Visual Studio Installer („Desktop development with C++"), dann reicht
> `npm run tauri:build`.

### Einmalig für signierte Releases

1. **Developer ID Application Certificate** in der macOS-Keychain. Verifikation:
   ```bash
   security find-identity -v -p codesigning | grep "Developer ID Application"
   ```
2. **App Store Connect API Key** (`AuthKey_<KEYID>.p8`) für Notarization.
   App Store Connect → Users and Access → Integrations → App Store Connect API
   → „+" → Access: Developer.
3. **Tauri Updater Key** generieren (siehe [Tauri-Updater einrichten](#tauri-updater-einrichten)).

Details zum Bezug der Apple-Credentials:
[`../feature-documentation/companion-app/build-and-release.md`](../feature-documentation/companion-app/build-and-release.md).

---

## Projekt-Layout

```
companion/
├── src/                       React + Vite UI
│   ├── App.tsx
│   ├── routes/                Landing, Flash, Setup, Pair, Status
│   ├── components/
│   ├── lib/                   ipc.ts, strings.de.ts, platform.ts
│   ├── styles.css
│   └── main.tsx
├── src-tauri/                 Rust-Backend
│   ├── src/
│   │   ├── lib.rs             Tauri-Commands (#[tauri::command])
│   │   ├── flash.rs           espflash-Wrapper
│   │   ├── ports.rs           serialport (VID 0x303A)
│   │   ├── daemon_proc.rs     Daemon-Lifecycle
│   │   ├── service.rs         LaunchAgent (mac) / Scheduled Task (win)
│   │   ├── ipc.rs             Socket/Pipe ↔ Python-Daemon
│   │   ├── ble_scan.rs        btleplug
│   │   ├── crash.rs           Bug-Report-Bundle
│   │   ├── tray.rs            Menubar-Icon
│   │   └── updater.rs         Tauri-Updater
│   ├── capabilities/          Tauri-2-Permissions
│   ├── icons/                 PNG/ICNS/ICO für Bundle + Tray
│   ├── macos/entitlements.plist
│   ├── tauri.conf.json
│   ├── Cargo.toml
│   └── build.rs
├── resources/                 ── nicht eingecheckt ──
│   ├── firmware/*.bin         (über copy_firmware_to_companion.py befüllt)
│   └── daemon/clawdmeter-daemon-*  (über build_daemon_bundle.py befüllt)
├── .env.local                 (nicht eingecheckt; aus .env.local.example abgeleitet)
├── package.json
├── tsconfig.json
└── vite.config.ts
```

Sämtliche IPC-Aufrufe gehen über `src/lib/ipc.ts` → `invoke()` → Rust-Command
in `src-tauri/src/lib.rs`. Rust bleibt dünn; alle Domänen-Logik (Polling,
Provider, Secrets) lebt im Python-Daemon. Vollständige IPC-Spezifikation:
[`../feature-documentation/companion-app/ipc-protocol.md`](../feature-documentation/companion-app/ipc-protocol.md).

---

## Dev-Workflow

### Erststart

```bash
cd companion
npm install                  # installiert tauri-cli und Frontend-Deps
npm run tauri:dev            # öffnet Desktop-Fenster mit Hot-Reload
```

Beim ersten Start kompiliert Cargo die Rust-Dependencies (~5 min). Folgeläufe
sind incremental und brauchen wenige Sekunden.

### UI-only ohne Daemon

```bash
VITE_MOCK_IPC=1 npm run dev  # Frontend nur — alle IPC-Calls liefern Mock-Daten
```

Praktisch für rein visuelle Arbeit (Routes, Styling, Layout). `src/lib/ipc.ts`
erkennt das Flag und schaltet auf Fixture-Responses um — die Tauri-Runtime
läuft dabei gar nicht.

### Typen-Checks

```bash
npx tsc -b               # TypeScript-Build (referenced projects)
cargo check --manifest-path src-tauri/Cargo.toml
```

---

## Bauen — Schritt für Schritt

Ein Companion-Release besteht aus **drei Build-Artefakten**, die in dieser
Reihenfolge entstehen:

1. **Firmware-Binaries** (`firmware/`) → in `companion/resources/firmware/` einbetten
2. **Daemon-Bundles** (`daemon/`) → in `companion/resources/daemon/` einbetten
3. **Companion-App-Bundle** (Tauri) → DMG bzw. NSIS-Installer in `dist/`

Tauri bricht ohne **beide** Resource-Bundles mit „resource not found" ab.

### 1. Firmware-Binaries einbetten

```bash
# Aus dem Repo-Root
pio run -d firmware -e wine-216
pio run -d firmware -e standard-216
pio run -d firmware -e standard-180
python3 tools/copy_firmware_to_companion.py
# → companion/resources/firmware/{wine-216,standard-216,standard-180}.bin
```

Das Skript kopiert `firmware.factory.bin` (gemergt: Bootloader +
Partition-Table + App), **nicht** `firmware.bin`. Letzteres würde beim
Flashen die ersten 64 KB überschreiben und das Gerät beim Boot bricken.

### 2. Daemon-Bundle bauen

#### macOS-arm64 (lokal)

```bash
# Aus dem Repo-Root
./daemon/.venv/bin/python tools/build_daemon_bundle.py
# → companion/resources/daemon/clawdmeter-daemon-macos-arm64
```

PyInstaller bündelt den **laufenden** Python-Interpreter — ein Cross-Compile
für Windows existiert nicht. Für den Windows-Daemon gibt es zwei Wege:

#### Windows-x64, Variante A — aus CI-Artifact ziehen

```bash
gh run list --workflow release-companion.yml --status success -L 1
gh run download <RUN_ID> -n daemon-clawdmeter-daemon-win-x64.exe \
    -D companion/resources/daemon
```

Erfordert `gh` + Push-Rechte aufs Repo. Falls kein grüner Lauf existiert:
„Actions" → „release-companion" → „Run workflow" (workflow_dispatch).

#### Windows-x64, Variante B — in Windows-VM gebaut

```bash
# In der VM (UTM/Parallels/Bootcamp):
python tools\build_daemon_bundle.py

# Auf dem Mac:
scp user@winvm:~/clawdmeter/companion/resources/daemon/clawdmeter-daemon-win-x64.exe \
    companion/resources/daemon/
```

Beide Pfade werden vom Release-Skript automatisiert (`--pull-win-daemon`
bzw. `--win-daemon-path <pfad>`, siehe [unten](#one-shot-release-via-skript)).

### 3. Signing-Credentials einrichten

```bash
cp .env.local.example .env.local
$EDITOR .env.local
direnv allow   # falls direnv installiert
```

Pflichtfelder in `.env.local`:

| Variable | Inhalt | Quelle |
|---|---|---|
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: Dein Name (TEAMID)` | `security find-identity -v -p codesigning` |
| `APPLE_TEAM_ID` | 10-stellige Team-ID | Apple Developer Account |
| `APPLE_API_KEY` | Key-ID (~10 Zeichen) | App Store Connect API |
| `APPLE_API_ISSUER` | Issuer-UUID | App Store Connect API |
| `APPLE_API_KEY_PATH` | Absoluter Pfad zur `.p8` | von Apple einmalig generiert |
| `TAURI_SIGNING_PRIVATE_KEY` | Absoluter Pfad zum Updater-Key | siehe [Tauri-Updater](#tauri-updater-einrichten) |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Passwort des Key-Files | bei Generation gesetzt |

`APPLE_CERTIFICATE` / `APPLE_CERTIFICATE_PASSWORD` **nicht** lokal setzen — die
sind nur für CI, wo das `.p12` in eine temporäre Keychain importiert wird.

Verifizieren:

```bash
echo $APPLE_TEAM_ID                            # darf nicht leer sein
security find-identity -v -p codesigning | grep "$APPLE_SIGNING_IDENTITY"
ls "$APPLE_API_KEY_PATH"                       # muss existieren
ls "$TAURI_SIGNING_PRIVATE_KEY"                # muss existieren
```

Ohne diese ENV-Vars produziert der Build einen **unsigned** DMG, der beim
ersten Start die Gatekeeper-Warnung auslöst. Funktional ist das ok für Tests.

### 4. macOS-Release-Bundle (aarch64)

```bash
cd companion
npx @tauri-apps/cli build --target aarch64-apple-darwin
# → src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/Clawdmeter_<version>_aarch64.dmg
```

Tauri liest die Apple-Identity aus dem ENV, ruft `codesign`, dann
`notarytool submit --wait` auf und stapelt das Notarization-Ticket in den DMG.
Dauer: ~3 min Build + 2–5 min Notarization.

Für nicht-signierte Test-Builds reicht der kürzere Pfad:

```bash
npm run tauri:build
# → src-tauri/target/release/bundle/dmg/Clawdmeter_<version>_aarch64.dmg
```

### 5. Windows-Release-Bundle (Cross-Build vom Mac)

```bash
cd companion
npx @tauri-apps/cli build \
    --target x86_64-pc-windows-msvc \
    --runner cargo-xwin \
    --bundles nsis
# → src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/Clawdmeter_<version>_x64-setup.exe
```

Der erste Lauf lädt das MSVC-SDK (~500 MB) nach `~/.xwin-cache/`. Folgeläufe
sind incremental und brauchen < 1 min.

Bis ein EV-Code-Signing-Cert beschafft ist, ist der Installer **unsigned** —
Anwender sehen beim ersten Start „Windows hat Ihren PC geschützt" →
„Weitere Informationen" → „Trotzdem ausführen".

---

## One-Shot-Release via Skript

`tools/release-companion.sh` fasst alle Phasen zusammen:

```bash
./tools/release-companion.sh --pull-win-daemon --full
```

| Flag | Wirkung |
|---|---|
| `--mac` | nur macOS-Bundle |
| `--win` | nur Windows-Bundle |
| `--full` | mac + win |
| `--pull-win-daemon` | Windows-Daemon-Binary aus letztem grünen CI-Lauf ziehen |
| `--win-daemon-path <pfad>` | Windows-Daemon-Binary aus angegebenem Pfad kopieren |
| `--skip-firmware` | Firmware-Builds überspringen (Binaries bereits in `resources/firmware/`) |
| `--skip-daemon` | Daemon-Build überspringen (Binaries bereits in `resources/daemon/`) |

Beispiele:

```bash
# Nur macOS, FW + Daemon bereits gebaut
./tools/release-companion.sh --mac --skip-firmware --skip-daemon

# Nur Windows, Daemon aus lokaler VM-Kopie
./tools/release-companion.sh --win --win-daemon-path ~/Downloads/clawdmeter-daemon-win-x64.exe

# Volles Release
./tools/release-companion.sh --pull-win-daemon --full
```

Finale Artefakte landen in `dist/`.

---

## Tauri-Updater einrichten

Einmalig pro Repo:

```bash
mkdir -p ~/.tauri
npx @tauri-apps/cli signer generate -w ~/.tauri/clawdmeter.key
```

Den ausgegebenen **Public-Key** in [`src-tauri/tauri.conf.json`](src-tauri/tauri.conf.json) →
`plugins.updater.pubkey` eintragen. **Privatkey-Pfad + Passwort** in
`.env.local`:

```bash
TAURI_SIGNING_PRIVATE_KEY="/Users/<user>/.tauri/clawdmeter.key"
TAURI_SIGNING_PRIVATE_KEY_PASSWORD="<key-passwort>"
```

Der Build erzeugt automatisch eine `latest.json` neben den DMG/EXE-Artefakten.
Die App pollt gegen den Endpoint in `tauri.conf.json` →
`plugins.updater.endpoints`. Privatkey gehört zusätzlich als
GitHub-Secret in CI (`TAURI_SIGNING_PRIVATE_KEY` /
`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`).

---

## Versionierung

Vor jedem Release **alle drei** Versionen synchron halten:

1. [`package.json`](package.json) → `version`
2. [`src-tauri/tauri.conf.json`](src-tauri/tauri.conf.json) → `version`
3. [`../daemon/clawdmeter_daemon/__init__.py`](../daemon/clawdmeter_daemon/__init__.py) → `__version__`

Empfohlener Tag-Workflow:

```bash
# 1. Versionen bumpen (alle drei Files)
$EDITOR package.json src-tauri/tauri.conf.json ../daemon/clawdmeter_daemon/__init__.py

# 2. Committen + taggen
git commit -am "Companion vX.Y.Z"
git tag companion-vX.Y.Z

# 3. Release bauen + sanity-check
./tools/release-companion.sh --pull-win-daemon --full
# manuell starten: DMG im Finder, EXE in Windows-VM

# 4. Tag pushen → CI bestätigt die Artefakte
git push --tags

# 5. Falls die CI nicht publisht:
gh release create companion-vX.Y.Z dist/*
```

Firmware-Versionen werden implizit über die PlatformIO-Builds des Tags
mitgezogen.

---

## CI / GitHub Actions

[`.github/workflows/release-companion.yml`](../.github/workflows/release-companion.yml) deckt drei Phasen ab:

1. **build-daemon-bundles** — PyInstaller-Build auf macOS-14 und windows-latest.
   Artefakte: zwei Daemon-Binaries.
2. **build-firmware** — PlatformIO-Build aller drei Envs auf ubuntu-latest.
   Artefakte: drei `firmware.bin`.
3. **build-companion** — Tauri-Build auf macOS-14 (signed/notarized) und
   windows-latest (unsigned). Lädt Artefakte aus 1+2, bündelt sie in
   `companion/resources/`, dann `npx tauri build`.

Trigger:

* Push eines Tags `companion-vX.Y.Z` → Vollrelease + GitHub-Release.
* `workflow_dispatch` → Smoke-Test ohne Release-Publish.

Erforderliche Repository-Secrets:

| Secret | Inhalt |
|---|---|
| `APPLE_CERTIFICATE` | base64-codiertes `.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | `.p12`-Passwort |
| `APPLE_SIGNING_IDENTITY` | Identity-String |
| `APPLE_TEAM_ID` | 10-stellige Team-ID |
| `APPLE_API_KEY` | App Store Connect Key-ID |
| `APPLE_API_ISSUER` | App Store Connect Issuer-UUID |
| `APPLE_API_KEY_BASE64` | base64-codiertes `.p8` |
| `TAURI_SIGNING_PRIVATE_KEY` | Privatkey-Inhalt (nicht Pfad) |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Key-Passwort |

### Base64-Secrets erzeugen

GitHub-Secrets sind reine Strings; Binärdateien (`.p12`, `.p8`) müssen vor dem
Einfügen base64-codiert werden. Auf macOS:

```bash
# 1. .p12 (Developer ID Application Certificate, aus Keychain exportiert)
base64 -i DeveloperID.p12 | pbcopy
# → in GitHub: Settings → Secrets → APPLE_CERTIFICATE einfügen

# 2. .p8 (App Store Connect API Key)
base64 -i AuthKey_<KEYID>.p8 | pbcopy
# → in GitHub: Settings → Secrets → APPLE_API_KEY_BASE64 einfügen
```

Auf Linux/WSL identisch, nur ohne `pbcopy`:

```bash
base64 -w0 DeveloperID.p12 > cert.b64        # -w0 = keine Zeilenumbrüche
base64 -w0 AuthKey_<KEYID>.p8 > key.b64
```

Die GitHub-UI akzeptiert beide Varianten (mit und ohne Zeilenumbrüche); der
CI-Schritt decodiert mit `base64 -d` und legt das Original-Binary in einer
temporären Keychain bzw. einem Temp-File ab.

> **Sicherheit:** Nach dem Einfügen die base64-Zwischendateien wieder löschen
> (`rm cert.b64 key.b64`). Der Klartext-Schlüssel im Klartext zu cat'ten und
> in Shell-History abzulegen, ist genauso gefährlich wie das Original.

---

## Troubleshooting

### „resource fork, Finder information, or similar detritus not allowed"

Codesign weigert sich zu signieren, weil das `.app`-Bundle einen
`com.apple.FinderInfo`-xattr trägt. Diagnose:

```bash
xattr -lr companion/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Clawdmeter.app \
    | grep -E "FinderInfo|ResourceFork|fileprovider"
```

Häufigste Ursache: Das Repo liegt unter `~/Documents` und macOS hat
„Schreibtisch & Dokumente in iCloud" aktiv — der iCloud-FileProvider
indexiert das frisch erzeugte Bundle und setzt dabei `FinderInfo` +
`com.apple.fileprovider.fpfs#P`. Andere FileProvider (Google Drive,
Dropbox) verhalten sich identisch.

**Quickfix für den aktuellen Build:**

```bash
xattr -cr companion/src-tauri/target/aarch64-apple-darwin/release/bundle
cd companion
npx @tauri-apps/cli build --target aarch64-apple-darwin
```

**Wenn der xattr während des Bundlings sofort wieder gesetzt wird**, das
Cargo-Target-Verzeichnis aus dem iCloud-Pfad rauslegen:

```bash
export CARGO_TARGET_DIR="$HOME/.cargo-target/clawdmeter"
mkdir -p "$CARGO_TARGET_DIR"
cd companion
npx @tauri-apps/cli build --target aarch64-apple-darwin
# DMG liegt dann unter $CARGO_TARGET_DIR/aarch64-apple-darwin/release/bundle/dmg/
```

Bonus: incrementelle Builds werden spürbar schneller, weil Cargo-Writes
nicht mehr durch den iCloud-Sync laufen.

### „no identity found" / „errSecInternalComponent" beim macOS-Build

`security find-identity -v -p codesigning` listet deinen Eintrag nicht. Der
private Schlüssel ist in einer falschen Keychain oder das Cert ist abgelaufen.
Lösung: Cert in „login.keychain-db" duplizieren oder neu installieren.

### Notarization hängt auf „in progress"

Apple-API antwortet langsam. Realer Status:

```bash
xcrun notarytool log <UUID> --apple-id $APPLE_ID \
    --team-id $APPLE_TEAM_ID --password $APPLE_PASSWORD
```

Falls verloren: Build erneut starten — Tauri deduplifiziert über die
Submission-ID.

### `cargo-xwin` schlägt mit „failed to find link.exe" fehl

Der xwin-Cache ist leer und das MSVC-SDK wurde noch nicht akzeptiert. Lösung:

```bash
cargo xwin --accept-license
```

Danach erneut bauen.

### Windows-Daemon-Binary fehlt nach `--pull-win-daemon`

Es gibt keinen grünen `release-companion.yml`-Lauf auf `main`. Trigger
manuell via „Actions" → „release-companion" → „Run workflow"
(workflow_dispatch). Sobald grün, läuft `--pull-win-daemon` durch.

### NSIS bricht mit „Icon file not found" ab

`src-tauri/icons/icon.ico` fehlt. Aus einem 1024×1024-PNG generieren:

```bash
npx @tauri-apps/cli icon src-tauri/icons/icon.png -o src-tauri/icons
```

### Tauri-Build bricht mit „resource not found"

`resources/firmware/*.bin` oder `resources/daemon/clawdmeter-daemon-*` fehlt.
Beide vor `npm run tauri:build` befüllen (Schritte 1 + 2 oben).

### Rust-Build ist extrem langsam

Beim Erststart ist das normal (~5 min für ca. 600 Crates). Folgeläufe
nutzen `target/`-Cache. Wer regelmäßig zwischen Branches wechselt, kann
`sccache` (`brew install sccache`) als Wrapper aktivieren — `~/.cargo/config.toml`:

```toml
[build]
rustc-wrapper = "sccache"
```

### Erststart der App schlägt mit „Daemon connection refused" fehl

Der Onboarding-Wizard installiert den Daemon erst beim ersten Klick auf
„Daemon starten". Vorher ist das erwartetes Verhalten. Sollte das danach
weiter passieren: `tail -f ~/Library/Logs/clawdmeter-daemon.log`.

### Sicherheits-Hinweise

* `.env.local` enthält Pfade zu Privatkeys und API-Issuer-IDs.
  **Niemals committen** — das `*.local`-Pattern in [`.gitignore`](.gitignore) schützt davor.
* `.p8` (Notarization) und Tauri-Signing-Key liegen außerhalb des Repos.
  Im Backup-Tresor sichern.
* `direnv` lädt Variablen nur in Subprocesses; sie tauchen nicht in
  `~/.zsh_history` auf.
* `.envrc` selbst ist eingecheckt (legt nur das Layout fest, keine Werte) —
  das ist sicher.

---

## Architektur kurz

```
companion/
├── src/                React + Vite UI
│   ├── routes/         Landing, Flash, Setup, Pair, Status
│   ├── components/
│   └── lib/            ipc.ts, strings.de.ts, platform.ts
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
[`../feature-documentation/companion-app/ipc-protocol.md`](../feature-documentation/companion-app/ipc-protocol.md).
