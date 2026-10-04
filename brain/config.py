"""All knobs in one place. Override any of them in .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# One key, or several separated by commas. Each Google Cloud project has its
# own free-tier quota, so a 429 on one key just rotates to the next.
GEMINI_API_KEYS = [k.strip() for k in os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", "")).split(",") if k.strip()]

# Gemini. Flash answers first; Pro is re-asked when Flash is unsure.
FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-3.8-flash")
# Fallbacks, in order. Measured on the free tier (Oct 3): each model has its own
# daily quota (3.8-flash: 20 requests/day), 3.7/3.6-flash answer in ~2 s, 3.5-flash
# kept answering when the newer ones were all overloaded (Oct 3), and
# Pro has ZERO free requests, so Pro is opt-in for paid keys only.
ALT_MODELS = [m.strip() for m in os.getenv("GEMINI_ALT_MODELS", "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash").split(",") if m.strip()]
PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "")           # e.g. gemini-3.1-pro-preview
PRO_FALLBACK_BELOW = float(os.getenv("PRO_FALLBACK_BELOW", "0.7"))
# Per-model deadline. Healthy answers take 4-17 s; a model that needs longer is
# effectively down and the chain should move on (3.7-flash hit 60 s on Oct 3).
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S", "35"))
# No Gemini at all: canned verdicts so the robot/voice/app can be built without quota.
GEMINI_MOCK = os.getenv("GEMINI_MOCK", "0") == "1"
MOCK_CASE = os.getenv("MOCK_CASE", "cycle")      # cycle | wrong_rule | correct | arithmetic
# Gemini 3 "thinks" before answering; high levels take 30 s+ on math. Keep
# Flash fast and let Pro think a bit more when it's called in as the fallback.
FLASH_THINKING = os.getenv("FLASH_THINKING", "low")      # minimal | low | medium | high
PRO_THINKING = os.getenv("PRO_THINKING", "medium")
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))

# Policy
SPEAK_THRESHOLD = float(os.getenv("SPEAK_THRESHOLD", "0.7"))
COOLDOWN_S = float(os.getenv("COOLDOWN_S", "20"))
STUCK_AFTER_S = float(os.getenv("STUCK_AFTER_S", "60"))
# Said once when the board hasn't changed for STUCK_AFTER_S. Offers a look,
# gives nothing away. Empty string = face only, no speech.
STUCK_PROMPT = os.getenv("STUCK_PROMPT", "Take your time. Ask me to check whenever you're ready.")

# Camera / vision
# "auto" picks the external USB webcam (laptops' built-in cameras enumerate first
# and often sit behind a privacy shutter, delivering black frames). Or a number.
CAMERA_INDEX = os.getenv("CAMERA_INDEX", "auto")
CAMERA_NAME = os.getenv("CAMERA_NAME", "")        # optional substring of the device name, e.g. "WEB CAM"
CAMERA_W = int(os.getenv("CAMERA_W", "1920"))
CAMERA_H = int(os.getenv("CAMERA_H", "1080"))
# Auto-check when the board changed and then held still this long. 3 s fired on
# every pause while writing (12 checks in two minutes on the first live test).
STILL_S = float(os.getenv("STILL_S", "5"))
# ...and never more often than this. Quota guard; on-demand checks bypass it.
MIN_CHECK_INTERVAL_S = float(os.getenv("MIN_CHECK_INTERVAL_S", "5"))
# Fraction of pixels that must differ from the last checked board to re-check.
# 0.0001 catches erasing a single character; raise it if lighting flicker
# (projector, window) causes checks with nothing new on the board.
CHANGE_THR = float(os.getenv("CHANGE_THR", "0.0001"))
# Size of the flattened board image. Handwriting is small relative to the frame
# (the first real capture had "1+1=2" ~150 px wide in a 1280 px frame), so keep
# resolution: Gemini reads detail per 768-px tile and the extra tokens are cheap.
BOARD_W, BOARD_H = 1600, 900
# Find the whiteboard's rectangle and deskew it. Turn off (or press `b` in the
# preview) if the detector keeps locking onto a window, door or monitor instead.
BOARD_DETECT = os.getenv("BOARD_DETECT", "1") == "1"
JPEG_MAX_W = int(os.getenv("JPEG_MAX_W", "1600"))

# Voice (ElevenLabs). Speech plays on the laptop speakers, the student is heard
# through the laptop's own mic; the ESP32 only gets the face and mouth levels.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# "Jessica - Playful, Bright, Warm": a premade voice, so any API key can use it.
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9")
TTS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")     # fastest, cheapest per character
STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")
STT_LANGUAGE = os.getenv("ELEVENLABS_STT_LANGUAGE", "en")          # empty = auto-detect
# Mic: part of the device name ("Digital Microphone"). Empty = the laptop's
# built-in mic. Webcam mics are never picked, even if they're the system default.
MIC_NAME = os.getenv("MIC_NAME", "")
SPEAKER_NAME = os.getenv("SPEAKER_NAME", "")      # empty = the system's default output
LISTEN_MAX_S = float(os.getenv("LISTEN_MAX_S", "15"))        # longest question
LISTEN_SILENCE_S = float(os.getenv("LISTEN_SILENCE_S", "1.0"))  # this much quiet after speaking = done
LISTEN_START_S = float(os.getenv("LISTEN_START_S", "6"))     # give up if nobody speaks this long
# Spoken lines are cached here (gitignored), so repeats cost no credits and play instantly.
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", ROOT / "brain" / "tts_cache"))

# Every analysed frame + Gemini reply is saved here (gitignored). Feeds the
# demo cache at H18 and gives us real test fixtures.
RECORD_DIR = Path(os.getenv("RECORD_DIR", ROOT / "brain" / "recordings"))
# Promoted recordings (committed). Used when Gemini fails, or first if PREFER_CACHE=1.
CACHE_DIR = Path(os.getenv("CACHE_DIR", ROOT / "brain" / "demo_cache"))
PREFER_CACHE = os.getenv("PREFER_CACHE", "0") == "1"

# Server
HOST = os.getenv("BRAIN_HOST", "0.0.0.0")
PORT = int(os.getenv("BRAIN_PORT", "8000"))
