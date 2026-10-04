"""Pure-Python fallback for board_prep.cpp. Same functions, same semantics.

Used automatically when the compiled module isn't present (see __init__.py),
so the brain keeps working even if the C++ build breaks at 3 a.m.
"""

from __future__ import annotations

import cv2
import numpy as np

BACKEND = "python"
Quad = list[tuple[float, float]]


def _order_corners(pts: np.ndarray) -> Quad:
    pts = pts.reshape(4, 2).astype(float)
    s, d = pts.sum(1), pts[:, 1] - pts[:, 0]
    tl, br = pts[s.argmin()], pts[s.argmax()]
    tr, bl = pts[d.argmin()], pts[d.argmax()]
    return [tuple(tl), tuple(tr), tuple(br), tuple(bl)]


def find_board(frame: np.ndarray, min_area_frac: float = 0.2) -> Quad | None:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), None, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = min_area_frac * frame.shape[0] * frame.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        if cv2.contourArea(c) < min_area:
            break
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return _order_corners(approx)
    return None


def warp(frame: np.ndarray, quad: Quad, w: int = 1280, h: int = 720) -> np.ndarray:
    src = np.array(quad, dtype=np.float32)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def enhance(flat: np.ndarray) -> np.ndarray:
    if flat.ndim != 3:
        return flat.copy()
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2Lab)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_Lab2BGR)


def change_score(a: np.ndarray, b: np.ndarray, thresh: int = 30) -> float:
    def prep(img: np.ndarray) -> np.ndarray:
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        g = cv2.resize(g, (320, 180), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(g, (5, 5), 0)

    d = cv2.absdiff(prep(a), prep(b))
    _, d = cv2.threshold(d, thresh, 255, cv2.THRESH_BINARY)
    return float(cv2.countNonZero(d)) / d.size


def prepare(frame: np.ndarray, w: int = 1280, h: int = 720, min_area_frac: float = 0.2) -> tuple[np.ndarray, bool]:
    quad = find_board(frame, min_area_frac)
    if quad is not None:
        return warp(frame, quad, w, h), True
    s = min(1.0, w / frame.shape[1])
    return cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), False
