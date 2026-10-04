# Otter Tutor: project website (StormHacks 2026), local only

## 0. How to work with me (read first)
- I'm Sebastian (SFU electronics engineering). **Talk to me in Spanish.** Code, comments, identifiers **and every word on the website are in ENGLISH**. Zero Spanish on the page.
- This folder is **local only**. A teammate will publish it later.
  - **Do NOT** `git push`, create remote repos, or deploy (no Vercel/Netlify/GitHub Pages).
  - **Do NOT** create or modify files outside `website/`, except unzipping `../Hackathon26--main.zip` into `./reference/` once. `reference/` is **READ-ONLY**.
- Work in phases (section 9). At the end of each phase, tell me what changed and how to preview it, then **stop** until I say "ok".
- **Current status:** Phase 1 was built with an old design that looked like a copy of the StormHacks site. **Redo Phase 1 from scratch with this file**, then continue.

## 1. The job of the page
Judges give it **about 60 seconds of scrolling**. In that time they must understand, feel, and remember one thing:

> **Otter Tutor sees your mistake and refuses to give you the answer.** A desk robot watches you solve calculus on a real whiteboard, aims a laser at the exact line where you slipped, tells you *what kind* of slip it is, and makes you find the fix yourself.

## 2. Facts (use these; never invent numbers, quotes, users, or stats)
Source: `reference/.../README.md`, `docs/GAMEPLAN.md`, `brain/*.py`, `otter-robot-esp32/`.
- **Name:** Otter Tutor. Built at **StormHacks 2026** (SFU Burnaby, Oct 3–4) in 24 hours by **Leandro, Sebas, Chris, Allen**. Ask me who did what.
- **Pipeline:** 2K webcam → **OpenCV (C++)** finds and deskews the whiteboard and waits until the ink stops moving → **Gemini** (Flash, with a Pro fallback) transcribes every line to LaTeX, judges each step (`ok | wrong_rule | misapplied | arithmetic | unclear`), and boxes the first wrong line → **SymPy** re-derives the math and vetoes false alarms → **policy**: speaks only at confidence ≥ 0.70, flags each mistake once, 20 s cooldown, word filter → the **ESP32** gets WebSocket JSON (`face`, `mouth`, `look`, `laser`, `home`), the laser aims through 4 calibrated corners, and the **ElevenLabs** voice speaks (push-to-talk speech-to-text for the student).
- **Rule #1 (it's the product):** it names the **line** and the **kind** of slip, **never** the correct rule, and never writes corrected math. There is **no hint ladder**.
- **Real lines it says** (from `policy.py`; use them verbatim):
  - "Hmm, take another look at which rule fits line 2."
  - "Check how you applied that rule on line 2."
  - "Something in the arithmetic on line 2 doesn't add up."
  - Praise: "Nice work, that all checks out."
- **Official demo problem:** `d/dx [x² sin x]`, solved on line 2 with the quotient rule (wrong).
- **Robot:**
  - ESP32
  - 2.8" ILI9341 display running our otter (6 moods: idle, listening, thinking, talking, happy, confused)
  - 2× SG90 servos (pan/tilt)
  - KY-008 laser in the otter's "hand"
  - 3D-printed body (7 parts) that clips onto the webcam
  - Laser can't tilt above the board; it turns itself off after 6 s.
- **True build stories you may use** (in the "24 hours" section):
  - Gemini's free tier allowed **20 requests per day**, so we added key rotation, model fallbacks, and a cached demo.
  - Our first arm design **hit the body at full swing**. We checked every angle in CAD until there were zero collisions.
  - A false alarm is worse than a miss, so **SymPy can veto Gemini**.
- **Don't claim** the GAMEPLAN stretch items (Tiger Data, Snowflake, Solana, .tech) unless I confirm them.

## 3. Our otter (port it, don't redesign it)
`reference/.../otter-robot-esp32/otter-robot/src/otter.cpp` is our own otter design: 320×240 TFT shapes, 6 moods, blink, bob, a mouth level, and extras. Port it **1:1** to `website/otter.js` as a `<canvas>` class with `setMood()`, `setMouth()` and a `talk(ms, after)` helper that fakes the mouth envelope. Same coordinates, colors and timing. TFT `fillEllipse(x,y,rx,ry)` takes radii.

## 4. Design v3: mostly the CROX template, plus a little StormHacks warmth
Reference A, the main one: **CROX, a Framer template for engineering & robotics studios** (dribbble.com/shots/27779449, live at crox.framer.website). Take its **system**, not its pixels:
- the whole page is built from **tiles joined by a 4 px seam**, so it reads like a **spec sheet**
- a **full-width nameplate** headline
- a **"system status" table** with real numbers before any marketing copy
- a **dark panel** holding a technical visual
- a **cross-hatched tile** (section-view hatching)
- every claim is **measurable**
- a **footer with a direct ask** and the wordmark across the full width

Reference B, a small dose only: StormHacks' **warmth**. The friendly mascot energy becomes **our otter's face**, and one sunny **highlighter yellow**. No colour bands, no dot grids, no `{i++;}`, no smoke shapes, no chunky serif.

Don't copy CROX's layout, wording, or wordmark 1:1. Remix it with our own content so it isn't a template clone.

**Palette** (CSS variables; you may tune the shades if contrast needs it):
| Token | Hex | Use |
|---|---|---|
| `--seam` | `#E2E3E5` | page background / 4 px seams |
| `--tile` | `#F6F5F1` | tiles ("whiteboard paper") |
| `--ink` | `#15171C` | text, hairlines |
| `--panel` | `#0F1216` | dark tiles |
| `--laser` | `#FF4A1C` | THE accent: buttons, active states, laser dot, the red-pen circle |
| `--highlight` | `#FFD54A` | highlighter strokes on the whiteboard only (the StormHacks nod) |
| `--marker` | `#1E44B8` | handwriting |
| `--fur` / `--cream` | `#8A5A3B` / `#F1DCC0` | otter screen frame only |

**Type:**
- Archivo (variable): **width ~118, weight 800** for the nameplate and headlines, normal width for body.
- JetBrains Mono for spec labels and numbers, in sentence case.
- Kalam 700 for whiteboard handwriting.

**Math in the background:** it should underline what the page is about, quietly.
- A faint **graph-paper grid** (1 px lines, 24 px) inside light tiles, plus axis tick marks along some seams.
- Large **handwritten derivations** in `--marker` at ~6–8% opacity behind 2–3 tiles: e.g. `d/dx[x² sin x]`, `u = x²`, `∫ 2x cos(x²) dx`, a sketched sine curve.
- A recurring **red-pen circle** (`--laser`, hand-drawn SVG stroke) around one wrong term: the page's signature mark, echoing the laser.
- Keep text contrast AA. The math never sits behind body copy at full strength.

**Layout:**
- 12-column grid, 4 px gap.
- Flat tiles: no shadows, radius 0–2 px. 1 px ink hairlines inside tables.
- Tiles stack on mobile (360 px).

**Motion (only meaningful motion):**
- the 360° robot video
- the otter
- the laser dot landing
- the red-pen circle drawing itself once when the demo flags an error
- the nav underline

No fade-in on every section. Respect `prefers-reduced-motion`.

## 5. The 60-second scroll (order = story)
| Time | Section | What the judge gets |
|---|---|---|
| 0–5 s | **Hero** | Nameplate, the one-line promise, and the otter + laser already reacting |
| 5–15 s | **The 360° robot** | Proof it's real hardware: `robot_360` video in a dark tile, with a spec table beside it |
| 15–25 s | **The 1 a.m. problem** | A moment every student knows, and why answer apps make it worse |
| 25–40 s | **Your turn (demo)** | They click a line 2 and the otter catches them |
| 40–50 s | **How it decides** | 4 steps + system status + the rules it lives by |
| 50–60 s | **Built in 24 hours** | Honest build stories, the team, and the closing ask |

## 6. Copy deck (use this text; you may tighten it, but keep the voice)
Patterns borrowed from winning hackathon pages (Devpost/TreeHacks winners, Devpost judge advice), applied in our own words:
- one-line pitch = **verb + object + concrete outcome**
- **visual proof before explanation**
- a **specific human moment** instead of an abstract problem
- **numbers you can check**
- **honest challenges** for credibility
- a bit of **personality**

**Hero**
- Spec line: `Desk robot / Calculus / StormHacks 2026`
- Nameplate: `OTTER TUTOR`
- Headline: **It sees your mistake. It won't tell you the answer.**
- Sub: A desk robot that watches you solve calculus on a whiteboard, points a laser at the line where it went wrong, and lets you fix it yourself.
- Buttons: `Try the demo` (laser) / `Watch it move` (scrolls to the video)
- Otter bubble cycles: "Watching the board…" → "Reading line 2…" → "Hmm, take another look at which rule fits line 2." → "Nice work, that all checks out."

**360° robot**
- Title: **Real hardware. Built overnight.**
- Video caption: Two servos, one laser, seven printed parts. The arm pans and tilts to land on any line of the board.
- Spec table: Display 2.8" / 320×240, 6 moods · Arm 2× SG90, pan + tilt · Pointer red laser, auto-off 6 s · Eyes 2K webcam + mic · Brain ESP32 ↔ laptop over Wi-Fi

**The 1 a.m. problem**
- Title: **It's 1 a.m. Line 3 is wrong. You can't see why.**
- Body: So you snap a photo, an app hands you the full solution, and you copy it down. It feels like progress. Then the quiz shows up, and there's no app on the quiz.
- Kicker: Getting the answer isn't the same as finding it.
- Three tiles (categories, no brand names): **Photo solvers** "Answer in two seconds. Learning in zero." · **Chatbots** "Ask for a hint, get the whole solution." · **Answer keys** "They tell you *that* it's wrong, not *where*."

**Your turn (demo)**
- Title: **Your turn. Pick a line 2.**
- Prompt: Find d/dx [x² · sin x]. Choose what you'd write next.
- Choices:
  - `(2x sin x − x² cos x) / sin² x` → wrong_rule
  - `2x sin x + x² sin x` → misapplied
  - `2x sin x + x cos x` → arithmetic
  - `2x sin x + x² cos x` → ok
- Behavior: the otter shows "thinking" for ~1.4 s. On a mistake: the laser dot lands on line 2, the red-pen circle draws around the wrong term, the otter talks and then turns confused, and the bubble shows the real nudge line. On the correct line: it's happy and says the praise line.
- Fine print: These are the robot's real lines. Notice what it never says.

**How it decides**
- Title: **Quiet until it's sure.**
- Steps (numbered, it's a real sequence):
  1. **It waits.** Nothing happens until your marker stops moving.
  2. **Gemini reads every line** and boxes the first one that's off.
  3. **SymPy re-checks the math.** If the two disagree, the otter stays quiet.
  4. **The laser lands**, the otter frowns, and you hear which line, never which rule.
- System status table: Moods 6 · Confidence to speak 0.70 · Repeat cooldown 20 s · Laser auto-off 6 s · Answers given 0
- Rules tile: **Name the line, never the fix.** · **Say it once.** · **A false alarm is worse than a miss.** · **Laser stays below eye level.**

**Built in 24 hours**
- Title: **What broke, and what we did about it.**
  - Gemini's free tier gave us 20 requests a day. We built key rotation, model fallbacks, and a cached demo run.
  - The first arm swung straight into its own body. We tested every angle in CAD until nothing collided.
  - The AI sometimes flagged correct work. Now a math engine has veto power.
- Stack line: Gemini API · ElevenLabs · OpenCV (C++) · SymPy · ESP32 · Bambu Lab printing
- Team: Leandro · Sebas · Chris · Allen (roles: ask me)

**Footer (direct ask)**
- **Bring a whiteboard. The otter brings the laser.**
- Built at StormHacks 2026, SFU Burnaby. A student project, not an official StormHacks page. Devpost / GitHub links: TODO.

**Writing rules (so it reads like people wrote it):**
- Short sentences, concrete nouns, plain verbs. Read every line out loud. If you wouldn't say it to a judge, cut it.
- Banned words and patterns:
  - "revolutionize, seamless, empower, unlock, harness, leverage, cutting-edge, game-changer, next-generation, elevate, journey, delve, robust"
  - "Imagine a world…", "In today's fast-paced…"
  - "not just X, it's Y"
  - rhetorical triads everywhere
  - em-dash chains
  - exclamation marks
  - emoji
  - ALL-CAPS labels (the nameplate is the only exception)
- No accent-colouring a single word in headlines. The red-pen circle is the only emphasis device.

## 7. Assets
Everything is in `incoming/`. Copy what you use into `website/assets/`.
- `robot_360.mp4` + `robot_360.webm` (preferred, ~200 KB) and `robot_360.gif` (fallback). Use `<video autoplay muted loop playsinline poster=…>` with both sources. **This is the most important visual on the page.**
- `robot_model.stl`: optional live wireframe in the hero's dark tile (three.js from a CDN, STLLoader + EdgesGeometry, slow rotation, lazy-init). If it costs performance, skip it. The video matters more.
- `otter_arm_motion.gif`, `view_*.png`: extra CAD renders, optional.
- Missing (leave labeled placeholders and list them): photos of the real robot and the team, the demo video, links.

## 8. Tech constraints
- Plain HTML + CSS + vanilla JS, no build step, all in `website/`: `index.html`, `styles.css`, `main.js`, `otter.js`, `demo.js`, `assets/`. three.js from a CDN is the only allowed library.
- Semantic HTML, alt text, visible focus, AA contrast, responsive from 360 px, no horizontal scroll.
- Lazy-load anything below the fold. Lighthouse ≥ 90 on performance and accessibility.

## 9. Phases (stop after each one)
- **Phase 1 (REDO NOW):** throw away the old look. Build all sections with design v3 and the copy deck, including the static math background and the 360° video. No demo logic yet.
- **Phase 2:** port the otter canvas; hero loop + otter screen tile.
- **Phase 3:** interactive demo (choices, laser dot, red-pen circle, otter reactions, real lines).
- **Phase 4:** polish: the 60-second scroll test (time it), reduced motion, accessibility, Lighthouse, 360/768/1920 px checks.
- **Phase 5:** `website/README.md`: how to preview, and how a teammate can publish later (steps only, don't do it).

## 10. Preview
From this folder: `python -m http.server 8000 --directory website` → http://localhost:8000 (Ctrl+F5 to reload).

## 11. Feedback round 1 (Sebastian, after Phase 1). These override anything above.
**Why the interactions "don't work":** `otter.js` and `demo.js` don't exist yet (that's Phases 2–3). Build them now, with the changes below.

**Facts that changed:**
- **Moods:** we'll probably add more. Don't print a fixed count. Say "moods like listening, thinking, talking, happy, confused…", and in tables show `Moods: 6+`.
- **Microphone:** the **laptop's mic** (not the webcam's). Hardware table: Eyes = 2K webcam, Ears = laptop mic, Voice = laptop speakers (ElevenLabs).
- **Laser:** stays **on while it points**. Remove every "auto-off 6 s". Keep only the safety line "can't tilt above the board".
- **Timing:** replace "Repeat cooldown 20 s" with **"Waits after you stop writing: 5 s"** (STILL_S). Add **"Repeats the same nudge: never"** (it flags each mistake once).
- **Photos:** remove every photo placeholder on the page (robot photos and team photos). The **team section uses our avatars** from `incoming/avatars/` (`leandro.png`, `sebas.png`, `chris.png`, `allen.png`). If they're missing, show a clean initial-letter avatar and list the missing files.

**Whiteboards must never look empty:**
- The hero board is good. Keep it.
- The **demo board** starts with line 1 already handwritten. Line 2 is a dashed ghost line labeled "your line 2 appears here". When the visitor picks an option, line 2 **writes itself in** (Kalam, a stroke-by-stroke reveal), then the otter reacts.
- Any other board-like tile gets real handwritten content (a derivation, a sketch), never a blank rectangle.

**The demo must show what happens, not just offer 4 buttons:**
- **Auto-play:** if the visitor hasn't clicked within **30 s** of the demo entering view, auto-pick option A. A judge who just scrolls still sees the full reaction.
- After a pick, show a **"What the otter did"** verdict panel (spec-sheet style) with four rows:
  1. **Verdict:** `wrong_rule` / `misapplied` / `arithmetic` / `ok`, plus a confidence like `0.86`.
  2. **It said:** the real nudge line, also in the otter's speech bubble.
  3. **It did:** "laser on line 2 · face: confused" (or "face: happy").
  4. **It knew, but didn't say:** the hidden reason, blurred or redacted (e.g. "this is a product, not a quotient"). A "reveal" toggle shows that the robot knows the fix and deliberately holds it back. This is the selling point.
- Each option keeps a small caption so people know what kind of slip it is *after* choosing ("wrong rule", "forgot a derivative", "dropped a power", "correct").
- Add a **"Reset"** button. Respect reduced motion (no stroke animation, instant states).

**Section 02 / method suggestion: PENDING, don't build until I confirm.**
Sebastian wants section 02 to say the otter *suggests the method* that solves the problem without solving it. The current robot code (`prompts.py` / `policy.py`) **forbids** naming the rule or method. Don't claim it until I confirm the team changed the robot. If I say "method hint confirmed", then:
- describe 2 levels: (1) by default it names the line and the kind of slip; (2) if you say "I'm stuck", it suggests **which method** to try (e.g. "this one wants a substitution"), never the steps or the answer;
- show level 2 in the demo verdict panel as "If you say 'I'm stuck'".

**Team roles (confirmed):**
- **Chris:** the brain: Gemini vision, the SymPy check, nudge policy, and the laptop server.
- **Sebas:** CAD and the 3D-printed body/arm, plus a lot of the electronics.
- **Leandro:** hardware (electronics, wiring, firmware). Ask before adding detail.
- **Allen:** hardware (electronics, wiring, firmware). Ask before adding detail.
Use short, human one-liners under each avatar. Don't invent fun facts.

## 12. Feedback round 2: sync with the team's NEW code (overrides everything above)
**Source of truth is now `../Hackathon26--main (1).zip`.** Unzip it into `./reference_v2/` once. It and `reference/` are **READ-ONLY**: never edit, move, delete, commit, or push anything in them. Only re-adapt the *information* on the website. The old `otter-robot-esp32/` folder no longer exists; the robot code is in `otter-robot-arduino/`.

**1. The otter changed: match the robot exactly.** Port `reference_v2/.../otter-robot-arduino/otter_robot/otter.cpp` **1:1** into `website/otter.js` and replace the old brown otter.
- The screen is now **portrait 240×320**. Make the otter-screen tile 3:4 portrait.
- Colors, from `color565`:
  - background `rgb(52,53,94)`, stripes `rgb(69,71,120)`
  - outline `rgb(43,34,51)`
  - fur `rgb(247,174,0)`, muzzle `rgb(255,212,94)`
  - eyes `rgb(59,30,30)`, nose `rgb(224,104,96)`
  - mouth `rgb(122,42,42)`, tongue `rgb(240,138,138)`
  - blush `rgb(232,96,48)`, stars `rgb(255,211,77)`, dots `rgb(201,207,224)`
- Same 6 moods, blink, bob, mouth level and extras: thought bubble, white "?", stars, sound bars.
- Update the screen frame color around it to suit the navy screen. Remove the old brown `--fur`/`--cream` tokens.

**2. The real hint ladder (from `brain/policy.py` + `prompts.py`). Describe it exactly like this:**
- **First nudge:** it names *what you were doing* and the line, e.g. "Check how you took the derivative on line 1."
- **Second hint**, given once, if you ask again, keep writing with the mistake still there, or stay stuck for 60 s: it points at the *exact part* of the line, e.g. "Look at what happened to the x when you took the derivative on line 1."
- **Never:** the rule's name, the method, a corrected step, or the answer. A word filter enforces it.
- **You can talk to it:** push-to-talk on the **laptop mic**. It answers small talk and explains concepts in plain words. If your question is about the mistake, it answers by the same rules and the laser points at that line.
- Section 02 / "how it decides" must say this ladder. **Do NOT say it tells you the method.** The code forbids that. If the team later adds a method level, I'll tell you.

**3. Demo panel: show both levels.** For each choice show "First nudge", then a button **"Keep going with the mistake"** that reveals the "Second hint" (the otter talks again, the laser stays on line 2). Use these lines, built from the real templates:
- **A** `(2x sin x − x² cos x)/sin² x` · wrong_rule
  - First: "Hmm, take another look at which rule you picked when you took the derivative on line 2."
  - Second: "Look at what ended up on the bottom of your answer on line 2."
- **B** `2x sin x + x² sin x` · misapplied
  - First: "Check how you took the derivative on line 2."
  - Second: "Look at what happened to the sin x in the second term on line 2."
- **C** `2x sin x + x cos x` · arithmetic
  - First: "Double-check the arithmetic when you took the derivative on line 2."
  - Second: "Check the power on the x in the second term on line 2."
- **D** `2x sin x + x² cos x` · ok: "Nice work, that all checks out."

Keep the "It knew, but didn't say" redacted row.

**4. Numbers, from `brain/config.py` and `otter-robot-arduino/otter_robot/config.h`:**
- confidence to speak 0.70
- waits after you stop writing 5 s
- second hint after 60 s stuck (or when you ask)
- 20 s between spoken nudges
- pan ±60°; tilt −25° to +15° (laser stays below eye level)
- **laser safety auto-off 6 s** (`LASER_TIMEOUT_MS 6000` is back in the code, so this replaces round 1's "laser constant")
- ears: laptop mic; voice: ElevenLabs through the laptop speakers
- moods 6

**5.** Everything else from section 11 still applies (no photos, avatars, the whiteboard writes itself, auto-play at 30 s, English only).

---

## 13. Feedback round 3: real photos, circuit, smoother motion (latest; overrides earlier rules where they conflict)

The robot is built. The site has almost no pictures of the real thing, and that is now the biggest gap. **Round 1's "no photos" rule is cancelled for these photos only.** Never add stock photos or invented images.

### 13.1 New assets (read-only in `incoming/`, copy what you use to `website/assets/photos/`)
Already resized, metadata stripped. Use `loading="lazy"`, real `width`/`height`, and `object-fit: cover` crops.
- `incoming/photos/final-front-tripod.jpg` (739×1600): the finished yellow robot from the front, on the webcam and tripod. The otter is on the screen, and the laser arm is on the right.
- `incoming/photos/final-back-wiring.jpg` (1200×1600): the back opened up. The ESP32 sits on a mini breadboard inside the case, with the servo leads labeled by hand.
- `incoming/photos/final-test-tripod.jpg` (1200×1600): first full test. The robot is on the tripod while a teammate checks it from his phone.
- `incoming/photos/build-printed-case.jpg` (895×1600): the first printed case, ears included, holding the screen in a hand.
- `incoming/photos/build-first-boot.jpg` (1200×1600): first boot on the breadboard. The otter's colors came out inverted (blue instead of gold).
- `incoming/photos/circuit-diagram.jpg` (1367×720): our wiring diagram. It shows the ESP32 DevKit, the pan and tilt SG90 servos, the KY-008 laser, the 2.8" ILI9341 screen, a 1 kΩ resistor, an NPN transistor and a 470 µF capacitor.
- `incoming/motion-reference/otter-tutor-deck.html` is our pitch deck. Read it **only for how its motion feels** (13.4). Do not copy its pastel look, fonts, canvas sea, otter drawing or text.

### 13.2 Hardware section (`#robot`): show the real robot
- Put `final-front-tripod.jpg` next to the 360° CAD video as a pair: **"The CAD" / "The real one"**. Use the same tile system, the corner marks and a mono caption like `Fig. 2 · Photo · first full test`.
- Replace the hatch tile "7 printed parts" with `build-printed-case.jpg`, and keep the big **7** over the photo as a label.
- The spec sheet stays.

### 13.3 New section `#circuit`, directly after `#robot` (number it **02 / Circuit** and renumber the later section heads; add it to the nav)
- Title idea: **"How it's wired."** Keep the copy short and plain, following the anti-AI writing rules in §6.
- Big tile: `circuit-diagram.jpg` on a light panel, with **numbered hotspots** over the parts: 1 ESP32, 2 pan servo, 3 tilt servo, 4 laser + NPN + 1 kΩ, 5 screen, 6 470 µF capacitor. Hovering or focusing a hotspot highlights its row in the pin table, and the reverse works too. The hotspots must be keyboard-reachable buttons with labels, and positioned in % so they stay on the parts at every width.
- Side tile: `final-back-wiring.jpg`, captioned "The same circuit, packed into the case."
- Pin table, taken from `reference_v2/.../otter_robot/config.h` and `TFT_eSPI_User_Setup.h`. Use these exact values:
  - Pan servo: GPIO 25
  - Tilt servo: GPIO 26
  - Laser: GPIO 27 (firmware turns it off after 6 s)
  - Screen (SPI): MOSI 23 · SCLK 18 · MISO 19 · CS 5 · DC 16 · RST 17
- One small footnote, because `config.h` says so: "The diagram shows the transistor version from our wiring guide. On the final robot the laser runs straight from GPIO 27, active-low."
- Do not state voltages, currents or part values that are not in the diagram or the code.

### 13.4 Smoother motion (take only the feel from the deck)
- **Reveals:** elements rise 24–34 px and fade in, `cubic-bezier(.2,.7,.2,1)`, 0.8–1 s, staggered about 100 ms per item inside a section. Use IntersectionObserver.
  - The page must be fully readable without JS. Only hide things after JS adds a class to `<html>`.
  - Add a fallback timer so nothing stays invisible if the observer never fires.
- **State changes ease instead of jumping:**
  - The otter's mood switches after a short beat.
  - The laser dot glides to its spot with a soft glow pulse.
  - The red-pen circle draws itself (stroke-dashoffset).
  - Speech bubbles crossfade.
  - Demo verdict rows fill in one after another.
- **Ambient life, small and slow:** the otter breathes/bobs and blinks (already in `otter.js`; keep it smooth), plus a faint laser glow.
- **Photos:** settle from scale 1.03 to 1 on reveal. Add a **lightbox** on click: fade and scale in, Esc or click closes it, focus returns to the photo, and arrow keys move between photos.
- **Tiles:** on hover they lift 2–4 px with a 250 ms shadow transition.
- **Performance:** animate only transform and opacity, and keep it at 60 fps. Under `prefers-reduced-motion`, turn all of it off.
- Smooth scrolling for nav links.

### 13.5 New section "The final setup", placed just before `#build` ("What broke…")
- Title idea: **"From breadboard to tripod."** It shows the real order of the build, so numbering is fine:
  - ① `build-first-boot.jpg`: "First boot. The colors came out inverted."
  - ② `build-printed-case.jpg` may appear again here only if it is cropped differently; otherwise skip it.
  - ③ `final-test-tripod.jpg`: "First full test on the tripod."
- Make it a horizontal photo strip on desktop and stack it at 360 px. All photos open in the same lightbox.

### 13.6 Rules that still hold
- English only on the site, the CROX design (§4) and everything from rounds 1–2, except "no photos".
- Work only inside `website/`.
  - Never modify `Hackathon26-/`, `reference/`, `reference_v2/` or `incoming/`.
  - No git commit, push or deploy.
- **When done:**
  - Preview at `http://localhost:8000` (`python -m http.server 8000 --directory website`).
  - Check that the console has no errors.
  - Check 1440 px and 360 px widths with no horizontal scroll, and that the hotspots line up.
  - Then report back to me in Spanish and stop.

### 13.7 Status: round 3 is already built (Oct 4, by Claude in Cowork)
- `website/` now has the real photos in `#robot`, the `#circuit` section with hotspots + pin map, the `#setup` strip, the lightbox and the smoother motion (reveals, bubble crossfade, laser glide/glow, verdict rows). A copy of the round-2 site is in `backup_website_round2/`.
- Small deviations from 13.2/13.5 above: the hatch "7" tile stayed; `build-printed-case.jpg` is used once, in the final-setup strip (step 2).
- Don't rebuild these. Only fix bugs or do what I ask next.
