"""Connect the brain to the robot over the USB cable instead of Wi-Fi.

  python -m brain.tools.serial_bridge                   # /dev/ttyUSB0 -> ws://localhost:8000/robot
  python -m brain.tools.serial_bridge --port /dev/ttyUSB1 --url ws://localhost:8000/robot

The firmware accepts the same JSON commands on its serial port as over
WebSocket, and prints its replies as `[tx] {...}`. This relays both ways, so
the brain sees an ordinary robot connection. Use it when the venue Wi-Fi
won't let the ESP32 reach the laptop (enterprise logins, client isolation).
Start the brain server first; the bridge reconnects if either side drops.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

import serial  # pyserial
import websockets

log = logging.getLogger("bridge")


def open_serial(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, baud, 0.05
    ser.dtr = ser.rts = False          # opening must not hold the ESP32 in reset
    ser.open()
    return ser


def wait_until_ready(ser: serial.Serial, timeout_s: float = 30.0) -> bool:
    """Opening the port resets most ESP32 boards (auto-reset circuit), and the
    firmware then spends up to 15 s trying Wi-Fi before it reads commands.
    Anything sent before '[otter] ready' is lost, so wait for it."""
    deadline = time.monotonic() + timeout_s
    buf = b""
    log.info("waiting for the robot to boot (up to %.0f s; the Wi-Fi attempt takes ~15 s)...", timeout_s)
    while time.monotonic() < deadline:
        buf += ser.read(256)
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode(errors="replace").strip()
            if "[otter] ready" in line:
                log.info("robot ready")
                return True
            if line.startswith("[net]"):
                log.info("robot: %s", line)
    return False


async def serial_to_ws(ser: serial.Serial, ws, echo: bool) -> None:
    """Robot -> brain: forward `[tx] {json}` lines; show the rest as robot logs."""
    buf = b""
    while True:
        chunk = await asyncio.to_thread(ser.read, 256)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode(errors="replace").strip()
            if line.startswith("[tx] "):
                payload = line[5:]
                try:
                    json.loads(payload)
                except json.JSONDecodeError:
                    continue
                await ws.send(payload)
            elif line and echo and not line.startswith("[rx]"):
                log.info("robot: %s", line)


async def ws_to_serial(ser: serial.Serial, ws) -> None:
    """Brain -> robot: one JSON command per line."""
    async for msg in ws:
        await asyncio.to_thread(ser.write, (msg.strip() + "\n").encode())


async def run(port: str, baud: int, url: str, echo: bool) -> None:
    ser = open_serial(port, baud)
    log.info("serial %s open", port)
    if not await asyncio.to_thread(wait_until_ready, ser):
        log.warning("no '[otter] ready' from the robot; continuing anyway (already running?)")
    while True:
        try:
            async with websockets.connect(url) as ws:
                log.info("connected to brain at %s", url)
                await ws.send('{"status":"ready"}')    # what the firmware sends on a Wi-Fi connect
                tasks = [asyncio.create_task(serial_to_ws(ser, ws, echo)),
                         asyncio.create_task(ws_to_serial(ser, ws))]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                for t in done:
                    t.result()
        except (OSError, websockets.ConnectionClosed) as e:
            log.warning("brain connection lost (%s); retrying in 2 s", e)
        await asyncio.to_thread(ser.write, b'{"action":"home"}\n')   # laser off, head centred
        await asyncio.sleep(2)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--url", default="ws://localhost:8000/robot")
    p.add_argument("--quiet", action="store_true", help="don't echo the robot's own log lines")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
    try:
        asyncio.run(run(args.port, args.baud, args.url, not args.quiet))
    except serial.SerialException as e:
        print(f"serial error: {e}\n(is the ESP32 plugged in? permission: sudo chmod a+rw {args.port})", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
