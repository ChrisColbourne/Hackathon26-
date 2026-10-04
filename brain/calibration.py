"""Map a Gemini bounding box to laser pan/tilt angles.

Person A runs calibration mode: the brain sends the laser to each board corner,
A nudges pan/tilt until the dot sits on the corner, and we save the four pairs.
After that, a box centre (0..1000 in the flat board image) becomes angles by
bilinear interpolation between the corners. Order: TL, TR, BR, BL, matching
brain.vision's corner order so the warped image and the laser agree.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("calibration.json")


@dataclass
class Corner:
    pan: float
    tilt: float


@dataclass
class Calibration:
    tl: Corner
    tr: Corner
    br: Corner
    bl: Corner

    @classmethod
    def default(cls) -> "Calibration":
        # Sensible guess for a board ~1.5 m away; replace via calibration mode.
        return cls(Corner(-25, 10), Corner(25, 10), Corner(25, -10), Corner(-25, -10))

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Calibration":
        if not path.exists():
            return cls.default()
        d = json.loads(path.read_text())
        return cls(**{k: Corner(**v) for k, v in d.items()})

    def save(self, path: Path = DEFAULT_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))     # asdict recurses into the Corners

    def angles_at(self, u: float, v: float) -> tuple[float, float]:
        """u, v in 0..1 across the board (left->right, top->bottom)."""
        u, v = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)
        w_tl, w_tr, w_br, w_bl = (1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v
        pan = w_tl * self.tl.pan + w_tr * self.tr.pan + w_br * self.br.pan + w_bl * self.bl.pan
        tilt = w_tl * self.tl.tilt + w_tr * self.tr.tilt + w_br * self.br.tilt + w_bl * self.bl.tilt
        return round(pan, 1), round(tilt, 1)

    def box_to_angles(self, box: list[int]) -> tuple[float, float]:
        """Gemini box [ymin, xmin, ymax, xmax] on 0..1000 -> (pan, tilt) at its centre."""
        ymin, xmin, ymax, xmax = box
        return self.angles_at((xmin + xmax) / 2000.0, (ymin + ymax) / 2000.0)


CORNER_ORDER = ("tl", "tr", "br", "bl")
