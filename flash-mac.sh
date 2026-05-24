#!/bin/bash
# Build and flash Clawdmeter firmware on macOS.
#
# Usage:
#   ./flash-mac.sh                                 # AMOLED-2.16, auto-detect port
#   ./flash-mac.sh --board=18                      # AMOLED-1.8, auto-detect port
#   ./flash-mac.sh --board=216 /dev/cu.usbmodem1101  # explicit board + port
#   ./flash-mac.sh /dev/cu.usbmodem1101              # 2.16 with explicit port
#
# Without -e, `pio run` builds AND flashes every defined env in sequence —
# the second upload silently overwrites the first. Always pass -e.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BOARD="216"
PORT=""

for arg in "$@"; do
    case "$arg" in
        --board=*)
            BOARD="${arg#--board=}"
            ;;
        --env=*)
            ENV_OVERRIDE="${arg#--env=}"
            ;;
        --help|-h)
            sed -n '2,9p' "$0"
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

if [ -n "$ENV_OVERRIDE" ]; then
    ENV="$ENV_OVERRIDE"
else
    case "$BOARD" in
        216) ENV="waveshare_amoled_216" ;;
        18)  ENV="waveshare_amoled_18" ;;
        *)
            echo "Error: unknown --board='$BOARD'. Valid values: 216, 18."
            exit 1
            ;;
    esac
fi

if [ -z "$PORT" ]; then
    PORT=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)
    if [ -z "$PORT" ]; then
        echo "Error: no /dev/cu.usbmodem* device found. Plug in via USB-C."
        exit 1
    fi
fi

if ! command -v pio >/dev/null; then
    echo "Error: 'pio' not found. Install with:"
    echo "  brew install platformio"
    exit 1
fi

echo "=== Flashing Clawdmeter ==="
echo "Board: $ENV"
echo "Port:  $PORT"
echo ""

cd "$SCRIPT_DIR/firmware"
pio run -e "$ENV" -t upload --upload-port "$PORT"

echo ""
echo "=== Done ==="
echo "Monitor with: pio device monitor -p $PORT -b 115200"
