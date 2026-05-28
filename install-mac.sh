#!/bin/bash
# macOS installer for Clawdmeter daemon (Python + bleak + launchd).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_LABEL="com.clawdmeter.daemon"
PLIST_SRC="$SCRIPT_DIR/daemon/$SERVICE_LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$SERVICE_LABEL.plist"
VENV_DIR="$SCRIPT_DIR/daemon/.venv"
DAEMON_PY="$SCRIPT_DIR/daemon/clawdmeter_daemon.py"
LOG_DIR="$HOME/Library/Logs"
LOG_OUT="$LOG_DIR/clawdmeter-daemon.out.log"
LOG_ERR="$LOG_DIR/clawdmeter-daemon.err.log"

echo "=== Clawdmeter macOS install ==="
echo ""

echo "[1/6] Checking prerequisites..."
for cmd in python3 curl; do
    command -v "$cmd" >/dev/null || { echo "Error: $cmd is required"; exit 1; }
done
echo "  OK"
echo ""

echo "[2/6] Creating Python virtualenv at daemon/.venv ..."
if [ ! -d "$VENV_DIR" ] || ! "$VENV_DIR/bin/python" -c '' 2>/dev/null; then
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "bleak>=0.22" "httpx>=0.27" "tomli>=2.0;python_version<'3.11'"
PYTHON_BIN="$VENV_DIR/bin/python"
echo "  OK ($PYTHON_BIN)"
echo ""

echo "[3/6] Optional provider dependencies"
echo "  AWS Bedrock-Adapter ist aktuell deaktiviert (kein IAM-Pfad konfiguriert)."
echo "  Falls du ihn später reaktivierst, installiere boto3 mit:"
echo "    $VENV_DIR/bin/pip install 'boto3>=1.34'"
echo ""

echo "[4/6] Running interactive setup wizard..."
"$PYTHON_BIN" "$DAEMON_PY" setup
echo ""

echo "[5/6] Rendering launchd plist..."
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
sed \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    -e "s|__DAEMON_PATH__|${DAEMON_PY}|g" \
    -e "s|__REPO_DIR__|${SCRIPT_DIR}|g" \
    -e "s|__LOG_OUT__|${LOG_OUT}|g" \
    -e "s|__LOG_ERR__|${LOG_ERR}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "$PLIST_SRC" > "$PLIST_DST"
echo "  Installed: $PLIST_DST"
echo ""

echo "[6/6] Loading launchd service..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load -w "$PLIST_DST"
echo "  Loaded."
echo ""

echo "=== Done ==="
echo ""
echo "Useful commands:"
echo "  $PYTHON_BIN $DAEMON_PY doctor          # show config + enabled providers"
echo "  $PYTHON_BIN $DAEMON_PY setup           # re-run setup wizard"
echo "  launchctl unload $PLIST_DST            # stop"
echo "  launchctl load -w $PLIST_DST           # start"
echo "  tail -F $LOG_OUT                       # live logs"
echo ""
echo "First-time Bluetooth pairing (after firmware is flashed):"
echo "  1. Power on the device."
echo "  2. Open System Settings → Bluetooth."
echo "  3. Click 'Connect' next to 'Clawdmeter'."
echo "  4. The daemon will discover it within ~30 s and start polling."
echo ""
