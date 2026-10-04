"""Commands to the ESP32 (Contract 1). Mocks itself when no robot is connected.

The ESP32 connects to the brain's /ws/robot endpoint; server.py hands that
socket to `Robot.attach()`. Every method here just builds a RobotCommand and
sends JSON. With no socket attached, commands are logged as [MOCK ROBOT] so
Person B can work before Person A's hardware exists.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from .calibration import Calibration
from .schemas import Mood, RobotCommand

log = logging.getLogger("robot")


class _Socket(Protocol):
    async def send_text(self, data: str) -> Any: ...


class Robot:
    def __init__(self, calibration: Calibration | None = None):
        self.calibration = calibration or Calibration.load()
        self._ws: _Socket | None = None
        self.ready = False
        self.last_status: dict[str, Any] | None = None

    # ---- connection ---------------------------------------------------
    def attach(self, ws: _Socket) -> None:
        self._ws = ws
        log.info("robot attached")

    def detach(self) -> None:
        self._ws = None
        self.ready = False
        log.info("robot detached")

    def on_status(self, msg: dict[str, Any]) -> None:
        """Called by server.py for every message the ESP32 sends."""
        self.last_status = msg
        if msg.get("status") == "ready":
            self.ready = True

    @property
    def connected(self) -> bool:
        return self._ws is not None

    # ---- primitives ---------------------------------------------------
    async def send(self, cmd: RobotCommand) -> None:
        payload = json.dumps(cmd.model_dump(exclude_none=True))
        if self._ws is None:
            # mouth levels arrive ~15x/s while talking; keep them out of INFO logs
            (log.debug if cmd.action == "mouth" else log.info)("[MOCK ROBOT] %s", payload)
            return
        try:
            await self._ws.send_text(payload)
        except Exception as e:  # socket died; keep the brain alive
            log.warning("robot send failed (%s); detaching", e)
            self.detach()

    async def face(self, state: Mood) -> None:
        await self.send(RobotCommand(action="face", state=state))

    async def mouth(self, level: float) -> None:
        await self.send(RobotCommand(action="mouth", level=max(0.0, min(1.0, level))))

    async def look(self, pan: float, tilt: float) -> None:
        await self.send(RobotCommand(action="look", pan=pan, tilt=tilt))

    async def laser(self, on: bool, pan: float | None = None, tilt: float | None = None) -> None:
        await self.send(RobotCommand(action="laser", on=on, pan=pan, tilt=tilt))

    async def home(self) -> None:
        await self.send(RobotCommand(action="home"))

    # ---- composites ---------------------------------------------------
    async def point_at(self, box: list[int], hold_s: float = 4.0) -> None:
        """Turn toward a Gemini box, laser on, hold, then laser off (head stays)."""
        pan, tilt = self.calibration.box_to_angles(box)
        await self.look(pan, tilt)
        await self.laser(True, pan, tilt)
        await asyncio.sleep(hold_s)
        await self.laser(False)

    async def react(self, mood: Mood) -> None:
        """Mood plus a small matching head move (A tunes the angles)."""
        await self.face(mood)
        if mood == "confused":
            await self.look(0, 6)
        elif mood == "happy":
            await self.look(0, -4)
            await asyncio.sleep(0.3)
            await self.look(0, 0)
