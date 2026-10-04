#pragma once
// ---- Pins (match the wiring guide) ----
#define PIN_PAN    25
#define PIN_TILT   26
#define PIN_LASER  27

// ---- Servo tuning ----
// Angles in the JSON are degrees from centre. pan: + = right, tilt: + = up.
#define PAN_CENTER   90
#define TILT_CENTER  90
#define PAN_LIMIT    60     // max +/- degrees left/right
#define TILT_MIN    -25     // lowest the head can look
#define TILT_MAX     15     // SAFETY: highest it can look, keep the laser below eye level
#define PAN_INVERT   true   // flip if the head turns the wrong way (true since the pan servo was replaced, Oct 4)
#define TILT_INVERT  false
#define SERVO_SPEED  150.0f // max degrees per second

// ---- Laser ----
#define LASER_TIMEOUT_MS 6000 // SAFETY: laser turns itself off after this
// true  = laser lights when GPIO 27 is LOW (laser '-' wired straight to the pin; our robot, Oct 3)
// false = laser lights when GPIO 27 is HIGH (switched through the 2N2222, as in the wiring guide)
#define LASER_ACTIVE_LOW true

// ---- Screen ----
// The LCD is mounted vertically: portrait, 240 wide x 320 tall.
// 0 = otter turned 90 deg counter-clockwise from the old landscape setup (1).
// 2 = the same but 180 deg around: use it if the otter comes out upside down.
#define SCREEN_ROTATION 0

// ---- Wireless firmware updates (ArduinoOTA) ----
// Flash over Wi-Fi with ../flash.sh ota. Optional password: OTA_PASS in secrets.h.
#define OTA_HOSTNAME "otter-robot"   // reachable as otter-robot.local

#include "secrets.h"          // copy secrets.example.h to secrets.h
