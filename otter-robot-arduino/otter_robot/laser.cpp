#include <Arduino.h>
#include "config.h"
#include "laser.h"

namespace laser {
static bool on = false;
static uint32_t since = 0;

void begin() { pinMode(PIN_LASER, OUTPUT); digitalWrite(PIN_LASER, LOW); }
void set(bool v) { on = v; since = millis(); digitalWrite(PIN_LASER, v ? HIGH : LOW); }
bool isOn() { return on; }
void update() { if (on && millis() - since > LASER_TIMEOUT_MS) set(false); }
}
