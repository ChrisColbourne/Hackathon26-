// Otter face for a 240x320 ILI9341 mounted vertically (portrait), in the team's design: golden head,
// yellow muzzle, coral nose, blush dots. The head sits in the lower part of the screen at 90% of the old
// landscape size (18 px clear each side); the mood extras (thought bubble, "?", stars, sound bars) go above it.
// Whole frame goes into an 8-bit sprite (~77 KB) and is pushed at ~25 fps, so it never flickers.
#include <Arduino.h>
#include <TFT_eSPI.h>
#include "config.h"
#include "otter.h"

namespace otter {
enum Mood { IDLE, LISTENING, THINKING, TALKING, HAPPY, CONFUSED };
static const int W = 240, H = 320;     // portrait
static const int CX = 120, CY = 180;   // middle of the head
static TFT_eSPI tft;
static TFT_eSprite spr(&tft);
static Mood mood = IDLE;
static float mouthTarget = 0, mouthLevel = 0;
static uint32_t lastMouthMsg = 0, lastFrame = 0, nextBlink = 2000, blinkStart = 0;
static bool blinking = false, useSprite = true;
static uint16_t BG, BG2, OUT, FUR, MUZ, EYE, NOSE, WHITE, MOUTH, TONGUE, BLUSH, STAR, DOT;

void begin() {
  tft.init();
  tft.setRotation(SCREEN_ROTATION);  // portrait 240x320, see config.h
  BG = tft.color565(52, 53, 94);    BG2 = tft.color565(69, 71, 120);  OUT = tft.color565(43, 34, 51);
  FUR = tft.color565(247, 174, 0);  MUZ = tft.color565(255, 212, 94); EYE = tft.color565(59, 30, 30);
  NOSE = tft.color565(224, 104, 96); WHITE = TFT_WHITE;              MOUTH = tft.color565(122, 42, 42);
  TONGUE = tft.color565(240, 138, 138); BLUSH = tft.color565(232, 96, 48); STAR = tft.color565(255, 211, 77);
  DOT = tft.color565(201, 207, 224);
  spr.setColorDepth(8);
  if (!spr.createSprite(W, H)) { useSprite = false; Serial.println("[otter] no RAM for sprite"); }
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
  g.fillRect(0, 22, W, 10, BG2);
  g.fillRect(0, 288, W, 6, BG2);

  // ears, head, muzzle (each with a dark outline)
  int eu = mood == LISTENING ? -5 : 0;
  g.fillCircle(CX - 88, CY - 34 + b + eu, 14, OUT); g.fillCircle(CX - 88, CY - 34 + b + eu, 10, FUR);
  g.fillCircle(CX + 88, CY - 34 + b + eu, 14, OUT); g.fillCircle(CX + 88, CY - 34 + b + eu, 10, FUR);
  g.fillEllipse(CX, CY + b, 97, 90, OUT);      g.fillEllipse(CX, CY + b, 94, 86, FUR);
  g.fillEllipse(CX, CY + 18 + b, 67, 43, OUT); g.fillEllipse(CX, CY + 18 + b, 64, 40, MUZ);

  // blush dots
  const int bx[3] = {-67, -56, -58}, by[3] = {11, 4, 16};
  for (int k = 0; k < 3; k++) { g.fillCircle(CX + bx[k], CY + by[k] + b, 4, BLUSH); g.fillCircle(CX - bx[k], CY + by[k] + b, 4, BLUSH); }

  // eyes
  int lx = 0, ly = 0;
  if (mood == THINKING) { lx = 5; ly = -5; } else if (mood == IDLE) lx = (int)(sinf(t * 0.5f) * 3);
  int er = mood == LISTENING ? 13 : 11;
  const int ex[2] = {CX - 34, CX + 34};
  for (int i = 0; i < 2; i++) {
    if (mood == HAPPY) {
      g.fillEllipse(ex[i], CY - 18 + b, 11, 9, EYE);
      g.fillEllipse(ex[i], CY - 13 + b, 12, 8, FUR);
    } else {
      float o = open;
      if (mood == CONFUSED && i == 0) o = min(o, 0.45f);
      g.fillEllipse(ex[i] + lx, CY - 20 + ly + b, er, max(1, (int)((er + 2) * o)), EYE);
      if (o > 0.4f) g.fillCircle(ex[i] + lx - 4, CY - 25 + ly + b, 3, WHITE);
    }
  }
  if (mood == CONFUSED) {
    g.drawWideLine(CX - 47, CY - 36 + b, CX - 23, CY - 33 + b, 4, OUT, FUR);
    g.drawWideLine(CX + 23, CY - 40 + b, CX + 47, CY - 45 + b, 4, OUT, FUR);
  }
  if (mood == THINKING) {
    g.drawWideLine(CX - 45, CY - 37 + b, CX - 23, CY - 40 + b, 4, OUT, FUR);
    g.drawWideLine(CX + 23, CY - 40 + b, CX + 45, CY - 37 + b, 4, OUT, FUR);
  }

  // nose
  g.fillTriangle(CX - 13, CY + b, CX + 13, CY + b, CX, CY + 12 + b, NOSE);
  g.fillEllipse(CX, CY + 1 + b, 13, 4, NOSE);
  g.drawWideLine(CX, CY + 12 + b, CX, CY + 17 + b, 2.5f, OUT, MUZ);

  // mouth
  if (mood == TALKING) {
    int h = 4 + (int)(mouthLevel * 13);
    g.fillEllipse(CX, CY + 20 + b + h / 2, 10 + (int)(mouthLevel * 3), h, MOUTH);
    g.fillEllipse(CX, CY + 22 + b + (int)(h * 0.9f), 6, max(1, (int)(h * 0.35f)), TONGUE);
  } else if (mood == CONFUSED || mood == THINKING) {
    g.drawWideLine(CX - 9, CY + 23 + b, CX + 9, CY + 23 + b, 3, OUT, MUZ);
  } else {  // small open smile: lower half of an ellipse with a tongue
    int h = mood == HAPPY ? 9 : 6;
    g.fillEllipse(CX, CY + 19 + b, 11, h, MOUTH);
    g.fillEllipse(CX, CY + 19 + b + (int)(h * 0.75f), 6, max(1, (int)(h * 0.45f)), TONGUE);
    g.fillRect(CX - 13, CY + 19 + b - h - 1, 26, h + 1, MUZ);  // cut the top half off
    g.drawWideLine(CX, CY + 12 + b, CX, CY + 19 + b, 2.5f, OUT, MUZ);
  }

  // extras, in the space above the head (and the corners for the stars)
  if (mood == HAPPY) {
    const int sx[4] = {30, 210, 24, 216}, sy[4] = {64, 60, 270, 266};
    for (int k = 0; k < 4; k++) g.fillCircle(sx[k], sy[k] + (int)(sinf(t * 4 + k) * 4), 4 + (int)(sinf(t * 6 + k) * 1.5f), STAR);
  }
  if (mood == THINKING) {
    g.fillEllipse(176, 54, 28, 18, WHITE); g.fillCircle(150, 78, 5, WHITE);
    int on = ((int)(t * 3)) % 4;
    for (int k = 0; k < 3; k++) g.fillCircle(164 + k * 12, 54, 4, on > k ? BG : DOT);
  }
  if (mood == CONFUSED) { g.setTextColor(WHITE); g.setTextSize(5); g.drawString("?", 170, 34 + (int)(sinf(t * 3) * 3), 1); }
  if (mood == LISTENING)
    for (int k = 0; k < 3; k++) { int h = 10 + (int)(fabsf(sinf(t * 8 + k)) * 22); g.fillRoundRect(CX - 15 + k * 12, 58 - h / 2, 6, h, 3, WHITE); }
}

void update() {
  uint32_t now = millis();
  if (now - lastFrame < 40) return;
  lastFrame = now;
  if (useSprite) { draw(spr, now / 1000.0f); spr.pushSprite(0, 0); }
}
}
