"""The robot's WebSocket for the test tools, kept current across reconnects.

The ESP32 rejoins by itself after a Wi-Fi drop or a restart. A restart right
after a head move means the servos pulled the supply low (brownout): see
"Robot keeps restarting" in COMMANDS.txt.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets


class RobotLink:
    def __init__(self) -> None:
        self.ws: Any = None
        self.connected = asyncio.Event()
        self.connections = 0
        self.acks: list[str] = []
        self.replay: dict | None = None      # re-sent after a reconnect (e.g. the laser's current aim)

    async def handler(self, ws) -> None:
        """Pass to websockets.serve()."""
        self.connections += 1
        if self.reconnects:
            print("\n  ! robot reconnected. If that happened right after the head moved, it RESTARTED: "
                  "the servos are pulling the power supply too low (see COMMANDS.txt).", flush=True)
        else:
            print("robot connected.", flush=True)
        self.ws = ws
        self.connected.set()
        if self.replay is not None and self.reconnects:      # put the laser back where it was
            await asyncio.sleep(0.5)
            await self.send(self.replay)
        try:
            async for msg in ws:                 # drain the robot's replies so its sends never block
                try:
                    m = json.loads(msg)
                except ValueError:
                    continue
                if m.get("status") == "done":
                    self.acks.append(m.get("action", ""))
        except websockets.ConnectionClosed:
            pass
        if self.ws is ws:
            self.ws = None
            self.connected.clear()

    @property
    def reconnects(self) -> int:
        return max(0, self.connections - 1)

    async def wait(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self.connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def send(self, cmd: dict, wait_s: float = 20.0) -> bool:
        """Send to whichever connection is live, waiting up to wait_s for the robot
        to come back. False if it doesn't."""
        for _ in range(2):
            if self.ws is None and not await self.wait(wait_s):
                return False
            ws = self.ws
            try:
                await ws.send(json.dumps(cmd))
                return True
            except websockets.ConnectionClosed:
                if self.ws is ws:
                    self.ws = None
                    self.connected.clear()
        return False
