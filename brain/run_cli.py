"""Dev loop for the brain, no server, no robot needed.

  python -m brain.run_cli --image path/to/board.jpg      # one check on a photo
  python -m brain.run_cli --camera [--show] [--index 0]  # live: auto-check when the board settles
      keys:  c = check now   b = toggle board detection   q / Esc = quit
      They work in the preview window (click it first to give it focus) OR typed
      in the terminal followed by Enter. Ctrl+C and closing the window also quit.
  add --mock to either: canned verdicts, no Gemini calls, zero quota (for A/C/D's testing)

Prints Gemini's reading, SymPy's opinion, and what the policy decided the otter
should say. Robot commands print as [MOCK ROBOT].
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import select
import sys
import time
from concurrent.futures import Future
from pathlib import Path

import cv2
import numpy as np

from . import config
from .camera import Camera, SettleDetector, encode_jpeg, flatten, is_dark, resolve_camera
from .gemini_brain import GeminiBrain
from .mock_brain import MockBrain
from .policy import Decision, Policy
from .robot import Robot
from .schemas import BoardAnalysis, StepStatus
from .threads import run_in_daemon
from .verifier import VerifierResult, verify
from .vision import BACKEND, enhance

log = logging.getLogger("cli")

Brain = GeminiBrain | MockBrain
WINDOW = "otter view  (c=check, b=toggle detect, q=quit)"


def quiet_qt_fonts() -> None:
    """opencv-python bundles a Qt whose font dir doesn't exist, so every preview
    frame logs 'QFontDatabase: Cannot find font directory'. Give it the system
    fonts: via QT_QPA_FONTDIR, and (belt and braces) by creating that dir with
    symlinks, which is what finally silenced it on Ubuntu 24.04."""
    system = next((d for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/usr/share/fonts")
                   if os.path.isdir(d)), None)
    if not system:
        return
    os.environ.setdefault("QT_QPA_FONTDIR", system)
    qt_fonts = Path(cv2.__file__).parent / "qt" / "fonts"
    if qt_fonts.parent.is_dir() and not qt_fonts.is_dir():
        try:
            qt_fonts.mkdir()
            for f in Path(system).glob("*.ttf"):
                (qt_fonts / f.name).symlink_to(f)
        except OSError:
            pass


def check(brain: Brain, policy: Policy, flat: np.ndarray, context: dict | None = None
          ) -> tuple[BoardAnalysis, VerifierResult, Decision]:
    jpeg = encode_jpeg(enhance(flat), max_w=config.JPEG_MAX_W)
    analysis = brain.see(jpeg, context)
    vres = verify(analysis)
    decision = policy.decide(analysis, vres)
    return analysis, vres, decision


def report(a: BoardAnalysis, v: VerifierResult, d: Decision, model: str | None) -> None:
    print("\n" + "=" * 72)
    print(f"model={model}  topic={a.topic}  complete={a.board_complete}  confidence={a.confidence:.2f}")
    print(f"problem: {a.problem}")
    for s in a.steps:
        flag = {"ok": "  ", "unclear": " ?", }.get(s.status.value, "!!")
        sym = v.line_ok.get(s.line)
        sym_s = "sympy=✓" if sym else "sympy=✗" if sym is False else "sympy=?"
        rule = f"  [{s.rule_used} -> {s.rule_expected}]" if s.status == StepStatus.WRONG_RULE else ""
        print(f" {flag} L{s.line} {s.status.value:<10} {sym_s}  {s.latex}{rule}")
        if s.note and s.status not in (StepStatus.OK, StepStatus.UNCLEAR):
            print(f"      note (internal): {s.note}")
    if v.veto_line is not None:
        print(f" VETO: {v.note}")
    for dis in v.disagreements:
        print(f" sympy disagrees: {dis}")
    print(f" gemini nudge: {a.nudge!r}")
    print(f" decision: speak={d.speak} mood={d.mood} reason={d.reason}")
    if d.speak:
        print(f"\n   OTTER SAYS: \"{d.text}\"\n")
    print("=" * 72)


async def act(robot: Robot, d: Decision) -> None:
    # The CLI never has a real ESP32 attached (commands print as [MOCK ROBOT]),
    # so keep the laser hold short instead of freezing the preview for 4 s.
    await robot.show(d.mood, d.box if d.speak else None, hold_s=0.2)


def run_image(path: Path, brain: Brain, policy: Policy, robot: Robot) -> int:
    img = cv2.imread(str(path))
    if img is None:
        print(f"could not read {path}", file=sys.stderr)
        return 2
    flat, found = flatten(img)
    print(f"vision backend={BACKEND} board_found={found} -> {flat.shape[1]}x{flat.shape[0]}")
    a, v, d = check(brain, policy, flat)
    report(a, v, d, brain.last_model)
    asyncio.run(act(robot, d))
    return 0


def _terminal_key() -> str | None:
    """A key typed in the terminal (plus Enter), without blocking. Lets the keys
    work even when the preview window doesn't have focus, or without --show."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return None
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.readline().strip().lower()[:1] or None
    except (OSError, ValueError):
        pass
    return None


def _window_key(view: np.ndarray) -> str | None:
    """Show the frame, pump Qt events, and return a pressed key as a lowercase
    letter ('q' for Esc or a closed window)."""
    cv2.imshow(WINDOW, view)
    k = cv2.waitKey(1) & 0xFF
    try:
        if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
            return "q"                        # user clicked the window's X
    except cv2.error:
        pass
    if k == 27:
        return "q"
    if k != 255 and k < 128:
        return chr(k).lower()
    return None


def run_camera(index: str, show: bool, brain: Brain, policy: Policy, robot: Robot) -> int:
    if show:
        quiet_qt_fonts()
    det = SettleDetector(still_s=config.STILL_S, min_interval_s=config.MIN_CHECK_INTERVAL_S,
                             change_thr=config.CHANGE_THR)
    detect = config.BOARD_DETECT
    stuck_announced = False
    dark_warned = False
    context: dict = {"previous_nudges": [], "last_problem": None}
    last_box: list[int] | None = None

    # Checks run on a daemon thread so the preview keeps drawing and keys keep
    # working during the 5-40 s a Gemini call (or a model's timeout) can take,
    # and so `q` exits immediately even mid-call.
    pending: Future | None = None
    pending_since = 0.0
    recheck_after = False                      # board settled again while a check was running

    cam_index, cam_name = resolve_camera(index)
    print(f"keys: c = check now, b = toggle board detection, q = quit. "
          f"{'Click the preview window first, or ' if show else ''}type the key + Enter here.")
    try:
        with Camera(cam_index, config.CAMERA_W, config.CAMERA_H) as cam:
            print(f"camera #{cam_index} ({cam_name}) {cam.size} vision={BACKEND} board_detect={detect}. "
                  "Waiting for the board to settle...")
            while True:
                frame = cam.read()
                if frame is None:
                    time.sleep(0.05)
                    continue
                dark = is_dark(frame)
                if dark and not dark_warned:
                    print("WARNING: black frame. Privacy shutter closed, lens covered, or wrong camera? "
                          "Not sending to Gemini. Try --index N or CAMERA_NAME in .env.")
                dark_warned = dark
                flat, found = flatten(frame, detect)
                trigger = det.update(flat) and not dark

                # ---- input: terminal and/or preview window ----
                key = _terminal_key()
                if show:
                    view = flat.copy()
                    h, w = view.shape[:2]
                    if last_box:
                        y0, x0, y1, x1 = last_box
                        cv2.rectangle(view, (x0 * w // 1000, y0 * h // 1000), (x1 * w // 1000, y1 * h // 1000),
                                      (0, 0, 255), 3)
                    cv2.putText(view, f"detect={'on' if detect else 'off'} board={'yes' if found else 'no'} "
                                f"motion={det.last_motion:.3f} changed={det.last_changed:.3f} "
                                f"idle={det.idle_seconds():.0f}s", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (0, 128, 0), 2)
                    if pending is not None:
                        cv2.putText(view, f"checking... {time.monotonic() - pending_since:.0f}s",
                                    (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    key = _window_key(view) or key
                if key == "q":
                    print("quit")
                    break
                if key == "b":
                    detect = not detect
                    print(f"board detection {'on' if detect else 'off'}")
                on_demand = False
                if key == "c":
                    if dark:
                        print("not checking a black frame")
                    elif pending is not None:
                        print("a check is already running")
                    else:
                        on_demand = True

                # ---- stuck detection ----
                if det.idle_seconds() > config.STUCK_AFTER_S and not stuck_announced and pending is None:
                    stuck_announced = True
                    print(f"[stuck] nothing changed for {config.STUCK_AFTER_S:.0f}s -> thinking face")
                    asyncio.run(robot.face("thinking"))
                    if config.STUCK_PROMPT:
                        print(f'\n   OTTER SAYS: "{config.STUCK_PROMPT}"\n')
                if det.last_motion > det.motion_thr:
                    stuck_announced = False

                # ---- a check finished? ----
                if pending is not None and pending.done():
                    try:
                        a, v, d = pending.result()
                    except Exception as e:
                        print(f"check failed: {e}")
                        asyncio.run(robot.face("idle"))
                    else:
                        report(a, v, d, brain.last_model)
                        asyncio.run(act(robot, d))
                        last_box = d.box if d.speak else None
                        if d.speak:
                            context["previous_nudges"].append(d.text)
                        if a.problem:
                            context["last_problem"] = a.problem
                    pending = None
                    if recheck_after:
                        recheck_after = False
                        trigger = True

                # ---- start a check ----
                if trigger or on_demand:
                    if pending is not None:
                        recheck_after = True   # board changed under a running check; look again after
                    else:
                        print(f"\n[{'on-demand' if on_demand else 'auto'}] checking board...")
                        asyncio.run(robot.face("thinking"))
                        det.mark_analyzed(flat)
                        pending = run_in_daemon(check, brain, policy, flat, {**context, "on_demand": on_demand},
                                                name="check")
                        pending_since = time.monotonic()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        if show:
            cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=Path, help="check one photo and exit")
    src.add_argument("--camera", action="store_true", help="live loop from the webcam")
    p.add_argument("--index", default=config.CAMERA_INDEX, help="camera index, or 'auto' (default: %(default)s)")
    p.add_argument("--show", action="store_true", help="preview window (camera mode)")
    p.add_argument("--no-record", action="store_true", help="don't save frames/replies to brain/recordings")
    p.add_argument("--mock", action="store_true",
                   help="no Gemini calls: canned verdicts (wrong rule / correct / arithmetic), zero quota")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname).1s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    brain: Brain
    if args.mock or config.GEMINI_MOCK:
        print("MOCK MODE: no Gemini calls, canned verdicts")
        brain = MockBrain()
    else:
        brain = GeminiBrain(record_dir=None if args.no_record else config.RECORD_DIR)
    policy = Policy(threshold=config.SPEAK_THRESHOLD, cooldown_s=config.COOLDOWN_S)
    robot = Robot()
    if args.image:
        return run_image(args.image, brain, policy, robot)
    return run_camera(args.index, args.show, brain, policy, robot)


if __name__ == "__main__":
    sys.exit(main())
