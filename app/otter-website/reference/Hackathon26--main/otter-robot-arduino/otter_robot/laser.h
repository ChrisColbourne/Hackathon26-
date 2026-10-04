#pragma once
namespace laser {
void begin();
void set(bool on);
void update();                    // enforces LASER_TIMEOUT_MS
bool isOn();
}
