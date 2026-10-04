# Otter robot firmware (ESP32, Arduino IDE)

The ESP32 only obeys JSON commands from the brain (laptop): otter face on the
2.8" ILI9341, pan/tilt servos, laser. Contract: [../docs/GAMEPLAN.md](../docs/GAMEPLAN.md).

## Setup

1. Arduino IDE with **esp32 by Espressif** boards; board: *ESP32 Dev Module*.
2. Libraries (Library Manager): **TFT_eSPI** (Bodmer), **ESP32Servo**, **ArduinoJson** 7.x,
   **WebSockets** (Markus Sattler / links2004).
3. Replace the whole `Documents/Arduino/libraries/TFT_eSPI/User_Setup.h` with
   [TFT_eSPI_User_Setup.h](TFT_eSPI_User_Setup.h).
4. Copy `otter_robot/secrets.example.h` to `otter_robot/secrets.h` and fill in the Wi-Fi
   and the laptop's IP. **Never commit or upload `secrets.h`** (it holds the Wi-Fi password).
5. Open `otter_robot/otter_robot.ino`, upload, Serial Monitor at 115200.
   Unplug the VIN wire before flashing over USB.

## Testing

- The brain: `python -m brain.server` on the laptop (port 8000; `GEMINI_MOCK=1` needs no
  Gemini quota). The robot connects to `ws://LAPTOP_IP:8000/robot`.
- Without the brain: `python test_server.py` (same port) and type `happy`, `think`, `talk`,
  `look -20 10`, `laser -15 -5`, `off`, `home`, or raw JSON.
- Without any server: type JSON in the Serial Monitor, e.g. `{"action":"face","state":"happy"}`.

Commands: `{"action":"face","state":"happy"}` · `{"action":"mouth","level":0.6}` ·
`{"action":"look","pan":-18,"tilt":5}` · `{"action":"laser","on":true,"pan":-22,"tilt":-8}` · `{"action":"home"}`

Angles are degrees from centre: pan + = right, tilt + = up (limits in `config.h`).
A `look` always switches the laser off; use `laser` with `pan`/`tilt` to aim and fire.
Tuning (servo centres, limits, direction, speed, laser timeout) lives in `otter_robot/config.h`.
The LCD is mounted vertically (portrait, 240x320). Otter upside down? Set `SCREEN_ROTATION` to `2` in `config.h`.
