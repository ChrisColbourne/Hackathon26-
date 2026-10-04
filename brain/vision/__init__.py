"""Whiteboard preprocessing. Prefers the C++ module, falls back to Python.

    from brain.vision import prepare, change_score, enhance, BACKEND
"""

try:
    from . import board_prep as _impl  # compiled by build.sh
except ImportError:  # not built (yet), or ABI mismatch
    from . import vision_py as _impl

BACKEND: str = _impl.BACKEND
find_board = _impl.find_board
warp = _impl.warp
enhance = _impl.enhance
change_score = _impl.change_score
prepare = _impl.prepare

__all__ = ["BACKEND", "find_board", "warp", "enhance", "change_score", "prepare"]
