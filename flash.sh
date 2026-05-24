#!/bin/bash
# Build and flash Clawdmeter firmware on Linux.
#
# Usage:
#   ./flash.sh                              # Default-Env (wine-216), /dev/ttyACM0
#   ./flash.sh --env=standard-216           # Standard 2.16"
#   ./flash.sh --env=standard-180           # Standard 1.8"
#   ./flash.sh /dev/ttyACM1                 # Default-Env, expliziter Port
#   ./flash.sh --env=standard-216 /dev/ttyACM1
#
# Verfügbare Envs (siehe firmware/platformio.ini):
#   wine-216, standard-216, standard-180
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

[ -z "$PORT" ] && PORT="/dev/ttyACM0"

if ! command -v pio >/dev/null; then
    if [ -x "$HOME/.platformio/penv/bin/pio" ]; then
        PIO="$HOME/.platformio/penv/bin/pio"
    else
        echo "Error: 'pio' nicht gefunden."
        echo "Install: pip install --user platformio  (oder via PlatformIO-IDE)"
        exit 1
    fi
else
    PIO="pio"
fi

echo "=== Flashing Clawdmeter ==="
echo "Env:  $ENV"
echo "Port: $PORT"
echo ""

cd "$SCRIPT_DIR/firmware"
"$PIO" run -e "$ENV" -t upload --upload-port "$PORT"

echo ""
echo "=== Done ==="
echo "Monitor mit: $PIO device monitor -p $PORT -b 115200"
