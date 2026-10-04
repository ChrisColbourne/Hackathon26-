"""Guided hardware check: you watch the robot, it asks what you see.

  python -m brain.tools.robot_test            # stop brain.server first (same port)

Listens where the brain normally does (port 8000, any path), waits for the
ESP32 to connect over Wi-Fi, then steps through the laser and both servos
with big, obvious moves and asks you to confirm each one. Ends with a
diagnosis: wiring to check, or which config.h flag to flip.
The laser switches on during the test: aim the head away from people.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets

from .. import config

STEPS = [
    # (command(s), question, expected answers, key)
    ([{"action": "home"}, {"action": "face", "state": "happy"}],
     "The otter face should look HAPPY (curved eyes, yellow sparkles). Does it? [y/n] ", "y", "face"),
    ([{"action": "laser", "on": False}],
     "The laser was just switched OFF. Is it off? [y/n] ", "y", "laser_off"),
    ([{"action": "laser", "on": True}],
     "The laser was just switched ON (head centred). Is it on? [y/n] ", "y", "laser_on"),
    ([{"action": "laser", "on": False}],
     "And OFF again. Is it off? [y/n] ", "y", "laser_off2"),
    ([{"action": "look", "pan": -30, "tilt": 0}],
     "The head was told to turn to ITS LEFT (your left, standing behind it). "
     "Which way did it turn? [l = left / r = right / n = didn't move] ", "l", "pan"),
    ([{"action": "look", "pan": 30, "tilt": 0}],
     "Now to ITS RIGHT. Which way did it turn? [l / r / n] ", "r", "pan2"),
    # Centre first and pause, so the pan swinging back doesn't hide the tilt (Oct 3 run).
    ([{"action": "home"}, {"sleep": 2.0}, {"action": "look", "pan": 0, "tilt": 12}],
     "Head centred, then told to tilt UP only. Which way did it tilt? [u = up / d = down / n = didn't move] ",
     "u", "tilt"),
    ([{"action": "home"}, {"sleep": 2.0}, {"action": "look", "pan": 0, "tilt": -20}],
     "Centred again, then told to tilt DOWN only. Which way? [u / d / n] ", "d", "tilt2"),
]


async def ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip().lower()[:1]


def diagnose(a: dict[str, str]) -> list[str]:
    out = []
    if a.get("laser_off") == "n" or a.get("laser_off2") == "n":
        if a.get("laser_on") == "n":
            out.append("LASER IS INVERTED (on when told off, off when told on) -> set  #define LASER_ACTIVE_LOW "
                       "true  in otter_robot/config.h (or wire it through the 2N2222 and set it false)")
        else:
            out.append("LASER STAYS ON when told off -> wiring. The firmware drives GPIO 27 LOW for off, so the "
                   "laser must be getting power without the transistor:\n"
                   "   - laser '-' pin must go to the 2N2222 COLLECTOR, not straight to GND\n"
                   "   - 2N2222 EMITTER to GND, BASE to GPIO 27 through the 1 kOhm resistor\n"
                   "   - check the transistor's pin order on its datasheet (it varies by maker)")
    if a.get("laser_on") == "n" and a.get("laser_off") != "n":
        out.append("LASER NEVER COMES ON -> laser 'S' to the 5 V rail? transistor base on GPIO 27 via 1 kOhm? "
                   "emitter to GND? rail powered?")
    pan, pan2, tilt, tilt2 = a.get("pan"), a.get("pan2"), a.get("tilt"), a.get("tilt2")
    if pan == "n" and pan2 == "n" and tilt == "n" and tilt2 == "n":
        out.append("NEITHER SERVO MOVES -> power, most likely: servo RED wires to the 5 V rail (never the ESP32's "
                   "3V3), BROWN to the GND rail, the rail actually powered by the charger, and the ESP32's GND "
                   "on the same rail (common ground). Signal (orange): pan -> GPIO 25, tilt -> GPIO 26.")
    else:
        if pan == "n" and pan2 == "n":
            out.append("PAN SERVO doesn't move -> its orange signal wire on GPIO 25? red/brown on the rail?")
        elif pan == "r" and pan2 == "l":
            out.append("PAN IS REVERSED -> set  #define PAN_INVERT true  in otter_robot/config.h and reflash")
        if tilt == "n" and tilt2 == "n":
            out.append("TILT SERVO doesn't move -> its orange signal wire on GPIO 26? red/brown on the rail?")
        elif tilt == "d" and tilt2 == "u":
            out.append("TILT IS REVERSED -> set  #define TILT_INVERT true  in otter_robot/config.h and reflash")
    if a.get("face") == "n":
        out.append("FACE not happy -> screen wiring/rotation; is the screen showing the otter at all?")
    return out or ["Everything behaved as expected."]


async def main(port: int) -> int:
    robot: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def handler(ws) -> None:
        print("\nrobot connected.")
        await robot.put(ws)
        await ws.wait_closed()

    async with websockets.serve(handler, "0.0.0.0", port):
        print(f"waiting for the robot on port {port} (press EN on the ESP32 if it doesn't connect in ~10 s)...")
        ws = await robot.get()
        print("The laser will switch on during this test. Aim the head away from people.\n")
        answers: dict[str, str] = {}
        for cmds, question, expected, key in STEPS:
            for c in cmds:
                if "sleep" in c:
                    await asyncio.sleep(c["sleep"])
                else:
                    await ws.send(json.dumps(c))
            await asyncio.sleep(1.5)                    # let the head arrive
            answers[key] = await ask(question)
        await ws.send(json.dumps({"action": "home"}))
        print("\n--- result ---")
        for k, (_, _, expected, key) in zip(answers, STEPS):
            print(f"  {key:<11} expected {expected!r:<5} you saw {answers[key]!r:<5} {'OK' if answers[key] == expected else '<-'}")
        print("\n--- diagnosis ---")
        for line in diagnose(answers):
            print(" * " + line)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=config.PORT)
    try:
        sys.exit(asyncio.run(main(p.parse_args().port)))
    except KeyboardInterrupt:
        sys.exit(0)
