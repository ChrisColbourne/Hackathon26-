# brain/ — the laptop brain (Person B)

Webcam → OpenCV (C++) → Gemini → SymPy check → nudge policy → robot + voice + app.
Contracts and the full plan: [../docs/GAMEPLAN.md](../docs/GAMEPLAN.md).

## Setup (once)

```bash
sudo apt install python3.12-venv libopencv-dev cmake g++     # Ubuntu
python3 -m venv .venv && source .venv/bin/activate
pip install -r brain/requirements.txt
cp .env.example .env    # then paste GEMINI_API_KEY and ELEVENLABS_API_KEY
brain/vision/build.sh   # optional: compiles the C++ vision module; Python fallback otherwise
```

## Try it

```bash
# NO QUOTA NEEDED: canned verdicts cycle wrong-rule / correct / arithmetic.
# This is how A, C and D test the robot, voice and app against the brain.
python -m brain.run_cli --camera --show --mock
GEMINI_MOCK=1 CAMERA_ENABLED=1 python -m brain.server

# fake board, no camera (one real Gemini call)
python -m brain.tools.make_test_board /tmp/board.jpg --case quotient
python -m brain.run_cli --image /tmp/board.jpg

# live webcam, auto-check when the board settles; c = check now, b = toggle board detection, q = quit
# Keys work in the preview window (click it first so it has focus) or typed in the
# terminal followed by Enter. Esc, closing the window, and Ctrl+C also quit.
python -m brain.run_cli --camera --show
# every check saves what Gemini saw to brain/recordings/<stamp>.jpg (+ .json once it answers)

# the real server (ESP32 -> ws://LAPTOP:8000/robot or /ws/robot, app -> /ws/app)
CAMERA_ENABLED=1 python -m brain.server
python -m brain.server --show          # same + camera preview window (c = check now, t = talk, p = pause auto-checks, b, q)
python -m brain.tools.voice_test       # mic, speakers, ElevenLabs voice + transcription, one at a time
python -m brain.tools.serial_bridge    # 2nd terminal, only if the robot is on USB instead of Wi-Fi
curl -F image=@/tmp/board.jpg localhost:8000/check | python -m json.tool
```

## Files

| File | Does |
|---|---|
| `gemini_brain.py` | `see(jpeg, context) -> BoardAnalysis`. Flash, Pro fallback, structured JSON. |
| `prompts.py` | System prompt + the forbidden-words list for nudges. |
| `schemas.py` | Contracts 1–3 as pydantic models. The Gemini JSON schema comes from here. |
| `verifier.py` | SymPy re-derives the math; vetoes false flags. |
| `policy.py` | Speak or not: threshold, flag-once, cooldown, word filter, praise. |
| `camera.py` | Webcam + `SettleDetector` (changed, then still ~3 s → check). |
| `vision/` | C++ OpenCV: find board, deskew, enhance, change score. `vision_py.py` = fallback. |
| `calibration.py` | Gemini box → laser pan/tilt via 4 calibrated corners. |
| `robot.py` | Contract 1 commands; mocks when no ESP32 is connected. |
| `voice.py` | `speak()` ElevenLabs TTS with real lip sync + cache; `listen()` mic → ElevenLabs Scribe. Mock without a key. |
| `audio.py` | Laptop mic (built-in, never the webcam) and speakers via `parecord`/`pacat`. |
| `session.py` | Memory, prompt context, summary, sinks for Tiger Data/Snowflake. |
| `server.py` | FastAPI: `/ws/robot`, `/ws/app`, `POST /check`, `/health`, serves `app/`. |
| `run_cli.py` | Dev loop without the server. |
| `recordings/` | Every analysed frame + reply (gitignored). Source for the demo cache. |

## Tuning knobs (`.env`)

`SPEAK_THRESHOLD=0.7` · `PRO_FALLBACK_BELOW=0.7` · `COOLDOWN_S=20` · `STILL_S=5` · `MIN_CHECK_INTERVAL_S=5` ·
`STUCK_AFTER_S=60` · `CAMERA_INDEX=auto` · `CAMERA_NAME=` · `CAMERA_ENABLED=1` · `BOARD_DETECT=1` · `FLASH_THINKING=low` ·
`GEMINI_FLASH_MODEL=gemini-3.8-flash` · `GEMINI_ALT_MODELS=gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash` ·
`GEMINI_API_KEYS=k1,k2` (rotates on 429) · `PREFER_CACHE=1` (serve `demo_cache/` first)

## Talking to the otter

Tap `t` in the preview window (or type `t` + Enter in the terminal) and ask out loud.
The laptop's built-in mic records until you've been quiet for ~1 s (tap `t` again to stop
early), ElevenLabs transcribes it, and one Gemini call answers it while looking at the board:
small talk, concepts in plain words, or your work, but never the answer or a formula. The
reply plays on the laptop speakers while the LCD otter lip-syncs to it. Spoken lines are
cached in `brain/tts_cache/`, so repeats cost no ElevenLabs credits.

## Quota (read before testing)

Free tier = **20 requests/day on 3.8-flash, 0 on Pro**, per model. One `run_cli --camera`
session can burn that. Upgrade the key to paid, or pool teammates' keys via `GEMINI_API_KEYS`.
Run one brain process at a time; the SDK's retry sleep on a 429 can last over an hour, which
is why `gemini_brain.py` disables retries and enforces its own deadline.
