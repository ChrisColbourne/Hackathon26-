"""Check the otter's ears and voice, one step at a time.

  python -m brain.tools.voice_test

1. Lists the mics and the one the brain will use (webcam mics are skipped).
2. Records you on it until you stop talking, with a live level meter.
3. Plays a short tone on the laptop speakers.
4. With ELEVENLABS_API_KEY in .env: transcribes what you said, then the otter
   says it back in its ElevenLabs voice (a few characters of credit).
Needs no Gemini quota and no robot.
"""

from __future__ import annotations

import logging
import math
import sys

import numpy as np

from .. import audio, config
from ..voice import TTS_RATE, Voice


def meter(level: float) -> None:
    bars = max(0, min(40, int((math.log10(max(level, 1)) - 1) * 13)))   # room noise ~8 bars, speech 30+
    sys.stdout.write("\r   level |" + "#" * bars + " " * (40 - bars) + f"| {level:6.0f}")
    sys.stdout.flush()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname).1s %(name)s: %(message)s")
    if not audio.available():
        sys.exit("parecord/pacat/pactl missing: sudo apt install pulseaudio-utils")

    print("\n1) Microphones")
    for s in audio.list_mics():
        print(f"   {'(webcam, skipped) ' if audio.is_webcam(s) else '                  '}{s.get('description')}")
    mic = audio.pick_mic()
    print(f"   -> the brain listens on: {mic.description}"
          + (f"   (MIC_NAME={config.MIC_NAME!r})" if config.MIC_NAME else ""))

    print("\n2) Recording")
    input("   Press Enter, then say something like \"is my second line right?\" ")
    pcm, heard = audio.record_utterance(mic, on_level=meter)
    a = np.frombuffer(pcm, dtype=np.int16)
    print(f"\n   {len(a) / audio.MIC_RATE:.1f}s recorded, peak {int(np.abs(a).max()) if a.size else 0} / 32767, "
          f"speech {'DETECTED' if heard else 'NOT detected (too quiet, or wrong mic?)'}")

    print("\n3) Speakers")
    t = np.arange(int(TTS_RATE * 0.6)) / TTS_RATE
    tone = (np.sin(2 * math.pi * 660 * t) * np.minimum(1, (0.6 - t) * 20) * 6000).astype(np.int16)
    audio.Player(TTS_RATE, lambda level: None).play([tone.tobytes()])
    print("   played a short beep" + (f" on {config.SPEAKER_NAME}" if config.SPEAKER_NAME else " on the default output"))

    print("\n4) ElevenLabs")
    voice = Voice()
    if not voice.live:
        print("   skipped: put ELEVENLABS_API_KEY in .env to test transcription and the voice")
        return
    if not heard:
        print("   skipped transcription: no speech was detected in step 2")
        text = ""
    else:
        text = voice.transcribe(pcm)
        print(f'   heard: "{text}"')
    line = f"You said: {text}" if text else "Hi! I'm your otter tutor. Write a problem on the board and I'll help."
    print(f'   otter says: "{line}"')
    voice.speak(line, "happy")
    print("   done. If you heard the voice, speech in and out both work.\n")


if __name__ == "__main__":
    main()
