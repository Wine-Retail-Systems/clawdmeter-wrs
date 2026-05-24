#!/bin/bash
# Build and flash Clawdmeter firmware on macOS.
#
# Usage:
#   ./flash-mac.sh                                # Default-Env (wine-216), auto-port
#   ./flash-mac.sh --env=standard-216             # Standard 2.16"
#   ./flash-mac.sh --env=standard-180             # Standard 1.8"
#   ./flash-mac.sh /dev/cu.usbmodem1101           # Default-Env, expliziter Port
#   ./flash-mac.sh --env=standard-216 /dev/cu.usbmodem1101
#
# Verfügbare Envs (siehe firmware/platformio.ini):
#   wine-216, standard-216, standard-180
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default — Wine Edition. Mit --env überschreibbar.
ENV="wine-216"
PORT=""

for arg in "$@"; do
    case "$arg" in
        --env=*)
            ENV="${arg#--env=}"
            ;;
        --help|-h)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        -*)
            echo "Error: unknown option '$arg'"
            exit 1
            ;;
        *)
            PORT="$arg"
            ;;
    esac
done

if [ -z "$PORT" ]; then
    PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
    if [ -z "$PORT" ]; then
        echo "Error: kein /dev/cu.usbmodem* Gerät gefunden. USB-C anschließen."
        exit 1
    fi
fi

if ! command -v pio >/dev/null; then
    echo "Error: 'pio' nicht gefunden. Installiere mit:"
    echo "  brew install platformio"
    exit 1
fi

echo "=== Flashing Clawdmeter ==="
echo "Env:  $ENV"
echo "Port: $PORT"
echo ""

cd "$SCRIPT_DIR/firmware"
pio run -e "$ENV" -t upload --upload-port "$PORT"

echo ""
echo "=== Done ==="
echo "Monitor mit: pio device monitor -p $PORT -b 115200"
