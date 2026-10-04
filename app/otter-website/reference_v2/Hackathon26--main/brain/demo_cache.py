"""Cached Gemini replies for the demo problem.

Venue Wi-Fi dies, Gemini has a slow minute, the free tier rate-limits us:
the demo must not stop. Every analysed frame is saved to brain/recordings/;
`python -m brain.tools.cache_add <stamp>` promotes a good one into
brain/demo_cache/ (committed). At runtime the cache is consulted:

  - as a FALLBACK when both Gemini models fail (default), or
  - FIRST, if PREFER_CACHE=1, for a rehearsed demo where the board looks the
    same every run.

A hit means the current flat board image differs from a cached one by less
than `max_change` (fraction of pixels, see vision.change_score).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import config
from .schemas import BoardAnalysis
from .vision import change_score

log = logging.getLogger("cache")


@dataclass
class _Entry:
    name: str
    gray: np.ndarray
    analysis: BoardAnalysis


class DemoCache:
    def __init__(self, directory: Path = config.CACHE_DIR, max_change: float = 0.03):
        self.dir, self.max_change = directory, max_change
        self.entries: list[_Entry] = []
        self.reload()

    def reload(self) -> None:
        self.entries.clear()
        if not self.dir.is_dir():
            return
        for js in sorted(self.dir.glob("*.json")):
            jpg = js.with_suffix(".jpg")
            if not jpg.exists():
                continue
            img = cv2.imread(str(jpg), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            try:
                self.entries.append(_Entry(js.stem, img, BoardAnalysis.model_validate_json(js.read_text())))
            except Exception as e:
                log.warning("bad cache entry %s: %s", js.name, e)
        if self.entries:
            log.info("demo cache: %d entries from %s", len(self.entries), self.dir)

    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, jpeg: bytes) -> BoardAnalysis | None:
        if not self.entries:
            return None
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        best = min(self.entries, key=lambda e: change_score(e.gray, img))
        score = change_score(best.gray, img)
        if score <= self.max_change:
            log.info("demo cache HIT %s (change %.3f)", best.name, score)
            return best.analysis.model_copy(deep=True)
        log.debug("demo cache miss (closest %s at %.3f)", best.name, score)
        return None


def add_from_recording(stamp: str, src: Path = config.RECORD_DIR, dest: Path = config.CACHE_DIR,
                       name: str | None = None) -> Path:
    """Copy recordings/<stamp>.{jpg,json} into the cache, optionally renamed."""
    js, jpg = src / f"{stamp}.json", src / f"{stamp}.jpg"
    if not js.exists() or not jpg.exists():
        raise FileNotFoundError(f"no recording {stamp} in {src}")
    dest.mkdir(parents=True, exist_ok=True)
    base = name or stamp
    shutil.copy(js, dest / f"{base}.json")
    shutil.copy(jpg, dest / f"{base}.jpg")
    return dest / f"{base}.json"
