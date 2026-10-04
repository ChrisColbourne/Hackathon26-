#!/usr/bin/env bash
# Build and flash the otter firmware from this laptop (needs arduino-cli + esp32 core).
#   ./flash.sh               over USB (/dev/ttyUSB0; set PORT=... to change). Unplug VIN first!
#   ./flash.sh ota [HOST]    over Wi-Fi to a robot already running OTA firmware
#                            (HOST defaults to otter-robot.local; or pass the robot's IP)
set -euo pipefail
cd "$(dirname "$0")"
CLI="${ARDUINO_CLI:-$HOME/.local/bin/arduino-cli}"
FQBN=esp32:esp32:esp32
BUILD="${XDG_CACHE_HOME:-$HOME/.cache}/otter-tutor/fw-build"   # outside the repo: no odd chars in the path

[ -f otter_robot/secrets.h ] || { echo "otter_robot/secrets.h missing: copy secrets.example.h and fill it in"; exit 1; }
"$CLI" compile --fqbn "$FQBN" --build-path "$BUILD" otter_robot

if [ "${1:-usb}" = ota ]; then
  HOST="${2:-otter-robot.local}"
  ESPOTA="$(ls "$HOME"/.arduino15/packages/esp32/hardware/esp32/*/tools/espota.py | tail -1)"
  PASS="$(sed -nE 's/^#define[[:space:]]+OTA_PASS[[:space:]]+"([^"]*)".*/\1/p' otter_robot/secrets.h)"
  echo "flashing over Wi-Fi -> $HOST"
  python3 "$ESPOTA" -i "$HOST" -f "$BUILD/otter_robot.ino.bin" ${PASS:+-a "$PASS"} -r
else
  "$CLI" upload -p "${PORT:-/dev/ttyUSB0}" --fqbn "$FQBN" --input-dir "$BUILD" otter_robot
fi
