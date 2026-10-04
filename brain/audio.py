"""Laptop mic in, laptop speakers out, through PipeWire/PulseAudio's own tools.

  record_utterance()  the student's question from the laptop's built-in mic,
                      ending on ~1 s of quiet after they speak (tap-to-talk)
  Player              plays 16-bit PCM on the speakers and reports a mouth
                      level for each ~1/15 s as it is heard (lip sync)

parecord/pacat (pulseaudio-utils, preinstalled on Ubuntu) pick a mic by its
exact PipeWire name, which is how the webcam mic is kept out even when it's
the system default. No Python audio library or PortAudio needed.
"""

from __future__ import annotations

import io
import json
import logging
import math
import shutil
import subprocess
import threading
import time
import wave
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np

from . import config

log = logging.getLogger("audio")

MIC_RATE = 16000          # what speech-to-text wants; PipeWire resamples the mic for us
FRAME_S = 0.03            # VAD frame
SPEECH_MIN_RMS = 250      # int16 RMS. Laptop DMIC room noise measured ~40 (Oct 4), speech is 500+


@dataclass
class Mic:
    name: str             # PipeWire source name, passed to parecord
    description: str


def available() -> bool:
    return bool(shutil.which("parecord") and shutil.which("pacat") and shutil.which("pactl"))


def list_mics() -> list[dict]:
    """Every capture source except speaker monitors, with its PipeWire properties."""
    out = subprocess.run(["pactl", "--format=json", "list", "sources"], capture_output=True, text=True, timeout=5)
    sources = json.loads(out.stdout or "[]")
    return [s for s in sources if s.get("monitor_of_sink") in (None, "", "n/a")]


def is_webcam(src: dict) -> bool:
    props = src.get("properties", {})
    text = f"{src.get('name', '')} {src.get('description', '')} {props.get('device.product.name', '')}".lower()
    return props.get("device.form_factor") == "webcam" or "cam" in text


def pick_mic(name_hint: str = config.MIC_NAME) -> Mic:
    """The laptop's own mic. A name hint wins; otherwise prefer the built-in
    digital mic array, then any internal mic. Never a webcam."""
    mics = [s for s in list_mics() if not is_webcam(s)]
    if not mics:
        raise RuntimeError("no microphone found besides the webcam's")
    if name_hint:
        for s in mics:
            if name_hint.lower() in f"{s['name']} {s.get('description', '')}".lower():
                return Mic(s["name"], s.get("description", s["name"]))
        log.warning("no mic named like %r; using the built-in one", name_hint)

    def score(s: dict) -> int:
        d = f"{s['name']} {s.get('description', '')}".lower()
        props = s.get("properties", {})
        return (("digital microphone" in d or "dmic" in d) * 4 + (props.get("device.form_factor") == "internal") * 2
                + ("headphone" not in d and "headset" not in d))   # the jack mic is silent unless plugged in
    best = max(mics, key=score)
    return Mic(best["name"], best.get("description", best["name"]))


def to_wav(pcm: bytes, rate: int = MIC_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def rms(block: bytes) -> float:
    a = np.frombuffer(block, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


def record_utterance(mic: Mic, stop: threading.Event | None = None, max_s: float = config.LISTEN_MAX_S,
                     silence_s: float = config.LISTEN_SILENCE_S, start_s: float = config.LISTEN_START_S,
                     on_level: Callable[[float], None] | None = None) -> tuple[bytes, bool]:
    """Record until the student has spoken and then gone quiet for `silence_s`,
    or `stop` is set (second tap), or `max_s`. Returns (pcm16 mono 16 kHz, heard_speech).

    Speech = louder than 4x the room noise of the first few frames (and at least
    SPEECH_MIN_RMS), for 3 frames in a row. Quiet = under 70% of that."""
    frame_bytes = int(MIC_RATE * FRAME_S) * 2
    proc = subprocess.Popen(
        ["parecord", "--raw", f"--device={mic.name}", "--format=s16le", f"--rate={MIC_RATE}", "--channels=1",
         "--latency-msec=30", "--client-name=otter-tutor", "--stream-name=student"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks: list[bytes] = []
    floor: list[float] = []
    thr, loud_run, quiet_since, heard = None, 0, None, False
    t0 = time.monotonic()
    try:
        while True:
            block = proc.stdout.read(frame_bytes)                     # type: ignore[union-attr]
            if not block:
                raise RuntimeError(f"mic {mic.description!r} stopped delivering audio")
            chunks.append(block)
            level = rms(block)
            if on_level:
                on_level(level)
            now = time.monotonic() - t0
            if thr is None:
                if now > 0.06:                                       # skip the first frames' startup click
                    floor.append(level)
                if len(floor) >= 6:
                    thr = max(SPEECH_MIN_RMS, 4 * float(np.median(floor)))
                    log.debug("mic noise floor %.0f -> speech threshold %.0f", np.median(floor), thr)
                continue
            if not heard:
                loud_run = loud_run + 1 if level > thr else 0
                if loud_run >= 3:
                    heard = True
                elif now > start_s:
                    break                                            # nobody spoke
            else:
                if level < 0.7 * thr:
                    quiet_since = quiet_since if quiet_since is not None else now
                    if now - quiet_since >= silence_s:
                        break
                else:
                    quiet_since = None
            if now >= max_s or (stop is not None and stop.is_set()):
                break
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
    return b"".join(chunks), heard


class Player:
    """Plays mono 16-bit PCM through pacat at real-time pace and calls
    on_level(0..1) for each block at the moment it should be audible."""

    BLOCK_S = 1 / 15          # mouth updates ~15x/s, matching the firmware's animation
    LEAD_S = 0.15             # how far ahead of the speaker we let the writes run
    OUT_LATENCY_S = 0.06      # pacat --latency-msec below

    def __init__(self, rate: int, on_level: Callable[[float], None], sink: str = config.SPEAKER_NAME):
        self.rate, self.on_level, self.sink = rate, on_level, sink

    def play(self, chunks: Iterable[bytes]) -> None:
        cmd = ["pacat", "--playback", "--raw", "--format=s16le", f"--rate={self.rate}", "--channels=1",
               f"--latency-msec={int(self.OUT_LATENCY_S * 1000)}", "--client-name=otter-tutor",
               "--stream-name=otter-voice"]
        if self.sink:
            cmd.append(f"--device={self.sink}")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        bps = self.rate * 2
        block_bytes = int(self.rate * self.BLOCK_S) * 2
        levels: list[float] = []
        written, t_start, shown, pending = 0, None, -1, b""

        def show_due() -> None:
            nonlocal shown
            if t_start is None:
                return
            due = math.floor((time.monotonic() - t_start - self.OUT_LATENCY_S) / self.BLOCK_S)
            due = min(due, len(levels) - 1)
            if due > shown:
                shown = due
                self.on_level(levels[due])

        def write(block: bytes) -> None:
            nonlocal written, t_start
            if t_start is None:
                t_start = time.monotonic()
            proc.stdin.write(block)                                  # type: ignore[union-attr]
            written += len(block)
            levels.append(min(1.0, math.sqrt(rms(block) / 32768 * 8)))   # quiet speech ~0.4, loud ~1
            while (ahead := written / bps - (time.monotonic() - t_start)) > self.LEAD_S:
                show_due()
                time.sleep(min(self.BLOCK_S / 2, ahead - self.LEAD_S + 0.005))
            show_due()

        try:
            for chunk in chunks:
                pending += chunk
                while len(pending) >= block_bytes:
                    write(pending[:block_bytes])
                    pending = pending[block_bytes:]
            if len(pending) >= 2:
                write(pending[: len(pending) // 2 * 2])
            proc.stdin.close()                                       # type: ignore[union-attr]
            while t_start is not None and time.monotonic() - t_start < written / bps + self.OUT_LATENCY_S:
                show_due()
                time.sleep(self.BLOCK_S / 2)
            proc.wait(timeout=2)
        except BrokenPipeError:
            log.warning("speaker output closed early")
        finally:
            if proc.poll() is None:
                proc.kill()
