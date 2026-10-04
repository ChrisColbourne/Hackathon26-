#pragma once
namespace motion {
void begin();
void look(float pan, float tilt); // degrees from centre, clamped to safe limits
void home();
bool update();                    // true once, when the head reaches its target
bool moving();
}
