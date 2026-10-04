"""Show each of the otter's six expressions on the real robot.

  python -m brain.tools.face_test              # all six, 6 s each   (stop brain.server first: same port)
  python -m brain.tools.face_test happy        # just one, until Ctrl+C
  python -m brain.tools.face_test --hold 10    # all six, 10 s each

Listens where the brain normally does (port 8000), waits for the ESP32 to
connect over Wi-Fi, then cycles idle, listening, thinking, talking (with the
mouth moving), happy, confused. Prints whether the robot acknowledged each one;
you check that the screen matches.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys

import websockets

from .. import config

MOODS = ["idle", "listening", "thinking", "talking", "happy", "confused"]
LOOKS = {
    "idle": "gentle smile, eyes drifting side to side",
    "listening": "wide eyes, ears up, three bouncing bars above the head",
    "thinking": "eyes up, raised brows, thought bubble with filling dots",
    "talking": "mouth opening and closing",
    "happy": "^ ^ eyes, bigger smile, four twinkling stars",
    "confused": "one eye half shut, tilted brow, bobbing '?'",
}


async def show(ws, mood: str, hold_s: float, acks: list[str]) -> None:
    before = acks.count("face")
    await ws.send(json.dumps({"action": "face", "state": mood}))
    print(f"  {mood.upper():<10} should look like: {LOOKS[mood]}")
    t = 0.0
    while t < hold_s:
        if mood == "talking":          # drive the mouth like the voice does, ~15 levels/s
            level = abs(math.sin(t * 11) * math.sin(t * 7.3 + 1))
            await ws.send(json.dumps({"action": "mouth", "level": round(level, 2)}))
        await asyncio.sleep(1 / 15)
        t += 1 / 15
    print(f"  {'':<10} robot acknowledged: {'yes' if acks.count('face') > before else 'NO'}")


async def main(port: int, only: str | None, hold_s: float) -> int:
    robot: asyncio.Queue = asyncio.Queue(maxsize=1)
    acks: list[str] = []

    async def handler(ws) -> None:
        print("robot connected.\n")
        await robot.put(ws)
        async for msg in ws:                 # drain the robot's replies so its sends never block
            try:
                m = json.loads(msg)
            except ValueError:
                continue
            if m.get("status") == "done":
                acks.append(m.get("action", ""))

    async with websockets.serve(handler, "0.0.0.0", port):
        print(f"waiting for the robot on port {port} (press EN on the ESP32 if it doesn't connect in ~10 s)...")
        ws = await robot.get()
        await ws.send(json.dumps({"action": "home"}))
        await asyncio.sleep(1.0)
        if only:
            await show(ws, only, float("inf") if hold_s <= 0 else hold_s, acks)
        else:
            for mood in MOODS:
                await show(ws, mood, hold_s, acks)
        await ws.send(json.dumps({"action": "face", "state": "idle"}))
        await asyncio.sleep(0.5)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mood", nargs="?", choices=MOODS, help="show only this expression (until Ctrl+C)")
    p.add_argument("--hold", type=float, default=6.0, help="seconds per expression (default: %(default)s)")
    p.add_argument("--port", type=int, default=config.PORT)
    a = p.parse_args()
    try:
        sys.exit(asyncio.run(main(a.port, a.mood, 0 if a.mood and a.hold == 6.0 else a.hold)))
    except KeyboardInterrupt:
        sys.exit(0)
