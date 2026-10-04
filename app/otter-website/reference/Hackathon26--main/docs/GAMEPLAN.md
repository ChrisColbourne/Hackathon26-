# Otter Tutor: 24h Build Plan (4 people)

SFU StormHacks · Oct 3, 2026

A whiteboard tutor that watches a student solve math, and when it sees a mistake
it says so, out loud, without giving away the fix. It points a laser at the bad
line, and its face (an otter on an LCD) reacts.

## What changed from the first plan

| Old plan | Now |
|---|---|
| Raspberry Pi as the brain | **Laptop** is the brain. The Pi is gone. |
| Phone browser camera | **2K USB webcam** plugged into the laptop, aimed at the board |
| Phone/laptop mixed audio | **Laptop mic and speakers** for everything |
| Socratic hint ladder | **Flag + vague nudge.** Names the line and the kind of slip, never the right rule |
| ESP32 + servos + laser + LCD | Unchanged |

Everything else below is written against the new setup.

## Read this first: Gemini quota

Measured Oct 3 on our free-tier key: **`gemini-3.8-flash` allows 20 requests per
day**, `gemini-3.1-pro` allows **0**, and every model has its own daily counter.
One rehearsal burns a day of quota. Before any end-to-end testing:

1. **Upgrade the key to the paid tier** (AI Studio → API keys → Set up billing,
   $5 prepay). This is the fix. Do it tonight.
2. Until then, every teammate creates a key in their *own* Google Cloud project
   and we put them all in `.env` as `GEMINI_API_KEYS=k1,k2,k3`; the brain rotates
   on 429s. 3.7-flash and 3.6-flash are the automatic fallbacks.
3. Run **one** brain process at a time, and prefer `PREFER_CACHE=1` with the demo
   cache when rehearsing the fixed demo problem.
4. **A, C, D: use mock mode.** `GEMINI_MOCK=1 python -m brain.server` (or
   `run_cli --mock`) sends real face/look/laser commands, nudges and app events
   from canned verdicts, with zero Gemini calls. Only B's own testing needs quota.

## Who owns what

| Person | Owns | Done means |
|---|---|---|
| **A: Hardware + firmware** (C++) | ESP32, wiring, power, servos, laser, WebSocket client, calibration | Robot obeys JSON commands over Wi-Fi |
| **B: AI brain** (Python + C++) | Laptop server, webcam pipeline, Gemini vision, SymPy check, nudge policy, laser targeting, sponsor data | A frame of the board becomes a verdict, a nudge, and a point to aim at |
| **C: Voice, app + demo** | ElevenLabs TTS/STT, push-to-talk, web app, pitch, Devpost | The otter talks and listens; demo runs start to finish |
| **D: Otter face + body** | Otter animation on the LCD, 3D-printed shell, assembly | Otter blinks, talks, reacts in 6 moods, inside a finished body |

Prize fit: **Gemini** is B's work (it reads, reasons, locates). **ElevenLabs** is
C's (voice). **Tiger Data / Snowflake / .tech / Solana** are B's stretch items,
in that order, only after the core demo works.

## Repo layout

```
Hackathon26-/
  brain/          B · Python laptop server (FastAPI + WebSockets), Gemini, SymPy, policy
  brain/vision/   B · C++ OpenCV module (board crop/deskew + change detection), pybind11
  brain/voice.py  C · ElevenLabs speak()/listen(), runs inside the brain process
  app/            C · web app (static HTML/JS) served by the brain
  firmware/       A · ESP32 PlatformIO project; D's otter module lives in firmware/src/otter/
  dashboard/      B/C · .tech site (session summaries), reached via ngrok
  docs/           this file, wiring, contracts, demo script
  .env            secrets (gitignored). GEMINI_API_KEY, ELEVENLABS_API_KEY, TIGER_DSN, ...
```

Build everything against mocks until hour 6, then join.

## Architecture (laptop is the boss)

```
 webcam ──► brain/camera.py ──► vision (C++) ──► "board settled?" ──┐
                                                                    ▼
 app "check my work" / push-to-talk transcript ────────────► gemini_brain.see()
                                                                    │  Flash, Pro fallback
                                                                    ▼
                                            verifier.py (SymPy double-check)
                                                                    ▼
                                            policy.py (flag once, cooldown, nudge text)
                                      ┌─────────────┼──────────────┬──────────────┐
                                      ▼             ▼              ▼              ▼
                                 robot.py       voice.py       app (WS)      session.py
                              ESP32: face/   ElevenLabs:     status, hint,  Tiger Data log
                              look/laser     speak(nudge)    summary        → Snowflake, Solana
```

Trigger modes (both): **auto**, when the board changes and then holds still for a
few seconds; and **on demand**, from the app button or "check my work" by voice.

## Contracts (agree in hour 1, don't change silently)

### 1. Brain → ESP32 (WebSocket, JSON) — unchanged

| Message | Example | Robot does |
|---|---|---|
| face | `{"action":"face","state":"thinking"}` | idle, listening, thinking, talking, happy, confused |
| mouth | `{"action":"mouth","level":0.6}` | opens mouth 0..1, ~15×/s while talking |
| look | `{"action":"look","pan":-18,"tilt":12}` | turns head, degrees |
| laser | `{"action":"laser","on":true,"pan":-22,"tilt":8}` | aims, then laser on; `on:false` off |
| home | `{"action":"home"}` | laser off, head centred, idle face |

ESP32 → brain: `{"status":"ready"}` on connect, `{"status":"done","action":"look"}` after each move.

### 2. Gemini → Brain (structured JSON, see `brain/schemas.py`)

```json
{
  "board_text": "d/dx [x^2 sin x] = (2x sin x - x^2 cos x) / sin^2 x",
  "problem": "d/dx [x^2 sin x]",
  "topic": "derivative",
  "board_complete": true,
  "steps": [
    {"line": 1, "latex": "\\frac{d}{dx}[x^2 \\sin x]", "status": "ok",
     "rule_used": null, "rule_expected": null, "box": [120, 80, 220, 700]},
    {"line": 2, "latex": "\\frac{2x\\sin x - x^2\\cos x}{\\sin^2 x}", "status": "wrong_rule",
     "rule_used": "quotient_rule", "rule_expected": "product_rule", "box": [260, 80, 380, 900]}
  ],
  "first_error_line": 2,
  "confidence": 0.86,
  "nudge": "Hmm, look again at which rule fits line 2.",
  "mood": "confused"
}
```

- `status` ∈ `ok | wrong_rule | misapplied | arithmetic | unclear`. `unclear` means
  "can't read it", and is never spoken.
- `box` is Gemini's `[ymin, xmin, ymax, xmax]` on a 0–1000 scale. B maps its
  centre to pan/tilt with A's 4 calibration corners.
- `nudge` may name the **line** and the **kind** of slip (rule choice, how the rule
  was applied, arithmetic). It must never name the correct rule or write a
  corrected expression. The policy layer re-checks this with a word filter.

### 3. Brain ↔ App (WebSocket, JSON)

Brain → app: `{"event":"state","state":"thinking"}`,
`{"event":"nudge","text":"...","line":2,"kind":"wrong_rule"}`,
`{"event":"analysis", ...BoardAnalysis}`, `{"event":"summary", ...}`.

App → brain: `{"cmd":"check_now"}`, `{"cmd":"student_said","text":"..."}`,
`{"cmd":"stuck"}`, `{"cmd":"end_session"}`.

## Timeline

Gates: **H6** pieces talk to each other · **H12** full loop on real hardware ·
**H18** code freeze · **H20+** rehearse. If a gate slips >1h, cut from the
stretch list, don't move the freeze.

### B: AI brain (Gemini) — detailed, since this is the Gemini entry

**H0–6, alone (laptop + webcam, no robot needed)**
1. `run_cli.py`: webcam → frame → Gemini → print verdict. Prove the core idea on a
   real whiteboard photo in the first 2 hours.
2. `gemini_brain.see()`: Interactions API, structured JSON output, `thinking_level=low`
   (~10–17 s per check; higher levels take far longer). Flash first; re-ask the
   next model in the chain when confidence < 0.7, on a 429, or if JSON fails to parse.
3. `vision/` C++: find the whiteboard quad, warp it flat, return a change score
   vs the last analysed frame. Python fallback if the build fails.
4. "Settled" detector: changed, then still for ~5 s, at most one auto-check per
   12 s → trigger a check. Never call Gemini while the hand is in the frame or
   ink is still appearing; a student pausing between strokes must not drain quota.
5. `verifier.py`: SymPy re-derives derivatives/integrals/algebra from the problem
   and compares to the student's line. Gemini says "wrong", SymPy confirms;
   disagree → trust SymPy, lower confidence.
6. `policy.py`: speak only above threshold; flag each (line, kind) once; 20 s
   cooldown; strip any rule names from the nudge.
7. `robot.py` prints commands until A's ESP32 exists.

**H6–12, with A and C**: real `face/look/laser` to the ESP32; `nudge` → C's
`speak()`; C's transcript → next `see()` call as context. Server with both
WebSockets up.

**H12–18**
- Box → angles: centre of `box` → pan/tilt via bilinear interpolation over A's 4 corners.
- Stuck detection: board unchanged ~60 s → `thinking` face, offer a nudge.
- Session memory: last few nudges + what the student said → next prompt.
- Session summary at the end: steps checked, mistakes by kind, the one to review.
- Tiger Data: insert one row per check (`session_id, ts, topic, line, kind, confidence`).
- Demo cache: 3 cached Gemini replies for the planted demo problem.

**H18–20**: freeze. Only cached-reply and threshold tweaks after this.

**Stretch, in order** (only after H12 gate passes): `.tech` dashboard via ngrok
reading Tiger Data → Snowflake export of mistake table + one "most common slip"
query → Solana "practice badge" mint on `end_session`.

### A: hardware + firmware — as in the first plan
Power rail, screen to D within 2 h, servos with easing and hard limits (tilt
never above the board), laser via 2N2222, Wi-Fi + WebSocket client, test every
message by hand before B's server exists. H12–18: 4-corner calibration mode
with B, mood-matched head moves, mount everything with D. **Change**: the ESP32
connects to the **laptop's** IP, no Pi.

### C: voice, app + demo — as in the first plan, two changes
Audio is all on the **laptop**: `speak(text, mood)` streams ElevenLabs to the
laptop speakers and emits `mouth` levels; `listen()` is **push-to-talk** on the
laptop mic (ElevenLabs STT, browser speech API as backup). The app adds a
**"Check my work"** button that sends `check_now`. Pre-record one line per mood.
Devpost names Gemini (sees + locates) and ElevenLabs (speaks + listens).

### D: otter face + body — unchanged
Browser canvas prototype at 320×240 first, 6 moods, port to TFT_eSPI/LovyanGFX
shapes with sprite redraws, `setMood()` / `setMouth()`, prints running the whole
time. Reuse the canvas otter as the app's mascot for C.

## Tools and references (suggested, not required)

| Need | Use | Why |
|---|---|---|
| Read handwritten math | **Gemini 3.8 Flash** (vision) | Reads handwriting + layout + boxes in one call. No separate OCR. |
| Backup math OCR | [pix2tex / LaTeX-OCR](https://github.com/lukas-blecher/LaTeX-OCR) | Image → LaTeX, offline. Only if Gemini misreads a lot. |
| Verify the math | **SymPy** + `latex2sympy2` | Prevents false flags on correct work: the biggest demo risk. |
| Board crop/deskew, change detection | **OpenCV (C++)** + pybind11 | Fast, and it's the C++ part of the project. |
| Speech out / in | **ElevenLabs** TTS (flash model) + STT | Sponsor; low latency. |
| Wake word (stretch) | [openWakeWord](https://github.com/dscripka/openWakeWord) | "Hey Otter". Risky in a loud venue; keep push-to-talk. |
| ESP32 screen | TFT_eSPI or LovyanGFX | Shapes, not bitmaps, to save RAM. |
| Session log | **Tiger Data** (Postgres/Timescale) | One table, five columns. Powers the summary + dashboard. |
| Public dashboard | **.tech domain** + **ngrok** | Judges open `ottertutor.tech` on their phone. |
| Analytics | **Snowflake** | "Most common mistake across sessions". Prize-driven. |
| Badge | **Solana** devnet | Mint a practice token on `end_session`. Prize-driven, novelty. |

## Fallbacks

| If this fails | Fall back to | Owner |
|---|---|---|
| Gemini misreads handwriting | Bigger, neater writing; dark marker; re-ask Pro; SymPy veto | B |
| Gemini slow/offline | 3 cached replies for the demo problem | B |
| Gemini 429 (quota) | Key rotation → 3.7/3.6-flash → demo cache. Real fix: paid tier | B |
| False flag on correct work | SymPy veto + raise threshold to 0.85 | B |
| C++ vision build breaks | `vision_py.py` pure-Python fallback (same interface) | B |
| Laser calibration off | Head turns toward the board zone, no laser | A + B |
| Servos jitter / reset ESP32 | Check common GND + cap; else face only | A |
| Otter flickers / OOM | Fewer moods; redraw eyes + mouth only | D |
| ElevenLabs slow/offline | Pre-recorded lines, then browser voice | C |
| Venue Wi-Fi bad | Phone hotspot for laptop + ESP32 | All |
| Everything | Backup video of a good run | C + D |

## Demo script (~2 min)

1. Otter wakes, greets the judge (ElevenLabs).
2. Teammate writes `d/dx [x² sin x]` and solves it with the **quotient rule**.
3. Board settles → thinking face → Gemini reads → head turns, laser on line 2.
4. Otter: *"Hmm, look again at which rule fits line 2."* No answer given.
5. Teammate: "Oh, it's a product." Fixes it. Otter: happy face, *"Nice work."*
6. Laptop shows the session summary (+ dashboard on a phone if the stretch landed).
7. Close: who it helps, Gemini sees and locates, ElevenLabs speaks and listens.
