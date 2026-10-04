"""speak() / listen() — Person C owns this file. This is a working stub.

Interface the brain relies on:
    voice = Voice(on_mouth=robot_mouth_callback)
    voice.speak(text, mood)        # blocking; call via asyncio.to_thread
    voice.listen() -> str          # blocking push-to-talk; returns transcript

With ELEVENLABS_API_KEY set, speak() streams ElevenLabs TTS to the laptop
speakers. Without it, it prints the line and fakes a mouth envelope so the
otter still animates during mock runs.

C's TODOs: real amplitude -> on_mouth levels (~15/s), per-mood voice settings,
listen() via ElevenLabs STT, pre-recorded fallback lines per mood.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Callable

from .schemas import Mood

log = logging.getLogger("voice")

VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel"; pick an otter-ish one
TTS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")

# Warmer for praise, calmer when the student is stuck. C tunes these.
MOOD_SETTINGS: dict[str, dict[str, float]] = {
    "happy": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.6},
    "confused": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.3},
    "thinking": {"stability": 0.7, "similarity_boost": 0.8, "style": 0.2},
}


class Voice:
    def __init__(self, on_mouth: Callable[[float], None] | None = None, on_state: Callable[[Mood], None] | None = None):
        self.on_mouth = on_mouth or (lambda level: None)
        self.on_state = on_state or (lambda state: None)
        self._client = None
        key = os.getenv("ELEVENLABS_API_KEY")
        if key:
            try:
                from elevenlabs.client import ElevenLabs

                self._client = ElevenLabs(api_key=key)
            except Exception as e:  # SDK missing/broken -> mock
                log.warning("ElevenLabs unavailable (%s); using mock voice", e)

    @property
    def live(self) -> bool:
        return self._client is not None

    def speak(self, text: str, mood: Mood = "talking") -> None:
        if not text.strip():
            return
        self.on_state("talking")
        try:
            if self._client is not None:
                self._speak_elevenlabs(text, mood)
            else:
                self._speak_mock(text)
        except Exception as e:
            log.warning("TTS failed (%s); falling back to mock", e)
            self._speak_mock(text)
        finally:
            self.on_mouth(0.0)
            self.on_state("idle")

    def listen(self, max_s: float = 8.0) -> str:
        """Push-to-talk. Stub returns '' — C wires the mic + ElevenLabs STT."""
        log.info("listen() not implemented yet (Person C)")
        return ""

    # ---- backends --------------------------------------------------------
    def _speak_elevenlabs(self, text: str, mood: Mood) -> None:
        from elevenlabs import play

        audio = self._client.text_to_speech.convert(  # type: ignore[union-attr]
            voice_id=VOICE_ID,
            text=text,
            model_id=TTS_MODEL,
            output_format="mp3_44100_128",
            voice_settings=MOOD_SETTINGS.get(mood, MOOD_SETTINGS["confused"]),
        )
        data = b"".join(audio) if not isinstance(audio, (bytes, bytearray)) else bytes(audio)
        # TODO(C): decode + measure RMS ~15x/s -> self.on_mouth(level) while playing.
        self._fake_mouth(len(text) * 0.055, start=time.monotonic())
        play(data)  # needs ffplay or mpv on PATH

    def _speak_mock(self, text: str) -> None:
        print(f'\n   🦦 OTTER SAYS: "{text}"\n')
        self._fake_mouth(min(6.0, 0.6 + len(text) * 0.055), start=time.monotonic(), block=True)

    def _fake_mouth(self, duration: float, start: float, block: bool = False) -> None:
        """Sine-ish mouth envelope so the LCD otter talks even in mock mode."""
        if not block:
            return
        while (t := time.monotonic() - start) < duration:
            self.on_mouth(0.5 + 0.5 * abs(math.sin(t * 9.0)))
            time.sleep(1 / 15)
