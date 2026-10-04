#include <Arduino.h>
#include "config.h"
#include "laser.h"

namespace laser {
static bool on = false;
static uint32_t since = 0;

// Pin level for a laser state; LASER_ACTIVE_LOW flips it for robots wired without the transistor.
static void drive(bool v) { digitalWrite(PIN_LASER, (v != LASER_ACTIVE_LOW) ? HIGH : LOW); }

void begin() { drive(false); pinMode(PIN_LASER, OUTPUT); drive(false); }  // level first, so it never glitches on
void set(bool v) { on = v; since = millis(); drive(v); }
bool isOn() { return on; }
void update() { if (on && millis() - since > LASER_TIMEOUT_MS) set(false); }
}
