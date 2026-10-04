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
#define PAN_INVERT   false  // flip if the head turns the wrong way
#define TILT_INVERT  false
#define SERVO_SPEED  150.0f // max degrees per second

// ---- Laser safety ----
#define LASER_TIMEOUT_MS 6000 // laser turns itself off after this

#include "secrets.h"          // copy secrets.example.h to secrets.h
