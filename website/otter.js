// Otter face: a 1:1 port of otter-robot-arduino/otter_robot/otter.cpp to <canvas>.
// Portrait 240x320 screen: golden head, yellow muzzle, coral nose, blush dots, on navy stripes.
// Same coordinates, same colors, same timing (~25 fps, 160 ms blink every 2-5 s).
// TFT_eSPI fillEllipse(x, y, rx, ry) takes radii, like ctx.ellipse().
// (int) casts in the C++ truncate toward zero, so they become Math.trunc() here.

(function () {
  const MOODS = ["idle", "listening", "thinking", "talking", "happy", "confused"];
  const W = 240, H = 320;   // portrait
  const CX = 120, CY = 180; // middle of the head

  // tft.color565(r, g, b) values from otter.cpp begin()
  const C = {
    BG: "rgb(52,53,94)", BG2: "rgb(69,71,120)", OUT: "rgb(43,34,51)",
    FUR: "rgb(247,174,0)", MUZ: "rgb(255,212,94)", EYE: "rgb(59,30,30)",
    NOSE: "rgb(224,104,96)", WHITE: "#ffffff", MOUTH: "rgb(122,42,42)",
    TONGUE: "rgb(240,138,138)", BLUSH: "rgb(232,96,48)", STAR: "rgb(255,211,77)",
    DOT: "rgb(201,207,224)",
  };

  const trunc = Math.trunc;
  const clamp01 = (v) => Math.min(1, Math.max(0, v));
  const random = (n) => Math.floor(Math.random() * n); // Arduino random(n): 0..n-1

  class Otter {
    // options.still: draw static frames only (prefers-reduced-motion)
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.still = !!options.still;
      const scale = 2; // draw at 2x for sharp edges, keep 240x320 coordinates
      canvas.width = W * scale;
      canvas.height = H * scale;
      this.g = canvas.getContext("2d");
      this.g.scale(scale, scale);

      this.mood = "idle";
      this.mouthTarget = 0;
      this.mouthLevel = 0;
      this.lastMouthMsg = 0;
      this.lastFrame = 0;
      this.nextBlink = this.millis() + 2000;
      this.blinkStart = 0;
      this.blinking = false;
      this.talkTimer = null;
      this.talkDone = null;
      this.visible = true;

      // Only animate while the canvas is on screen.
      if ("IntersectionObserver" in window) {
        new IntersectionObserver((entries) => {
          this.visible = entries[0].isIntersecting;
        }).observe(canvas);
      }
      this.draw(0);
      if (!this.still) requestAnimationFrame(() => this.update());
    }

    millis() { return performance.now(); }

    setMood(state) {
      this.mood = MOODS.includes(state) ? state : "idle";
      if (this.still) this.draw(0);
    }

    setMouth(level) {
      this.mouthTarget = clamp01(level);
      this.lastMouthMsg = this.millis();
      if (this.still) this.draw(0);
    }

    // Fake the mouth envelope the brain streams while ElevenLabs audio plays (~15 msgs/s),
    // then switch to `after`. Resolves when the talking ends (or is cut short).
    talk(ms, after = "idle") {
      this.stopTalk();
      this.setMood("talking");
      if (this.still) {
        this.mouthLevel = 0.5;
        this.draw(0);
      }
      return new Promise((resolve) => {
        const start = this.millis();
        this.talkDone = resolve;
        this.talkTimer = setInterval(() => {
          const t = (this.millis() - start) / 1000;
          if (t * 1000 >= ms) {
            this.stopTalk();
            this.setMood(after);
            return;
          }
          // syllable-ish envelope: a fast wobble times a slower phrase shape, plus jitter
          const syllable = Math.abs(Math.sin(t * 11));
          const phrase = 0.55 + 0.45 * Math.sin(t * 2.3 + 1);
          const level = 0.15 + 0.85 * syllable * phrase * (0.7 + Math.random() * 0.3);
          if (!this.still) this.setMouth(level);
        }, 66);
      });
    }

    stopTalk() {
      if (this.talkTimer) clearInterval(this.talkTimer);
      this.talkTimer = null;
      this.mouthTarget = 0;
      if (this.talkDone) { const done = this.talkDone; this.talkDone = null; done(); }
    }

    update() {
      requestAnimationFrame(() => this.update());
      const now = this.millis();
      if (now - this.lastFrame < 40) return; // ~25 fps
      this.lastFrame = now;
      if (!this.visible || document.hidden) return;
      this.draw(now / 1000);
    }

    // ---- TFT_eSPI drawing primitives ----
    fillRect(x, y, w, h, c) { const g = this.g; g.fillStyle = c; g.fillRect(x, y, w, h); }
    fillCircle(x, y, r, c) { const g = this.g; g.fillStyle = c; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
    fillEllipse(x, y, rx, ry, c) {
      const g = this.g; g.fillStyle = c; g.beginPath();
      g.ellipse(x, y, Math.max(rx, 0.5), Math.max(ry, 0.5), 0, 0, Math.PI * 2); g.fill();
    }
    fillTriangle(x0, y0, x1, y1, x2, y2, c) {
      const g = this.g; g.fillStyle = c; g.beginPath();
      g.moveTo(x0, y0); g.lineTo(x1, y1); g.lineTo(x2, y2); g.closePath(); g.fill();
    }
    fillRoundRect(x, y, w, h, r, c) {
      const g = this.g; g.fillStyle = c; g.beginPath();
      if (g.roundRect) g.roundRect(x, y, w, h, r); else g.rect(x, y, w, h);
      g.fill();
    }
    drawWideLine(x0, y0, x1, y1, wd, c) {
      const g = this.g; g.strokeStyle = c; g.lineWidth = wd; g.lineCap = "round";
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
    }

    // ---- the frame, line for line from otter.cpp draw() ----
    draw(t) {
      const mood = this.mood;
      const now = this.millis();

      let open = 1;
      if (!this.still) {
        if (!this.blinking && now > this.nextBlink) { this.blinking = true; this.blinkStart = now; }
        if (this.blinking) {
          const p = (now - this.blinkStart) / 160;
          if (p >= 1) { this.blinking = false; this.nextBlink = now + 2000 + random(3000); } else open = Math.abs(1 - p * 2);
        }
      }
      if (mood === "listening") open = Math.max(open, 0.6);
      if (!this.still) {
        if (mood !== "talking" || now - this.lastMouthMsg > 400) this.mouthTarget = 0;
        this.mouthLevel += (this.mouthTarget - this.mouthLevel) * 0.5;
      } else if (mood !== "talking") {
        this.mouthLevel = 0;
      }
      const mouthLevel = this.mouthLevel;

      const b = mood === "talking" ? trunc(Math.sin(t * 9) * 1.5) : trunc(Math.sin(t * 1.6) * 2);
      this.fillRect(0, 0, W, H, C.BG);
      this.fillRect(0, 22, W, 10, C.BG2);
      this.fillRect(0, 288, W, 6, C.BG2);

      // ears, head, muzzle (each with a dark outline)
      const eu = mood === "listening" ? -5 : 0;
      this.fillCircle(CX - 88, CY - 34 + b + eu, 14, C.OUT); this.fillCircle(CX - 88, CY - 34 + b + eu, 10, C.FUR);
      this.fillCircle(CX + 88, CY - 34 + b + eu, 14, C.OUT); this.fillCircle(CX + 88, CY - 34 + b + eu, 10, C.FUR);
      this.fillEllipse(CX, CY + b, 97, 90, C.OUT);      this.fillEllipse(CX, CY + b, 94, 86, C.FUR);
      this.fillEllipse(CX, CY + 18 + b, 67, 43, C.OUT); this.fillEllipse(CX, CY + 18 + b, 64, 40, C.MUZ);

      // blush dots
      const bx = [-67, -56, -58], by = [11, 4, 16];
      for (let k = 0; k < 3; k++) {
        this.fillCircle(CX + bx[k], CY + by[k] + b, 4, C.BLUSH);
        this.fillCircle(CX - bx[k], CY + by[k] + b, 4, C.BLUSH);
      }

      // eyes
      let lx = 0, ly = 0;
      if (mood === "thinking") { lx = 5; ly = -5; } else if (mood === "idle") lx = trunc(Math.sin(t * 0.5) * 3);
      const er = mood === "listening" ? 13 : 11;
      const ex = [CX - 34, CX + 34];
      for (let i = 0; i < 2; i++) {
        if (mood === "happy") {
          this.fillEllipse(ex[i], CY - 18 + b, 11, 9, C.EYE);
          this.fillEllipse(ex[i], CY - 13 + b, 12, 8, C.FUR);
        } else {
          let o = open;
          if (mood === "confused" && i === 0) o = Math.min(o, 0.45);
          this.fillEllipse(ex[i] + lx, CY - 20 + ly + b, er, Math.max(1, trunc((er + 2) * o)), C.EYE);
          if (o > 0.4) this.fillCircle(ex[i] + lx - 4, CY - 25 + ly + b, 3, C.WHITE);
        }
      }
      if (mood === "confused") {
        this.drawWideLine(CX - 47, CY - 36 + b, CX - 23, CY - 33 + b, 4, C.OUT);
        this.drawWideLine(CX + 23, CY - 40 + b, CX + 47, CY - 45 + b, 4, C.OUT);
      }
      if (mood === "thinking") {
        this.drawWideLine(CX - 45, CY - 37 + b, CX - 23, CY - 40 + b, 4, C.OUT);
        this.drawWideLine(CX + 23, CY - 40 + b, CX + 45, CY - 37 + b, 4, C.OUT);
      }

      // nose
      this.fillTriangle(CX - 13, CY + b, CX + 13, CY + b, CX, CY + 12 + b, C.NOSE);
      this.fillEllipse(CX, CY + 1 + b, 13, 4, C.NOSE);
      this.drawWideLine(CX, CY + 12 + b, CX, CY + 17 + b, 2.5, C.OUT);

      // mouth
      if (mood === "talking") {
        const h = 4 + trunc(mouthLevel * 13);
        this.fillEllipse(CX, CY + 20 + b + trunc(h / 2), 10 + trunc(mouthLevel * 3), h, C.MOUTH);
        this.fillEllipse(CX, CY + 22 + b + trunc(h * 0.9), 6, Math.max(1, trunc(h * 0.35)), C.TONGUE);
      } else if (mood === "confused" || mood === "thinking") {
        this.drawWideLine(CX - 9, CY + 23 + b, CX + 9, CY + 23 + b, 3, C.OUT);
      } else { // small open smile: lower half of an ellipse with a tongue
        const h = mood === "happy" ? 9 : 6;
        this.fillEllipse(CX, CY + 19 + b, 11, h, C.MOUTH);
        this.fillEllipse(CX, CY + 19 + b + trunc(h * 0.75), 6, Math.max(1, trunc(h * 0.45)), C.TONGUE);
        this.fillRect(CX - 13, CY + 19 + b - h - 1, 26, h + 1, C.MUZ); // cut the top half off
        this.drawWideLine(CX, CY + 12 + b, CX, CY + 19 + b, 2.5, C.OUT);
      }

      // extras, in the space above the head (and the corners for the stars)
      if (mood === "happy") {
        const sx = [30, 210, 24, 216], sy = [64, 60, 270, 266];
        for (let k = 0; k < 4; k++)
          this.fillCircle(sx[k], sy[k] + trunc(Math.sin(t * 4 + k) * 4), 4 + trunc(Math.sin(t * 6 + k) * 1.5), C.STAR);
      }
      if (mood === "thinking") {
        this.fillEllipse(176, 54, 28, 18, C.WHITE); this.fillCircle(150, 78, 5, C.WHITE);
        const on = this.still ? 3 : trunc(t * 3) % 4;
        for (let k = 0; k < 3; k++) this.fillCircle(164 + k * 12, 54, 4, on > k ? C.BG : C.DOT);
      }
      if (mood === "confused") {
        // setTextSize(5) on the GLCD font: 6x8 cells scaled x5, top-left datum
        const g = this.g;
        g.fillStyle = C.WHITE;
        g.font = "bold 40px monospace";
        g.textBaseline = "top";
        g.fillText("?", 170, 34 + trunc(Math.sin(t * 3) * 3));
      }
      if (mood === "listening")
        for (let k = 0; k < 3; k++) {
          const h = 10 + trunc(Math.abs(Math.sin(t * 8 + k)) * 22);
          this.fillRoundRect(CX - 15 + k * 12, 58 - trunc(h / 2), 6, h, 3, C.WHITE);
        }
    }
  }

  window.Otter = Otter;
})();
