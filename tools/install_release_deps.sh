#!/usr/bin/env bash
# Installiert alle Build-Tools, die `tools/release-companion.sh` für
# mac- UND windows-cross-Builds braucht. Idempotent — bereits vorhandene
# Tools werden übersprungen.
#
# Setzt voraus:
#   • macOS mit Xcode CLT
#   • Homebrew
#
# Was hier NICHT installiert wird (manuelle Schritte):
#   • Apple Developer ID Cert in Keychain → siehe build-and-release.md
#   • App Store Connect API Key (.p8) → siehe build-and-release.md
#   • Tauri Updater Signing Key → siehe build-and-release.md
#   • Pubkey-Eintrag in tauri.conf.json
#
# Nutzung:
#   ./tools/install_release_deps.sh

set -euo pipefail

log() { printf "\n\033[1;35m▶ %s\033[0m\n" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Dieses Skript läuft nur auf macOS." >&2
    exit 1
fi

# ─── Homebrew ───────────────────────────────────────────────────────────
if ! have brew; then
    log "Homebrew installieren"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# ─── Xcode CLT (Codesign, notarytool) ───────────────────────────────────
if ! xcode-select -p >/dev/null 2>&1; then
    log "Xcode Command Line Tools installieren"
    xcode-select --install
    echo "Bitte den Apple-Dialog bestätigen, dann dieses Skript erneut starten."
    exit 0
fi

# ─── Brew-Pakete ────────────────────────────────────────────────────────
BREW_PKGS=(node platformio nsis direnv gh)
log "Brew-Pakete: ${BREW_PKGS[*]}"
for pkg in "${BREW_PKGS[@]}"; do
    if ! brew list "$pkg" >/dev/null 2>&1; then
        brew install "$pkg"
    else
        echo "  ✓ $pkg"
    fi
done

# ─── pnpm via Corepack ──────────────────────────────────────────────────
if ! have pnpm; then
    log "pnpm aktivieren (Corepack)"
    corepack enable
    corepack prepare pnpm@latest --activate
fi

# ─── Rust + Targets ─────────────────────────────────────────────────────
if ! have rustup; then
    log "rustup installieren"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    # shellcheck disable=SC1091
    . "$HOME/.cargo/env"
fi

log "Rust-Targets sicherstellen"
rustup target add aarch64-apple-darwin x86_64-pc-windows-msvc

# ─── cargo-xwin (Windows-Cross-Compile) ─────────────────────────────────
if ! have cargo-xwin; then
    log "cargo-xwin installieren"
    cargo install --locked cargo-xwin
fi

# ─── Daemon-venv ────────────────────────────────────────────────────────
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/daemon/.venv"
if [ ! -x "$VENV/bin/python" ]; then
    log "Python-venv für Daemon anlegen"
    python3 -m venv "$VENV"
fi
log "PyInstaller + bleak + httpx im venv"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "pyinstaller>=6.10" "bleak>=0.22" "httpx>=0.27"

# ─── direnv-Hook in ~/.zshrc (idempotent) ───────────────────────────────
ZSHRC="$HOME/.zshrc"
if ! grep -q 'direnv hook' "$ZSHRC" 2>/dev/null; then
    log "direnv-Hook in $ZSHRC ergänzen"
    printf '\n# direnv\neval "$(direnv hook zsh)"\n' >> "$ZSHRC"
fi

# ─── gh auth status (informativ) ───────────────────────────────────────
if have gh; then
    if ! gh auth status >/dev/null 2>&1; then
        log "GitHub CLI ist noch nicht authentifiziert — \`gh auth login\`"
    fi
fi

log "Fertig. Nächste Schritte:"
cat <<EOF
  1. companion/.env.local anlegen (cp companion/.env.local.example companion/.env.local)
     und mit den echten Werten füllen.
  2. direnv allow (im Repo-Root)
  3. ./tools/release-companion.sh --mac        — Smoketest macOS-Build
  4. ./tools/release-companion.sh --pull-win-daemon --full
EOF
