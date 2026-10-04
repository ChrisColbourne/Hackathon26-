// Otter tutor robot - the ESP32 only obeys JSON commands from the laptop.
// Contract: face{state} mouth{level} look{pan,tilt} laser{on,pan?,tilt?} home
// Test without a server: type a JSON command in the serial monitor.
#include <Arduino.h>
#include <ArduinoJson.h>
#include "config.h"
#include "otter.h"
#include "motion.h"
#include "laser.h"
#include "net.h"

static char pending[16] = "";   // action waiting for the head to arrive
static bool laserAfterMove = false;

static void reply(const char* action) {
  char buf[64];
  snprintf(buf, sizeof buf, "{\"status\":\"done\",\"action\":\"%s\"}", action);
  net::send(buf);
}

static void handle(const char* json, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, json, len)) { net::send("{\"status\":\"error\",\"msg\":\"bad json\"}"); return; }
  const char* a = doc["action"] | "";
  if (strcmp(a, "mouth")) Serial.printf("[rx] %.*s\n", (int)len, json);

  if (!strcmp(a, "face")) { otter::setMood(doc["state"] | "idle"); reply("face"); }
  else if (!strcmp(a, "mouth")) { otter::setMouth(doc["level"] | 0.0f); }
  else if (!strcmp(a, "look")) {
    // SAFETY: a plain look never carries the laser along. Without this, a look
    // arriving after a laser command re-targeted it (fired off-target) or swept a lit beam.
    laser::set(false); laserAfterMove = false;
    motion::look(doc["pan"] | 0.0f, doc["tilt"] | 0.0f); strcpy(pending, "look");
  }
  else if (!strcmp(a, "laser")) {
    bool on = doc["on"] | false;
    if (!on) { laser::set(false); laserAfterMove = false; reply("laser"); }
    else if (doc["pan"].is<float>() || doc["tilt"].is<float>()) {
      laser::set(false);  // aim first, then switch on
      motion::look(doc["pan"] | 0.0f, doc["tilt"] | 0.0f);
      laserAfterMove = true; strcpy(pending, "laser");
    } else { laser::set(true); reply("laser"); }
  }
  else if (!strcmp(a, "home")) {
    laser::set(false); laserAfterMove = false; otter::setMood("idle");
    motion::home(); strcpy(pending, "home");
  }
  else net::send("{\"status\":\"error\",\"msg\":\"unknown action\"}");

  if (pending[0] && !motion::moving()) {  // already there
    if (laserAfterMove) { laser::set(true); laserAfterMove = false; }
    reply(pending); pending[0] = 0;
  }
}

static void onLost() { laser::set(false); laserAfterMove = false; otter::setMood("idle"); motion::home(); }

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[otter] booting");
  laser::begin();
  otter::begin();
  motion::begin();
  motion::home();
  net::begin(handle, onLost);
  Serial.println("[otter] ready. Type JSON here to test, e.g. {\"action\":\"face\",\"state\":\"happy\"}");
}

void loop() {
  net::loop();
  if (motion::update() && pending[0]) {
    if (laserAfterMove) { laser::set(true); laserAfterMove = false; }
    reply(pending); pending[0] = 0;
  }
  laser::update();
  otter::update();

  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (line.length()) handle(line.c_str(), line.length()); line = ""; }
    else line += c;
  }
}
