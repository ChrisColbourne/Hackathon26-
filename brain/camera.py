"""Webcam capture and the "is the board worth analysing yet?" detector.

Two signals, both from brain.vision.change_score:
  motion   = change between consecutive frames  (hand moving, ink appearing)
  changed  = change since the last frame we sent to Gemini

We trigger when `changed` is big enough AND `motion` has been ~zero for
`still_s` seconds AND at least `min_interval_s` passed since the last check.
That way we never read a half-written line, never pay for a Gemini call when
nothing new is on the board, and a student who pauses every few seconds while
writing doesn't drain the daily quota.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import config
from .vision import change_score, prepare

log = logging.getLogger("camera")

DARK_MEAN = 20.0   # mean pixel value below this = black frame (shutter, lens cap, wrong camera)


def is_dark(frame: np.ndarray) -> bool:
    return float(frame.mean()) < DARK_MEAN


def list_cameras() -> list[tuple[int, str]]:
    """(index, name) for every /dev/video* node, from sysfs. Linux only."""
    out = []
    for p in sorted(Path("/sys/class/video4linux").glob("video*"), key=lambda p: int(p.name[5:])):
        try:
            name = (p / "name").read_text().strip()
        except OSError:
            name = "?"
        out.append((int(p.name[5:]), name))
    return out


def _probe_brightness(index: int, warm_s: float = 0.8) -> float | None:
    """Mean brightness after a short auto-exposure warm-up, or None if it won't open."""
    try:  # metadata nodes (video1, video3, ...) can't capture; don't let OpenCV shout about it
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        frame, t0 = None, time.monotonic()
        while time.monotonic() - t0 < warm_s:
            ok, f = cap.read()
            if ok:
                frame = f
        return None if frame is None else float(frame.mean())
    finally:
        cap.release()


def resolve_camera(spec: str = config.CAMERA_INDEX, name_hint: str = config.CAMERA_NAME) -> tuple[int, str]:
    """Turn CAMERA_INDEX into (index, device name).

    A number is used as-is. "auto" prefers a device whose name contains
    CAMERA_NAME; otherwise the highest-numbered device that delivers a
    non-black frame (external USB webcams enumerate after the built-in one).
    Each node is opened for under a second, so expect ~2-3 s of startup.
    """
    cams = list_cameras()
    names = dict(cams)
    if spec.strip().lower() != "auto":
        i = int(spec)
        return i, names.get(i, "?")
    if name_hint:
        for i, n in cams:
            if name_hint.lower() in n.lower() and _probe_brightness(i) is not None:
                return i, n
        log.warning("no openable camera named like %r; falling back to auto", name_hint)
    fallback: tuple[int, str] | None = None
    for i, n in reversed(cams):               # metadata nodes fail to open and are skipped
        mean = _probe_brightness(i)
        if mean is None:
            continue
        if mean >= DARK_MEAN:
            return i, n
        log.warning("camera #%d (%s) delivers black frames (mean %.1f); skipping", i, n, mean)
        fallback = fallback or (i, n)
    return fallback or (0, names.get(0, "?"))


def flatten(frame: np.ndarray, detect: bool | None = None) -> tuple[np.ndarray, bool]:
    """The board image we analyse: crop + deskew when detection is on, else just
    the frame shrunk to BOARD_W. Returns (image, board_found)."""
    if config.BOARD_DETECT if detect is None else detect:
        return prepare(frame, config.BOARD_W, config.BOARD_H)
    s = min(1.0, config.BOARD_W / frame.shape[1])
    return cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), False


class Camera:
    """Thin wrapper over cv2.VideoCapture tuned for a 2K USB webcam on Linux."""

    def __init__(self, index: int = 0, width: int = 1920, height: int = 1080, fps: int = 15):
        self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        # MJPG is what lets UVC webcams deliver high resolution at a usable frame rate.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open camera index {index}")

    @property
    def size(self) -> tuple[int, int]:
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def read(self) -> np.ndarray | None:
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        self.cap.release()

    def __enter__(self) -> "Camera":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


@dataclass
class SettleDetector:
    still_s: float = 5.0          # how long the board must hold still
    motion_thr: float = 0.004     # above this between frames = someone is writing
    # Below this vs the last analysed board = nothing new. Measured on the real
    # board (Oct 3): static camera noise 0.00000, erasing one 'x' 0.00033,
    # '= 2' -> '= 8x' 0.0016. The old 0.015 missed every small edit.
    change_thr: float = 0.0001
    min_interval_s: float = 12.0  # at most one auto-check this often
    _prev: np.ndarray | None = field(default=None, repr=False)
    _last_analyzed: np.ndarray | None = field(default=None, repr=False)
    _still_since: float = field(default_factory=time.monotonic)
    _last_motion_at: float = field(default_factory=time.monotonic)
    _last_trigger: float = -1e9
    last_motion: float = 0.0
    last_changed: float = 1.0

    def update(self, flat: np.ndarray, now: float | None = None) -> bool:
        """Feed one prepared frame. Returns True when it's time to call Gemini."""
        now = time.monotonic() if now is None else now
        gray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY) if flat.ndim == 3 else flat

        self.last_motion = change_score(self._prev, gray) if self._prev is not None else 1.0
        self._prev = gray
        if self.last_motion > self.motion_thr:
            self._still_since = now
            self._last_motion_at = now

        self.last_changed = change_score(self._last_analyzed, gray) if self._last_analyzed is not None else 1.0
        settled = now - self._still_since >= self.still_s
        spaced = now - self._last_trigger >= self.min_interval_s
        if settled and spaced and self.last_changed > self.change_thr:
            self._last_analyzed = gray
            self._last_trigger = now
            return True
        return False

    def mark_analyzed(self, flat: np.ndarray) -> None:
        """Call after an on-demand check so auto mode doesn't re-check the same board."""
        self._last_analyzed = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY) if flat.ndim == 3 else flat
        self._last_trigger = time.monotonic()

    def idle_seconds(self, now: float | None = None) -> float:
        """Seconds since anything moved. Used for stuck detection (~60 s)."""
        return (time.monotonic() if now is None else now) - self._last_motion_at


def encode_jpeg(img: np.ndarray, max_w: int = 1280, quality: int = 85) -> bytes:
    """Shrink + JPEG for the Gemini call. ~1280 px wide keeps tokens and latency sane."""
    if img.shape[1] > max_w:
        s = max_w / img.shape[1]
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()
