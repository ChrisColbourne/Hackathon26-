"""Render a fake whiteboard photo so the brain can be tested without a camera.

  python -m brain.tools.make_test_board out.jpg [--case quotient|correct|sign|algebra]

The text is printed, not handwritten, so this only proves the pipeline. Real
handwriting tests need the webcam.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

CASES = {
    # quotient rule used on a product -> wrong_rule on line 2
    "quotient": [
        "d/dx [ x^2 sin(x) ]",
        "= ( 2x sin(x) - x^2 cos(x) ) / sin^2(x)",
    ],
    # product rule done right -> nothing to flag
    "correct": [
        "d/dx [ x^2 sin(x) ]",
        "= 2x sin(x) + x^2 cos(x)",
    ],
    # quotient rule where it belongs, but numerator order flipped -> misapplied
    "sign": [
        "d/dx [ sin(x) / x ]",
        "= ( sin(x) - x cos(x) ) / x^2",
    ],
    # moved the 3 across without flipping the sign -> arithmetic
    "algebra": [
        "2x + 3 = 7",
        "2x = 10",
        "x = 5",
    ],
}


def render(lines: list[str], w: int = 1600, h: int = 900) -> np.ndarray:
    img = np.full((h, w, 3), 245, np.uint8)
    cv2.rectangle(img, (40, 40), (w - 40, h - 40), (90, 90, 90), 6)  # board frame
    y = 200
    for ln in lines:
        cv2.putText(img, ln, (120, y), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (30, 30, 120), 4, cv2.LINE_AA)
        y += 150
    noise = np.random.default_rng(0).normal(0, 4, img.shape).astype(np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    p.add_argument("--case", choices=sorted(CASES), default="quotient")
    a = p.parse_args(argv)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(a.out), render(CASES[a.case]))
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
