"""Aim the laser at the whiteboard's four corners and save them.

  python -m brain.tools.calibrate_laser        # stop brain.server first (same port)

The brain turns Gemini's box around a wrong line into pan/tilt angles by
blending these four corners, so the laser lands on the right line only once
this is done, and again whenever the robot or the board moves. Aim at the
corners of the board area the camera sees (the rectangle in the --show preview).

Keys, no Enter needed:  a / d = left / right   w / s = up / down   (1 deg; A D W S = 5 deg)
                        Enter = this corner is right, next one     q = quit without saving
Saves brain/calibration.json, which brain.server loads when it starts.
The laser is on while you aim: keep it away from people's eyes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import termios
import threading
import tty

import websockets

from .. import config
from ..calibration import CORNER_ORDER, DEFAULT_PATH, Calibration, Corner
from .robot_link import RobotLink

NAMES = {"tl": "TOP-LEFT", "tr": "TOP-RIGHT", "br": "BOTTOM-RIGHT", "bl": "BOTTOM-LEFT"}
PAN_LIMIT, TILT_MIN, TILT_MAX = 60, -25, 15     # same limits as the firmware's config.h
STEPS = {"a": (-1, 0), "d": (1, 0), "w": (0, 1), "s": (0, -1), "A": (-5, 0), "D": (5, 0), "W": (0, 5), "S": (0, -5)}
KEEPALIVE_S = 4.0                               # the firmware switches the laser off after 6 s without a command


def start_key_reader(loop: asyncio.AbstractEventLoop, keys: asyncio.Queue) -> None:
    """Single keypresses from the terminal (cbreak mode: Ctrl+C still works)."""
    def run() -> None:
        while True:
            ch = sys.stdin.read(1)
            loop.call_soon_threadsafe(keys.put_nowait, ch)
            if not ch:
                return
    threading.Thread(target=run, daemon=True).start()


async def aim(link: RobotLink, pan: float, tilt: float) -> None:
    link.replay = {"action": "laser", "on": True, "pan": pan, "tilt": tilt}   # re-aimed after a reconnect
    await link.send(link.replay)


async def calibrate(link: RobotLink, keys: asyncio.Queue) -> Calibration | None:
    cal = Calibration.load()                    # start from the last saved (or default) corners
    for name in CORNER_ORDER:
        c: Corner = getattr(cal, name)
        pan, tilt = c.pan, c.tilt
        print(f"\n{NAMES[name]} corner: move the dot onto it, then press Enter.")
        await aim(link, pan, tilt)
        while True:
            sys.stdout.write(f"\r  pan {pan:+6.1f}   tilt {tilt:+6.1f}   ")
            sys.stdout.flush()
            try:
                ch = await asyncio.wait_for(keys.get(), KEEPALIVE_S)
            except asyncio.TimeoutError:
                await link.send({"action": "laser", "on": True})   # keep it lit, don't move
                continue
            if ch in ("\n", "\r"):
                setattr(cal, name, Corner(pan, tilt))
                print("saved")
                break
            if ch in ("q", ""):
                return None
            if ch in STEPS:
                dp, dt = STEPS[ch]
                pan = max(-PAN_LIMIT, min(PAN_LIMIT, pan + dp))
                tilt = max(TILT_MIN, min(TILT_MAX, tilt + dt))
                await aim(link, pan, tilt)
    return cal


async def check(link: RobotLink, keys: asyncio.Queue, cal: Calibration) -> bool:
    print("\nChecking: the dot should land in the MIDDLE of the board. Does it? [y/n] ", end="", flush=True)
    await aim(link, *cal.angles_at(0.5, 0.5))
    while True:
        try:
            ch = await asyncio.wait_for(keys.get(), KEEPALIVE_S)
        except asyncio.TimeoutError:
            await link.send({"action": "laser", "on": True})
            continue
        if ch.lower() in ("y", "n"):
            print(ch)
            return ch.lower() == "y"


async def main(port: int) -> int:
    link = RobotLink()
    keys: asyncio.Queue = asyncio.Queue()

    async with websockets.serve(link.handler, "0.0.0.0", port):
        print(f"waiting for the robot on port {port} (press EN on the ESP32 if it doesn't connect in ~10 s)...")
        await link.wait()
        print("The laser switches on now. Keep it away from people's eyes.")
        old = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        start_key_reader(asyncio.get_running_loop(), keys)
        try:
            cal = await calibrate(link, keys)
            if cal is None:
                print("\nquit; nothing saved.")
                return 1
            if not await check(link, keys, cal):
                print("Not saved. Run it again and aim each corner a bit more carefully.")
                return 1
            cal.save()
            print(f"\nsaved to {DEFAULT_PATH.relative_to(DEFAULT_PATH.parents[1])}. "
                  "Restart brain.server to use it.")
            return 0
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
            link.replay = None
            await link.send({"action": "laser", "on": False}, wait_s=3)
            await link.send({"action": "home"}, wait_s=1)
            await asyncio.sleep(0.3)
            if link.reconnects:
                print(f"\nThe robot dropped off {link.reconnects} time(s) during this run. Restarts after a "
                      "head move mean the power supply is too weak for the servos (see COMMANDS.txt).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=config.PORT)
    try:
        sys.exit(asyncio.run(main(p.parse_args().port)))
    except KeyboardInterrupt:
        sys.exit(0)
