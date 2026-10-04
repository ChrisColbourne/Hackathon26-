// Otter face for a 320x240 ILI9341 in the team's design: golden head, yellow muzzle, coral nose, blush dots.
// Whole frame goes into an 8-bit sprite (~77 KB) and is pushed at ~25 fps, so it never flickers.
#include <Arduino.h>
#include <TFT_eSPI.h>
#include "otter.h"

namespace otter {
enum Mood { IDLE, LISTENING, THINKING, TALKING, HAPPY, CONFUSED };
static TFT_eSPI tft;
static TFT_eSprite spr(&tft);
static Mood mood = IDLE;
static float mouthTarget = 0, mouthLevel = 0;
static uint32_t lastMouthMsg = 0, lastFrame = 0, nextBlink = 2000, blinkStart = 0;
static bool blinking = false, useSprite = true;
static uint16_t BG, BG2, OUT, FUR, MUZ, EYE, NOSE, WHITE, MOUTH, TONGUE, BLUSH, STAR, DOT;

void begin() {
  tft.init();
  tft.setRotation(1);  // landscape 320x240; try 3 if upside down
  BG = tft.color565(52, 53, 94);    BG2 = tft.color565(69, 71, 120);  OUT = tft.color565(43, 34, 51);
  FUR = tft.color565(247, 174, 0);  MUZ = tft.color565(255, 212, 94); EYE = tft.color565(59, 30, 30);
  NOSE = tft.color565(224, 104, 96); WHITE = TFT_WHITE;              MOUTH = tft.color565(122, 42, 42);
  TONGUE = tft.color565(240, 138, 138); BLUSH = tft.color565(232, 96, 48); STAR = tft.color565(255, 211, 77);
  DOT = tft.color565(201, 207, 224);
  spr.setColorDepth(8);
  if (!spr.createSprite(320, 240)) { useSprite = false; Serial.println("[otter] no RAM for sprite"); }
  tft.fillScreen(BG);
}

void setMood(const char* s) {
  if (!strcmp(s, "listening")) mood = LISTENING;
  else if (!strcmp(s, "thinking")) mood = THINKING;
  else if (!strcmp(s, "talking")) mood = TALKING;
  else if (!strcmp(s, "happy")) mood = HAPPY;
  else if (!strcmp(s, "confused")) mood = CONFUSED;
  else mood = IDLE;
}

void setMouth(float level) { mouthTarget = constrain(level, 0.0f, 1.0f); lastMouthMsg = millis(); }

template <typename G> static void draw(G& g, float t) {
  float open = 1;
  uint32_t now = millis();
  if (!blinking && now > nextBlink) { blinking = true; blinkStart = now; }
  if (blinking) {
    float p = (now - blinkStart) / 160.0f;
    if (p >= 1) { blinking = false; nextBlink = now + 2000 + random(3000); } else open = fabsf(1 - p * 2);
  }
  if (mood == LISTENING) open = max(open, 0.6f);
  if (mood != TALKING || now - lastMouthMsg > 400) mouthTarget = 0;
  mouthLevel += (mouthTarget - mouthLevel) * 0.5f;

  int b = mood == TALKING ? (int)(sinf(t * 9) * 1.5f) : (int)(sinf(t * 1.6f) * 2);
  g.fillSprite(BG);
  g.fillRect(0, 22, 320, 10, BG2);
  g.fillRect(0, 206, 320, 6, BG2);

  // ears, head, muzzle (each with a dark outline)
  int eu = mood == LISTENING ? -6 : 0;
  g.fillCircle(62, 92 + b + eu, 15, OUT);  g.fillCircle(62, 92 + b + eu, 11, FUR);
  g.fillCircle(258, 92 + b + eu, 15, OUT); g.fillCircle(258, 92 + b + eu, 11, FUR);
  g.fillEllipse(160, 130 + b, 108, 100, OUT); g.fillEllipse(160, 130 + b, 104, 96, FUR);
  g.fillEllipse(160, 150 + b, 74, 48, OUT);   g.fillEllipse(160, 150 + b, 71, 45, MUZ);

  // blush dots
  const int bx[3] = {86, 98, 96}, by[3] = {142, 134, 148};
  for (int k = 0; k < 3; k++) { g.fillCircle(bx[k], by[k] + b, 4, BLUSH); g.fillCircle(320 - bx[k], by[k] + b, 4, BLUSH); }

  // eyes
  int lx = 0, ly = 0;
  if (mood == THINKING) { lx = 5; ly = -6; } else if (mood == IDLE) lx = (int)(sinf(t * 0.5f) * 3);
  int er = mood == LISTENING ? 14 : 12;
  const int ex[2] = {122, 198};
  for (int i = 0; i < 2; i++) {
    if (mood == HAPPY) {
      g.fillEllipse(ex[i], 110 + b, 12, 10, EYE);
      g.fillEllipse(ex[i], 116 + b, 13, 9, FUR);
    } else {
      float o = open;
      if (mood == CONFUSED && i == 0) o = min(o, 0.45f);
      g.fillEllipse(ex[i] + lx, 108 + ly + b, er, max(1, (int)((er + 2) * o)), EYE);
      if (o > 0.4f) g.fillCircle(ex[i] + lx - 4, 103 + ly + b, 3, WHITE);
    }
  }
  if (mood == CONFUSED) { g.drawWideLine(108, 90 + b, 134, 93 + b, 4, OUT, FUR); g.drawWideLine(186, 86 + b, 212, 80 + b, 4, OUT, FUR); }
  if (mood == THINKING) { g.drawWideLine(110, 89 + b, 134, 86 + b, 4, OUT, FUR); g.drawWideLine(186, 86 + b, 210, 89 + b, 4, OUT, FUR); }

  // nose
  g.fillTriangle(146, 130 + b, 174, 130 + b, 160, 143 + b, NOSE);
  g.fillEllipse(160, 131 + b, 14, 4, NOSE);
  g.drawWideLine(160, 143 + b, 160, 149 + b, 2.5f, OUT, MUZ);

  // mouth
  if (mood == TALKING) {
    int h = 4 + (int)(mouthLevel * 14);
    g.fillEllipse(160, 152 + b + h / 2, 11 + (int)(mouthLevel * 3), h, MOUTH);
    g.fillEllipse(160, 154 + b + (int)(h * 0.9f), 7, max(1, (int)(h * 0.35f)), TONGUE);
  } else if (mood == CONFUSED || mood == THINKING) {
    g.drawWideLine(150, 156 + b, 170, 156 + b, 3, OUT, MUZ);
  } else {  // small open smile: lower half of an ellipse with a tongue
    int h = mood == HAPPY ? 10 : 7;
    g.fillEllipse(160, 151 + b, 12, h, MOUTH);
    g.fillEllipse(160, 151 + b + (int)(h * 0.75f), 7, max(1, (int)(h * 0.45f)), TONGUE);
    g.fillRect(146, 151 + b - h - 1, 28, h + 1, MUZ);  // cut the top half off
    g.drawWideLine(160, 143 + b, 160, 151 + b, 2.5f, OUT, MUZ);
  }

  // extras
  if (mood == HAPPY) {
    const int sx[4] = {40, 280, 44, 276}, sy[4] = {60, 56, 190, 186};
    for (int k = 0; k < 4; k++) g.fillCircle(sx[k], sy[k] + (int)(sinf(t * 4 + k) * 4), 4 + (int)(sinf(t * 6 + k) * 1.5f), STAR);
  }
  if (mood == THINKING) {
    g.fillEllipse(272, 50, 28, 18, WHITE); g.fillCircle(246, 74, 5, WHITE);
    int on = ((int)(t * 3)) % 4;
    for (int k = 0; k < 3; k++) g.fillCircle(260 + k * 12, 50, 4, on > k ? BG : DOT);
  }
  if (mood == CONFUSED) { g.setTextColor(WHITE); g.setTextSize(5); g.drawString("?", 266, 34 + (int)(sinf(t * 3) * 3), 1); }
  if (mood == LISTENING)
    for (int k = 0; k < 3; k++) { int h = 10 + (int)(fabsf(sinf(t * 8 + k)) * 22); g.fillRoundRect(20 + k * 10, 120 - h / 2, 6, h, 3, WHITE); }
}

void update() {
  uint32_t now = millis();
  if (now - lastFrame < 40) return;
  lastFrame = now;
  if (useSprite) { draw(spr, now / 1000.0f); spr.pushSprite(0, 0); }
}
}
