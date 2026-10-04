"""speak() / listen(): the otter's voice and ears, on the laptop.

    voice = Voice(on_mouth=robot_mouth_callback, on_state=face_callback)
    voice.speak(text, mood)        # blocking; call via asyncio.to_thread
    voice.listen() -> str          # blocking; tap-to-talk, returns the transcript
    voice.stop_listening()         # second tap: stop recording now

speak() streams ElevenLabs TTS (raw PCM) to the laptop speakers and sends the
real loudness of each ~1/15 s to on_mouth, so the LCD otter lip-syncs. Lines
are cached on disk: repeats ("Yes, that all checks out.") are free and instant.
listen() records the laptop's built-in mic (never the webcam's) until the
student stops talking, then transcribes with ElevenLabs Scribe.

Without ELEVENLABS_API_KEY, speak() prints the line and fakes the mouth, and
listen() returns "" (there's nothing to transcribe with).
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections.abc import Callable, Iterator

from . import audio, config
from .schemas import Mood

log = logging.getLogger("voice")

TTS_RATE = 24000          # pcm_24000: the best raw PCM the free tier allows (44.1 kHz needs Pro)

# Warmer for praise, calmer when the student is stuck.
MOOD_SETTINGS: dict[str, dict[str, float]] = {
    "happy": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.6},
    "confused": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.3},
    "thinking": {"stability": 0.7, "similarity_boost": 0.8, "style": 0.2},
}
DEFAULT_SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.4}


class Voice:
    def __init__(self, on_mouth: Callable[[float], None] | None = None, on_state: Callable[[Mood], None] | None = None):
        self.on_mouth = on_mouth or (lambda level: None)
        self.on_state = on_state or (lambda state: None)
        self._client = None
        self._speak_lock = threading.Lock()          # one line at a time
        self._stop_listen = threading.Event()
        self.listening = False
        if config.ELEVENLABS_API_KEY:
            try:
                from elevenlabs.client import ElevenLabs

                self._client = ElevenLabs(api_key=config.ELEVENLABS_API_KEY)
            except Exception as e:  # SDK missing/broken -> mock
                log.warning("ElevenLabs unavailable (%s); using mock voice", e)
        self.audio_ok = audio.available()
        if not self.audio_ok:
            log.warning("parecord/pacat not found (sudo apt install pulseaudio-utils): no mic or speakers")
        self.mic: audio.Mic | None = None
        if self.audio_ok:
            try:
                self.mic = audio.pick_mic()
                log.info("mic: %s", self.mic.description)
            except Exception as e:
                log.warning("no usable mic: %s", e)

    @property
    def live(self) -> bool:
        return self._client is not None

    # ---- speaking ----------------------------------------------------------
    def speak(self, text: str, mood: Mood = "talking") -> None:
        if not text.strip():
            return
        with self._speak_lock:
            self.on_state("talking")
            try:
                if self._client is not None and self.audio_ok:
                    self._speak_elevenlabs(text, mood)
                else:
                    self._speak_mock(text)
            except Exception as e:
                log.warning("TTS failed (%s); falling back to mock", e)
                self._speak_mock(text)
            finally:
                self.on_mouth(0.0)
                self.on_state("idle")

    def _speak_elevenlabs(self, text: str, mood: Mood) -> None:
        settings = MOOD_SETTINGS.get(mood, DEFAULT_SETTINGS)
        key = hashlib.sha1(f"{config.VOICE_ID}|{config.TTS_MODEL}|{sorted(settings.items())}|{text}".encode())
        cached = config.TTS_CACHE_DIR / f"{key.hexdigest()}.pcm"
        player = audio.Player(TTS_RATE, self.on_mouth)
        if cached.is_file():
            player.play([cached.read_bytes()])
            return
        got: list[bytes] = []
        complete = False

        def stream() -> Iterator[bytes]:
            nonlocal complete
            from elevenlabs import VoiceSettings

            for chunk in self._client.text_to_speech.stream(  # type: ignore[union-attr]
                voice_id=config.VOICE_ID, text=text, model_id=config.TTS_MODEL,
                output_format=f"pcm_{TTS_RATE}", voice_settings=VoiceSettings(**settings),
            ):
                if isinstance(chunk, bytes) and chunk:
                    got.append(chunk)
                    yield chunk
            complete = True

        player.play(stream())                    # starts playing as soon as the first audio arrives
        if not complete:                         # cut short: don't cache half a line
            return
        try:
            config.TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(b"".join(got))
        except OSError as e:
            log.debug("tts cache write failed: %s", e)

    def _speak_mock(self, text: str) -> None:
        print(f'\n   🦦 OTTER SAYS: "{text}"\n', flush=True)
        start, duration = time.monotonic(), min(6.0, 0.6 + len(text) * 0.055)
        while (t := time.monotonic() - start) < duration:
            self.on_mouth(0.5 + 0.5 * abs(math.sin(t * 9.0)))
            time.sleep(1 / 15)

    # ---- listening ---------------------------------------------------------
    def listen(self) -> str:
        """Record the student from the laptop mic until they stop talking (or
        stop_listening()), then transcribe. "" if nothing was said or heard."""
        if self.mic is None:
            log.warning("listen(): no microphone")
            return ""
        self._stop_listen.clear()
        self.listening = True
        try:
            pcm, heard = audio.record_utterance(self.mic, self._stop_listen)
        finally:
            self.listening = False
        if not heard:
            log.info("heard nothing in %.1fs of listening", len(pcm) / 2 / audio.MIC_RATE)
            return ""
        return self.transcribe(pcm)

    def transcribe(self, pcm: bytes) -> str:
        """16 kHz mono 16-bit PCM -> text, via ElevenLabs Scribe."""
        secs = len(pcm) / 2 / audio.MIC_RATE
        if self._client is None:
            log.warning("recorded %.1fs, but transcribing needs ELEVENLABS_API_KEY in .env", secs)
            return ""
        t0 = time.monotonic()
        res = self._client.speech_to_text.convert(
            model_id=config.STT_MODEL,
            file=("question.wav", audio.to_wav(pcm), "audio/wav"),
            language_code=config.STT_LANGUAGE or None,
            tag_audio_events=False,                  # no "(laughs)" in the transcript
        )
        text = (getattr(res, "text", "") or "").strip()
        log.info("transcribed %.1fs of speech in %.1fs", secs, time.monotonic() - t0)
        return text

    def stop_listening(self) -> None:
        self._stop_listen.set()
