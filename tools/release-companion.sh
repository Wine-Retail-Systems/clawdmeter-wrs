#!/usr/bin/env bash
# Lokales Release-Skript für die Clawdmeter Companion-App.
#
# Stellt drei Pfade bereit:
#   --mac        nur macOS-Bundle (Daemon + Firmware + signed/notarized DMG)
#   --win        nur Windows-Bundle (MSI/NSIS via cargo-xwin) — Daemon-Bin
#                muss vorher entweder via --pull-win-daemon aus CI geholt
#                oder per --win-daemon-path <pfad> übergeben werden
#   --full       beides
#
# Voraussetzungen siehe feature-documentation/companion-app/local-build.md.
#
# Verwendung:
#   ./tools/release-companion.sh --full
#   ./tools/release-companion.sh --mac
#   ./tools/release-companion.sh --pull-win-daemon --win
#   ./tools/release-companion.sh --win-daemon-path ~/Downloads/clawdmeter-daemon-win-x64.exe --win

set -euo pipefail

# ─── Paths ──────────────────────────────────────────────────────────────
REPO="$(cd "$(dirname "$0")/.." && pwd)"
COMPANION="$REPO/companion"
FW_DIR="$COMPANION/resources/firmware"
DAEMON_DIR="$COMPANION/resources/daemon"
DIST="$REPO/dist"
ENV_FILE="$COMPANION/.env.local"

# ─── Args ───────────────────────────────────────────────────────────────
DO_MAC=0
DO_WIN=0
PULL_WIN_DAEMON=0
WIN_DAEMON_PATH=""
SKIP_FIRMWARE=0
SKIP_DAEMON=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --mac) DO_MAC=1 ;;
        --win) DO_WIN=1 ;;
        --full) DO_MAC=1; DO_WIN=1 ;;
        --pull-win-daemon) PULL_WIN_DAEMON=1 ;;
        --win-daemon-path) WIN_DAEMON_PATH="$2"; shift ;;
        --skip-firmware) SKIP_FIRMWARE=1 ;;
        --skip-daemon) SKIP_DAEMON=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
    esac
    shift
done

if [ "$DO_MAC" = 0 ] && [ "$DO_WIN" = 0 ]; then
    echo "Bitte --mac, --win oder --full angeben."
    exit 2
fi

# ─── Helpers ────────────────────────────────────────────────────────────
log() { printf "\n\033[1;35m▶ %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "Fehlt: $1 — siehe local-build.md"; exit 1; }; }

# ─── Env laden ──────────────────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    log "Lade $ENV_FILE"
    set -a; . "$ENV_FILE"; set +a
else
    echo "Keine $ENV_FILE — siehe companion/.env.local.example" >&2
    [ "$DO_MAC" = 1 ] && exit 1
fi

mkdir -p "$DIST" "$FW_DIR" "$DAEMON_DIR"

# ─── Phase 1: Firmware bauen (3 Envs) ───────────────────────────────────
if [ "$SKIP_FIRMWARE" = 0 ]; then
    log "Firmware: PlatformIO-Builds für wine-216 / standard-216 / standard-180"
    need pio
    pio run -d "$REPO/firmware" -e wine-216
    pio run -d "$REPO/firmware" -e standard-216
    pio run -d "$REPO/firmware" -e standard-180
    python3 "$REPO/tools/copy_firmware_to_companion.py"
fi

# ─── Phase 2: Daemon-Bundles ────────────────────────────────────────────
DAEMON_VENV="$REPO/daemon/.venv/bin/python"
if [ ! -x "$DAEMON_VENV" ]; then
    DAEMON_VENV="$(command -v python3)"
fi

if [ "$DO_MAC" = 1 ] && [ "$SKIP_DAEMON" = 0 ]; then
    log "Daemon-Bundle (mac, arm64) via PyInstaller"
    "$DAEMON_VENV" "$REPO/tools/build_daemon_bundle.py" --skip-smoke
fi

if [ "$DO_WIN" = 1 ] && [ "$SKIP_DAEMON" = 0 ]; then
    log "Daemon-Bundle (Windows, x64)"
    # PyInstaller kann nicht cross-compilen. Wir holen die Datei entweder
    # aus dem letzten grünen GitHub-Actions-Run oder via expliziten Pfad
    # (z. B. aus einer Windows-VM gescpt).
    DAEMON_WIN="$DAEMON_DIR/clawdmeter-daemon-win-x64.exe"
    if [ -n "$WIN_DAEMON_PATH" ]; then
        cp -v "$WIN_DAEMON_PATH" "$DAEMON_WIN"
    elif [ "$PULL_WIN_DAEMON" = 1 ]; then
        need gh
        log "Hole letzten erfolgreichen daemon-clawdmeter-daemon-win-x64.exe via gh"
        cd "$REPO"
        RUN_ID="$(gh run list \
            --workflow release-companion.yml \
            --branch main \
            --status success \
            --limit 1 \
            --json databaseId -q '.[0].databaseId')"
        if [ -z "$RUN_ID" ]; then
            echo "Kein grüner Workflow-Lauf gefunden. Trigger ihn (workflow_dispatch) und warte." >&2
            exit 1
        fi
        TMPD="$(mktemp -d)"
        gh run download "$RUN_ID" -n daemon-clawdmeter-daemon-win-x64.exe -D "$TMPD"
        cp "$TMPD/clawdmeter-daemon-win-x64.exe" "$DAEMON_WIN"
        rm -rf "$TMPD"
    else
        if [ ! -f "$DAEMON_WIN" ]; then
            echo "Kein Windows-Daemon-Bundle in $DAEMON_WIN." >&2
            echo "Optionen:" >&2
            echo "  a) --pull-win-daemon  (zieht aus letztem grünen GitHub-Actions-Lauf)" >&2
            echo "  b) --win-daemon-path  (lokaler Pfad, z. B. aus Windows-VM)" >&2
            echo "  c) Manuell in $DAEMON_DIR ablegen, dann --skip-daemon nutzen" >&2
            exit 1
        fi
        log "Reuse existing $DAEMON_WIN"
    fi
fi

# ─── Phase 3: Companion-App ─────────────────────────────────────────────
need node
PM="$(command -v pnpm || command -v npm)"
[ -z "$PM" ] && { echo "Weder pnpm noch npm gefunden"; exit 1; }
log "Companion: dependencies via $(basename "$PM")"
cd "$COMPANION"
if [ ! -d node_modules ]; then
    "$PM" install
fi

if [ "$DO_MAC" = 1 ]; then
    log "Companion (macOS): signed + notarized DMG"
    # Tauri-CLI nimmt sich folgende Env-Vars automatisch:
    #   APPLE_SIGNING_IDENTITY, APPLE_TEAM_ID,
    #   APPLE_API_KEY, APPLE_API_ISSUER, APPLE_API_KEY_PATH,
    #   TAURI_SIGNING_PRIVATE_KEY, TAURI_SIGNING_PRIVATE_KEY_PASSWORD
    npx -y @tauri-apps/cli build --target aarch64-apple-darwin
    cp -v "$COMPANION/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/"*.dmg "$DIST/"
fi

if [ "$DO_WIN" = 1 ]; then
    log "Companion (Windows): cargo-xwin → NSIS"
    need rustup
    rustup target add x86_64-pc-windows-msvc >/dev/null
    if ! command -v cargo-xwin >/dev/null 2>&1; then
        cargo install --locked cargo-xwin
    fi
    command -v makensis >/dev/null 2>&1 || \
        { echo "makensis fehlt — \`brew install nsis\`"; exit 1; }
    # Tauri 2 unterstützt cross-build via "--runner cargo-xwin" für Windows-MSVC.
    # MSI-Bundler braucht WiX (nicht ohne Schmerzen auf Mac). Wir bauen daher
    # nur das NSIS-Setup-EXE; die CI baut das MSI separat.
    npx -y @tauri-apps/cli build \
        --target x86_64-pc-windows-msvc \
        --runner cargo-xwin \
        --bundles nsis
    cp -v "$COMPANION/src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/"*.exe "$DIST/"
fi

# ─── Phase 4: Zusammenfassung ───────────────────────────────────────────
log "Fertig. Artifacts in $DIST:"
ls -lh "$DIST"
