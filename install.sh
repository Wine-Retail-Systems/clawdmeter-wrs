#!/bin/bash
# Linux installer for Clawdmeter daemon (Python + bleak + systemd --user).
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="clawdmeter-daemon"
SERVICE_SRC="$SCRIPT_DIR/daemon/$SERVICE_NAME.service"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
VENV_DIR="$SCRIPT_DIR/daemon/.venv"
DAEMON_PY="$SCRIPT_DIR/daemon/clawdmeter_daemon.py"

echo "=== Clawdmeter Linux install ==="
echo ""

echo "[1/5] Checking dependencies..."
for cmd in python3 bluetoothctl; do
    command -v "$cmd" >/dev/null || { echo "Error: $cmd is required"; exit 1; }
done
echo "  OK"
echo ""

echo "[2/5] Creating Python virtualenv at daemon/.venv ..."
if [ ! -d "$VENV_DIR" ] || ! "$VENV_DIR/bin/python" -c '' 2>/dev/null; then
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "bleak>=0.22" "httpx>=0.27" "tomli>=2.0;python_version<'3.11'"
PYTHON_BIN="$VENV_DIR/bin/python"
echo "  OK ($PYTHON_BIN)"
echo ""

echo "[3/5] Optional provider dependencies"
echo "  AWS Bedrock-Adapter ist aktuell deaktiviert (kein IAM-Pfad konfiguriert)."
echo "  Falls du ihn später reaktivierst, installiere boto3 mit:"
echo "    $VENV_DIR/bin/pip install 'boto3>=1.34'"
echo ""

echo "[4/5] Running interactive setup wizard..."
"$PYTHON_BIN" "$DAEMON_PY" setup
echo ""

echo "[5/5] Installing systemd user service..."
mkdir -p "$USER_SERVICE_DIR"
sed \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    -e "s|__DAEMON_PATH__|${DAEMON_PY}|g" \
    "$SERVICE_SRC" > "$USER_SERVICE_DIR/$SERVICE_NAME.service"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"
echo "  Service enabled and started."
echo ""

echo "=== Done ==="
echo ""
echo "Useful commands:"
echo "  $PYTHON_BIN $DAEMON_PY doctor                        # config + enabled providers"
echo "  $PYTHON_BIN $DAEMON_PY setup                         # re-run setup wizard"
echo "  systemctl --user status $SERVICE_NAME                # status"
echo "  systemctl --user restart $SERVICE_NAME               # restart after config change"
echo "  journalctl --user -u $SERVICE_NAME -f                # live logs"
echo ""
echo "First-time Bluetooth pairing:"
echo "  1. Power on the Clawdmeter."
echo "  2. bluetoothctl scan le"
echo "  3. Find 'Clawdmeter' and note the MAC address."
echo "  4. bluetoothctl pair <MAC>"
echo "  5. bluetoothctl trust <MAC>"
echo ""
