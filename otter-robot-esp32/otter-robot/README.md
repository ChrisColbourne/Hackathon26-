# Otter robot firmware (ESP32)

1. Copy `include/secrets.example.h` to `include/secrets.h`, then fill in Wi-Fi and the laptop's IP.
2. `pio run -t upload`, then `pio device monitor`.
3. No server yet? Type JSON in the serial monitor, or run `python tools/test_server.py` on the laptop.

Commands: `{"action":"face","state":"happy"}` · `{"action":"mouth","level":0.6}` ·
`{"action":"look","pan":-18,"tilt":5}` · `{"action":"laser","on":true,"pan":-22,"tilt":-8}` · `{"action":"home"}`

Tuning lives in `include/config.h`: servo centres, limits, direction, speed and the laser timeout.
Screen upside down? Change `setRotation(1)` to `3` in `src/otter.cpp`. Unplug the VIN wire before flashing over USB.
