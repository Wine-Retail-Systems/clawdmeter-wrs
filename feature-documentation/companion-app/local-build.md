# Companion-App — Lokaler Release-Workflow

Stand: 2026-05-28

Single-Source-of-Truth für den Bau eines vollständigen Companion-App-
Releases. Deckt sowohl macOS-arm64 als auch Windows-x64 ab, beides vom
selben Mac aus. Ergänzt
[`build-and-release.md`](build-and-release.md) (CI-Sicht) und
[`architecture.md`](architecture.md).

## TL;DR

```bash
# Einmalig
./tools/install_release_deps.sh

# Vor jedem Release
direnv allow                              # falls neu
./tools/release-companion.sh --pull-win-daemon --full
ls dist/
```

`dist/` enthält danach:

* `Clawdmeter_<version>_aarch64.dmg`  — signed + notarized macOS-Bundle
* `Clawdmeter_<version>_x64-setup.exe` — Windows NSIS-Installer (unsigned)

## Was beim Cross-Build funktioniert (und was nicht)

| Komponente | mac → mac | mac → win | Begründung |
|---|---|---|---|
| Firmware (ESP32-S3) | ✅ | ✅ | PlatformIO kapselt die Toolchain |
| Companion-App (Tauri) | ✅ | ✅ via `cargo-xwin` | MSVC-Header werden runtergeladen, NSIS via Homebrew |
| **Daemon (PyInstaller)** | ✅ | ❌ | PyInstaller bundelt den **laufenden** Interpreter — kein Cross-Compile-Pfad existiert. |

Für den Windows-Daemon gibt es zwei verifizierte Wege:

1. **`--pull-win-daemon`** — ziehe das Binary aus dem letzten grünen
   GitHub-Actions-Run (Job `build-daemon-bundles`, Matrix
   `windows-latest`). Erfordert `gh` + Push-Rechte aufs Repo.
2. **`--win-daemon-path <pfad>`** — du baust das Binary einmal in einer
   Windows-VM (UTM/Parallels/Bootcamp) und gibst den Pfad explizit
   mit. Empfohlen, wenn du keine GitHub-Actions-Minuten verbrennen
   willst oder offline arbeitest.

## Voraussetzungen (einmalig)

### macOS-Build

| Tool | Wozu | Install |
|---|---|---|
| Xcode Command Line Tools | clang, codesign, notarytool | `xcode-select --install` |
| Homebrew | Paketquelle | <https://brew.sh> |
| Node.js ≥ 20 | Frontend-Build | `brew install node` oder via nvm |
| pnpm (optional) | Bevorzugter Package-Manager | `corepack enable && corepack prepare pnpm@latest --activate` |
| Rust (stable) | Tauri-Backend | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| Python ≥ 3.11 | Daemon + PyInstaller | `brew install python@3.13` |
| PlatformIO CLI | Firmware-Builds | `pipx install platformio` oder `brew install platformio` |
| direnv (optional) | `.env.local` automatisch laden | `brew install direnv` |

### Windows-Cross-Build vom Mac

| Tool | Wozu | Install |
|---|---|---|
| Rust-Target `x86_64-pc-windows-msvc` | Cross-Target | `rustup target add x86_64-pc-windows-msvc` |
| `cargo-xwin` | MSVC-SDK-Header für Cross-Compile | `cargo install --locked cargo-xwin` |
| NSIS | Windows-Installer-Bundler | `brew install nsis` |
| `gh` CLI | (nur bei `--pull-win-daemon`) | `brew install gh && gh auth login` |

> **Hinweis zum MSI-Format**: WiX-basierter `.msi`-Bau auf Mac ist
> technisch möglich (`brew install mono` + manueller WiX-Bin-Download),
> aber fragil. Wir bauen lokal **nur NSIS** (`.exe`-Installer). Die CI
> baut zusätzlich MSI auf einem echten Windows-Runner; wenn du beides
> brauchst, push einen Tag.

### Apple-Signing-Identity & Notarization-Key

Beide einmalig anlegen, dann landen sie in `companion/.env.local`:

1. **Developer ID Application Certificate** in der Keychain (siehe
   `build-and-release.md` Abschnitt „Apple-Signing").
2. **App Store Connect API Key** für Notarization
   (`AuthKey_<KEYID>.p8`). Pfad und KEYID in `.env.local`.
3. **Tauri Updater Key** generieren:
   ```bash
   mkdir -p ~/.tauri
   pnpm --dir companion exec tauri signer generate -w ~/.tauri/clawdmeter.key
   ```
   Pubkey in `companion/src-tauri/tauri.conf.json` →
   `plugins.updater.pubkey` eintragen. Privkey-Pfad + Passwort in
   `.env.local`.

## Der Workflow im Detail

### Phase 0 — `.env.local` einrichten

```bash
cp companion/.env.local.example companion/.env.local
# in $EDITOR die echten Werte eintragen
direnv allow      # falls direnv installiert
```

Verifizieren:

```bash
echo $APPLE_TEAM_ID                  # darf nicht leer sein
security find-identity -v -p codesigning | grep "$APPLE_SIGNING_IDENTITY"
ls "$APPLE_API_KEY_PATH"             # muss existieren
ls "$TAURI_SIGNING_PRIVATE_KEY"      # muss existieren
```

### Phase 1 — Firmware bauen

```bash
pio run -d firmware -e wine-216
pio run -d firmware -e standard-216
pio run -d firmware -e standard-180
python3 tools/copy_firmware_to_companion.py
# → companion/resources/firmware/{wine-216,standard-216,standard-180}.bin
```

Das Skript greift auf `firmware.factory.bin` (gemergt Bootloader +
Partition-Table + App) zurück, nicht auf `firmware.bin`. Sonst würde
espflash die ersten 64 KB Flash überschreiben und das Gerät bricked
booten.

### Phase 2 — Daemon-Bundles

**macOS-arm64** (lokal):

```bash
./daemon/.venv/bin/python tools/build_daemon_bundle.py
# → companion/resources/daemon/clawdmeter-daemon-macos-arm64
```

**Windows-x64** — eine der beiden Varianten:

```bash
# Variante A — aus dem letzten grünen CI-Lauf
gh run list --workflow release-companion.yml --status success -L 1
gh run download <RUN_ID> -n daemon-clawdmeter-daemon-win-x64.exe \
    -D companion/resources/daemon
mv companion/resources/daemon/clawdmeter-daemon-win-x64.exe \
   companion/resources/daemon/clawdmeter-daemon-win-x64.exe

# Variante B — in der Windows-VM gebaut, per scp gezogen
scp user@winvm:~/clawdmeter/companion/resources/daemon/clawdmeter-daemon-win-x64.exe \
    companion/resources/daemon/
```

Das `release-companion.sh`-Skript automatisiert beide Varianten mit
`--pull-win-daemon` bzw. `--win-daemon-path`.

### Phase 3 — Companion-App-Bundle

**macOS-arm64**:

```bash
cd companion
npx @tauri-apps/cli build --target aarch64-apple-darwin
# → companion/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/Clawdmeter_*.dmg
```

Tauri liest aus dem ENV die Apple-Identity, ruft `codesign`, dann
`notarytool submit --wait` auf, stapelt das Notarization-Ticket in den
DMG. Dauer: ~3 min Build + 2–5 min Notarization.

**Windows-x64**:

```bash
cd companion
npx @tauri-apps/cli build \
    --target x86_64-pc-windows-msvc \
    --runner cargo-xwin \
    --bundles nsis
# → companion/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/Clawdmeter_*.exe
```

Der erste Lauf lädt das MSVC-SDK (~500 MB) nach `~/.xwin-cache/`.
Folgeläufe sind incremental und brauchen < 1 min.

### Phase 4 — Alles zusammen via Skript

```bash
./tools/release-companion.sh --pull-win-daemon --full
```

Das Skript fasst Phase 1–3 zusammen und legt die finalen Artifacts in
`dist/` ab. Sub-Modi:

| Flag | Wirkung |
|---|---|
| `--mac` | nur macOS-Bundle |
| `--win` | nur Windows-Bundle |
| `--full` | beides |
| `--pull-win-daemon` | Windows-Daemon-Binary aus letztem grünen CI-Lauf ziehen |
| `--win-daemon-path <pfad>` | Windows-Daemon-Binary aus angegebenem Pfad kopieren |
| `--skip-firmware` | Firmware-Builds überspringen (FW-Binaries bereits in `resources/firmware/`) |
| `--skip-daemon` | Daemon-Build überspringen (Binaries bereits in `resources/daemon/`) |

## Häufige Stolperfallen

### „no identity found" / „errSecInternalComponent"

`security find-identity -v -p codesigning` listet deinen Eintrag nicht.
Wahrscheinlich ist der private Schlüssel in einer anderen Keychain oder
das Cert ist abgelaufen. Lösung: Cert in „login.keychain-db" duplizieren
oder neu installieren.

### Notarization stuck auf „in progress"

Apple-API antwortet manchmal langsam. `xcrun notarytool log <UUID>
--apple-id $APPLE_ID --team-id $APPLE_TEAM_ID --password $APPLE_PASSWORD`
zeigt den realen Status. In dem Fall den Build erneut starten; Tauri
deduplifiziert über die Submission-ID.

### `cargo-xwin` schlägt fehl mit „failed to find link.exe"

Du hast den Cache geleert und das SDK ist noch nicht da. Lösung:
`cargo xwin --accept-license` einmal ausführen, dann erneut bauen.

### Windows-Daemon-Binary fehlt nach `--pull-win-daemon`

Es gibt keinen grünen `release-companion.yml`-Lauf auf `main`. Trigger:
„Actions" → „release-companion" → „Run workflow" (workflow_dispatch).
Sobald der Job grün ist, läuft `--pull-win-daemon` durch.

### NSIS-Bundle bricht mit „Icon file not found" ab

Im `companion/src-tauri/icons/`-Ordner fehlt `icon.ico`. Lösung:

```bash
npx @tauri-apps/cli icon companion/src-tauri/icons/icon.png \
    -o companion/src-tauri/icons
```

(Ein quadratisches 1024×1024-PNG als Quelle reicht.)

## Versionierung beim Release

Vor `tools/release-companion.sh --full`:

1. `companion/package.json` → `version` bumpen
2. `companion/src-tauri/tauri.conf.json` → `version` synchron
3. `daemon/clawdmeter_daemon/__init__.py` → `__version__` synchron
4. `git commit -am "Companion vX.Y.Z" && git tag companion-vX.Y.Z`
5. `tools/release-companion.sh --pull-win-daemon --full`
6. Sanity-Check: `dist/`-Artifacts manuell starten (Mac + Win-VM)
7. `git push --tags` → CI bestätigt die Release-Artifacts
8. `gh release create companion-vX.Y.Z dist/*` falls die CI nicht
   schon publisht hat

## Sicherheitshinweise

* `companion/.env.local` enthält Pfade zu Privatkeys und API-Issuer-IDs.
  **Niemals committen** — das `*.local`-Pattern in `companion/.gitignore`
  schützt davor.
* Die `.p8`-Datei (Notarization) und die Tauri-Signing-Key-Datei
  liegen außerhalb des Repos (Sascha: `999 - Appstoreconnect/`).
  Im Backup-Tresor sichern.
* `direnv` lädt die Variablen nur in Subprocesses; sie tauchen nicht in
  `~/.zsh_history` auf.
* Der `.envrc` selbst ist eingecheckt (legt nur das Layout fest, keine
  Werte) — das ist sicher.
