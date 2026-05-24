#!/bin/bash
# Build and flash Clawdmeter firmware on Linux.
#
# Usage:
#   ./flash.sh                              # AMOLED-2.16, /dev/ttyACM0
#   ./flash.sh --board=18                   # AMOLED-1.8, /dev/ttyACM0
#   ./flash.sh --board=216 /dev/ttyACM1     # explicit board + port
#   ./flash.sh /dev/ttyACM1                 # 2.16 with explicit port
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
    PORT="/dev/ttyACM0"
fi

if command -v pio >/dev/null; then
    PIO=pio
elif [ -x "$HOME/.platformio/penv/bin/pio" ]; then
    PIO="$HOME/.platformio/penv/bin/pio"
else
    echo "Error: 'pio' not found in PATH or ~/.platformio/penv/bin/."
    exit 1
fi

echo "=== Flashing Clawdmeter ==="
echo "Board: $ENV"
echo "Port:  $PORT"
echo ""

cd "$SCRIPT_DIR/firmware"
"$PIO" run -e "$ENV" -t upload --upload-port "$PORT"

echo ""
echo "=== Done! ==="
