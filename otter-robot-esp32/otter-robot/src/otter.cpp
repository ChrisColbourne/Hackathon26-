// Otter face for a 320x240 ILI9341. Our own design, drawn from simple shapes.
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
static uint16_t BG, WATER, FUR, FUR2, FURL, EAR, CREAM, DARK, NOSE, WHITE, PINK, MOUTH, TONGUE, STAR, INK;

void begin() {
  tft.init();
  tft.setRotation(1);  // landscape 320x240; try 3 if upside down
  BG = tft.color565(207, 232, 245);  WATER = tft.color565(185, 220, 239);
  FUR = tft.color565(138, 90, 59);   FUR2 = tft.color565(111, 69, 41);  FURL = tft.color565(148, 100, 70);
  EAR = tft.color565(201, 143, 107); CREAM = tft.color565(241, 220, 192);
  DARK = tft.color565(43, 27, 18);   NOSE = tft.color565(58, 36, 24);   WHITE = TFT_WHITE;
  PINK = tft.color565(240, 150, 165); MOUTH = tft.color565(110, 42, 42); TONGUE = tft.color565(233, 138, 138);
  STAR = tft.color565(255, 211, 77); INK = tft.color565(58, 74, 90);
  spr.setColorDepth(8);
  if (!spr.createSprite(320, 240)) { useSprite = false; Serial.println("[otter] no RAM for sprite, drawing direct"); }
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
  // blink
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

  int bob = mood == TALKING ? (int)(sinf(t * 9) * 1.5f) : (int)(sinf(t * 1.6f) * 2);
  g.fillSprite(BG);
  g.fillRect(0, 214, 320, 26, WATER);

  int eUp = mood == LISTENING ? -9 : 0, eR = mood == LISTENING ? 25 : 22;
  g.fillCircle(100, 64 + eUp + bob, eR, FUR2);  g.fillCircle(100, 64 + eUp + bob, eR / 2, EAR);
  g.fillCircle(220, 64 + eUp + bob, eR, FUR2);  g.fillCircle(220, 64 + eUp + bob, eR / 2, EAR);
  g.fillEllipse(160, 132 + bob, 106, 88, FUR);
  g.fillEllipse(160, 96 + bob, 70, 30, FURL);
  if (mood == HAPPY) { g.fillEllipse(98, 162 + bob, 18, 11, PINK); g.fillEllipse(222, 162 + bob, 18, 11, PINK); }
  g.fillEllipse(160, 162 + bob, 60, 42, CREAM);

  // eyes
  int lx = 0, ly = 0;
  if (mood == THINKING) { lx = 6; ly = -6; } else if (mood == IDLE) lx = (int)(sinf(t * 0.5f) * 3);
  int er = mood == LISTENING ? 15 : 13;
  const int ex[2] = {118, 202};
  for (int i = 0; i < 2; i++) {
    if (mood == HAPPY) {  // ^ ^ eyes: dark ellipse with the bottom covered by fur
      g.fillEllipse(ex[i], 122 + bob, 13, 11, DARK);
      g.fillEllipse(ex[i], 128 + bob, 14, 10, FUR);
    } else {
      float o = open;
      if (mood == CONFUSED && i == 0) o = min(o, 0.45f);
      int ry = max(1, (int)(er * o));
      g.fillEllipse(ex[i] + lx, 118 + ly + bob, er, ry, DARK);
      if (o > 0.4f) { g.fillCircle(ex[i] + lx - 4, 114 + ly + bob, 4, WHITE); g.fillCircle(ex[i] + lx + 4, 122 + ly + bob, 2, WHITE); }
    }
  }
  if (mood == CONFUSED) {
    g.drawWideLine(104, 104 + bob, 130, 106 + bob, 4, FUR2, FUR);
    g.drawWideLine(188, 96 + bob, 218, 90 + bob, 4, FUR2, FUR);
  }
  if (mood == THINKING) {
    g.drawWideLine(106, 100 + bob, 132, 97 + bob, 4, FUR2, FUR);
    g.drawWideLine(190, 97 + bob, 216, 100 + bob, 4, FUR2, FUR);
  }

  // nose
  g.fillEllipse(160, 149 + bob, 14, 9, NOSE);
  g.fillEllipse(155, 146 + bob, 4, 2, FURL);

  // mouth
  g.drawWideLine(160, 157 + bob, 160, 165 + bob, 2.5f, NOSE, CREAM);
  if (mood == TALKING) {
    int h = 3 + (int)(mouthLevel * 14);
    g.fillEllipse(160, 168 + bob + h / 2, 12 + (int)(mouthLevel * 3), h, MOUTH);
    g.fillEllipse(160, 170 + bob + (int)(h * 0.9f), 8, max(1, (int)(h * 0.35f)), TONGUE);
  } else {
    int s = mood == HAPPY ? 9 : mood == CONFUSED ? 2 : 5;  // smile = dark ellipse minus a cream one
    g.fillEllipse(160, 166 + bob, 17, s + 2, NOSE);
    g.fillEllipse(160, 163 + bob, 18, s + 1, CREAM);
  }

  // whiskers
  float tw = mood == IDLE ? sinf(t * 3) * 3 : 0;
  for (int s = -1; s <= 1; s += 2)
    for (int k = -1; k <= 1; k++) {
      int x0 = 160 + s * 36, y0 = 160 + k * 6 + bob;
      g.drawLine(x0, y0, x0 + s * 58, y0 + k * 10 + (int)(tw * (k + 2)), WHITE);
    }

  // extras
  if (mood == HAPPY)
    for (int k = 0; k < 4; k++) {
      const int sx[4] = {48, 272, 60, 262}, sy[4] = {70, 64, 188, 182};
      int r = 5 + (int)(sinf(t * 6 + k) * 2);
      g.fillCircle(sx[k], sy[k] + (int)(sinf(t * 4 + k) * 4), r, STAR);
    }
  if (mood == THINKING) {
    g.fillEllipse(268, 52, 30, 20, WHITE); g.fillCircle(240, 78, 6, WHITE); g.fillCircle(230, 90, 3, WHITE);
    int on = ((int)(t * 3)) % 4;
    for (int k = 0; k < 3; k++) g.fillCircle(256 + k * 12, 52, 4, on > k ? INK : WATER);
  }
  if (mood == CONFUSED) {
    g.setTextColor(INK); g.setTextSize(5);
    g.drawString("?", 262, 36 + (int)(sinf(t * 3) * 3), 1);
  }
  if (mood == LISTENING)
    for (int k = 0; k < 3; k++) {
      int h = 10 + (int)(fabsf(sinf(t * 8 + k)) * 22);
      g.fillRoundRect(22 + k * 10, 120 - h / 2, 6, h, 3, INK);
    }
}

void update() {
  uint32_t now = millis();
  if (now - lastFrame < 40) return;  // ~25 fps
  lastFrame = now;
  float t = now / 1000.0f;
  if (useSprite) { draw(spr, t); spr.pushSprite(0, 0); }
}
}
