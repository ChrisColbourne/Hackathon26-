#include <Arduino.h>
#include <ESP32Servo.h>
#include "config.h"
#include "motion.h"

namespace motion {
static Servo sPan, sTilt;
static float curP = 0, curT = 0, tgtP = 0, tgtT = 0;
static bool wasMoving = false;
static uint32_t last = 0;

static void write() {
  sPan.write(PAN_CENTER + (PAN_INVERT ? -curP : curP));
  sTilt.write(TILT_CENTER + (TILT_INVERT ? -curT : curT));
}

void begin() {
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  sPan.setPeriodHertz(50);
  sTilt.setPeriodHertz(50);
  sPan.attach(PIN_PAN, 500, 2400);
  sTilt.attach(PIN_TILT, 500, 2400);
  write();
  last = millis();
}

void look(float pan, float tilt) {
  tgtP = constrain(pan, -PAN_LIMIT, PAN_LIMIT);
  tgtT = constrain(tilt, TILT_MIN, TILT_MAX);
  wasMoving = true;
}

void home() { look(0, 0); }

bool moving() { return fabsf(tgtP - curP) > 0.3f || fabsf(tgtT - curT) > 0.3f; }

static float stepTo(float cur, float tgt, float maxStep) {
  float d = tgt - cur;
  if (fabsf(d) < 0.3f) return tgt;
  float s = d * 0.18f;                       // ease out
  if (fabsf(s) < 0.4f) s = d > 0 ? 0.4f : -0.4f;
  return cur + constrain(s, -maxStep, maxStep);
}

bool update() {
  uint32_t now = millis();
  if (now - last < 20) return false;         // 50 Hz
  float dt = (now - last) / 1000.0f;
  last = now;
  float maxStep = SERVO_SPEED * dt;
  curP = stepTo(curP, tgtP, maxStep);
  curT = stepTo(curT, tgtT, maxStep);
  write();
  if (wasMoving && !moving()) { wasMoving = false; return true; }
  return false;
}
}
