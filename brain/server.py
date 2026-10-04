"""The laptop brain server (FastAPI).

  uvicorn brain.server:app --host 0.0.0.0 --port 8000
  python -m brain.server              (same, reads HOST/PORT from .env)

Endpoints
  WS  /ws/robot   ESP32 connects here (Contract 1). One robot at a time.
  WS  /ws/app     Web app(s) connect here (Contract 3). Many allowed.
  POST /check     multipart `image` -> runs the full pipeline on that photo.
                  Handy for curl tests and for C's app if it ever sends photos.
  GET  /health    who's connected, how many checks, vision backend.
  GET  /          serves app/ if it exists (C's web app).

Camera loop: if CAMERA_ENABLED=1 in .env, the server watches the webcam and
auto-checks when the board settles. Without it, checks come only from
/check or the app's `check_now`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from . import config
from .camera import Camera, SettleDetector, encode_jpeg, flatten, is_dark, resolve_camera
from .gemini_brain import GeminiBrain
from .mock_brain import MockBrain
from .policy import Policy
from .robot import Robot
from .schemas import Mood, Nudge
from .session import Session
from .threads import run_in_daemon
from .verifier import verify
from .vision import BACKEND, enhance
from .voice import Voice

log = logging.getLogger("server")
CAMERA_ENABLED = os.getenv("CAMERA_ENABLED", "0") == "1"


class Brain:
    """Everything the endpoints share."""

    def __init__(self) -> None:
        self.gemini: GeminiBrain | MockBrain = MockBrain() if config.GEMINI_MOCK else GeminiBrain()
        self.policy = Policy(threshold=config.SPEAK_THRESHOLD, cooldown_s=config.COOLDOWN_S)
        self.robot = Robot()
        self.session = Session()
        self.apps: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.voice = Voice(on_mouth=self._mouth_from_thread, on_state=self._state_from_thread)
        self.latest_flat: np.ndarray | None = None
        self.check_requested = asyncio.Event()
        self.busy = asyncio.Lock()
        self.state: Mood = "idle"

    # ---- fan-out to apps --------------------------------------------------
    async def broadcast(self, event: dict[str, Any]) -> None:
        dead = []
        for ws in self.apps:
            try:
                await ws.send_text(json.dumps(event, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.apps.discard(ws)

    async def set_state(self, state: Mood) -> None:
        self.state = state
        await asyncio.gather(self.robot.face(state), self.broadcast({"event": "state", "state": state}))

    # voice.speak runs in a worker thread; hop back onto the event loop
    def _mouth_from_thread(self, level: float) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.robot.mouth(level), self.loop)

    def _state_from_thread(self, state: Mood) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.set_state(state), self.loop)

    # ---- the pipeline -------------------------------------------------------
    async def run_check(self, flat: np.ndarray, on_demand: bool = False) -> dict[str, Any]:
        async with self.busy:
            await self.set_state("thinking")
            jpeg = encode_jpeg(enhance(flat), max_w=config.JPEG_MAX_W)
            ctx = self.session.context(on_demand)
            try:
                # daemon thread: an in-flight Gemini call must not delay shutdown
                analysis = await asyncio.wrap_future(run_in_daemon(self.gemini.see, jpeg, ctx, name="gemini"))
            except Exception as e:
                log.error("gemini failed: %s", e)
                await self.set_state("idle")
                await self.broadcast({"event": "error", "text": f"Gemini failed: {e}"})
                return {"ok": False, "error": str(e)}
            self.session.consume_heard()
            vres = verify(analysis)
            decision = self.policy.decide(analysis, vres)
            self.session.add_check(analysis, vres, decision, on_demand)

            await self.broadcast({"event": "analysis", **analysis.model_dump(mode="json"),
                                  "sympy": vres.line_ok, "veto": vres.veto_line,
                                  "decision": {"speak": decision.speak, "reason": decision.reason}})
            if decision.speak:
                await self.broadcast(Nudge(text=decision.text, line=decision.line, kind=decision.kind,
                                           mood=decision.mood).model_dump(mode="json"))
                tasks = [asyncio.to_thread(self.voice.speak, decision.text, decision.mood),
                         self.robot.react(decision.mood)]
                if decision.box is not None:
                    tasks.append(self.robot.point_at(decision.box))
                await asyncio.gather(*tasks)
            await self.set_state(decision.mood if decision.mood in ("happy", "confused") else "idle")
            return {"ok": True, "analysis": analysis.model_dump(mode="json"),
                    "decision": {"speak": decision.speak, "text": decision.text, "mood": decision.mood,
                                 "line": decision.line, "reason": decision.reason}}

    # ---- camera loop ---------------------------------------------------------
    async def camera_loop(self) -> None:
        det = SettleDetector(still_s=config.STILL_S, min_interval_s=config.MIN_CHECK_INTERVAL_S)
        stuck_announced = False
        dark_warned = False
        try:
            cam_index, cam_name = await asyncio.to_thread(resolve_camera)
            cam = Camera(cam_index, config.CAMERA_W, config.CAMERA_H)
        except Exception as e:
            log.error("camera unavailable: %s (checks via /check and the app only)", e)
            return
        log.info("camera #%d (%s) %s, vision backend %s", cam_index, cam_name, cam.size, BACKEND)
        try:
            while True:
                frame = await asyncio.to_thread(cam.read)
                if frame is None:
                    await asyncio.sleep(0.05)
                    continue
                dark = is_dark(frame)
                if dark and not dark_warned:
                    log.warning("black frame from camera #%d: shutter closed / lens covered / wrong camera? "
                                "Not sending to Gemini.", cam_index)
                    await self.broadcast({"event": "error", "text": "camera frame is black"})
                dark_warned = dark
                flat, _found = await asyncio.to_thread(flatten, frame)
                self.latest_flat = flat
                trigger = det.update(flat) and not dark
                on_demand = self.check_requested.is_set() and not dark

                if (det.idle_seconds() > config.STUCK_AFTER_S and not stuck_announced
                        and self.state in ("idle", "listening") and not self.busy.locked()):
                    stuck_announced = True
                    await self.set_state("thinking")
                    await self.broadcast({"event": "stuck", "text": config.STUCK_PROMPT})
                    if config.STUCK_PROMPT:
                        await asyncio.to_thread(self.voice.speak, config.STUCK_PROMPT, "thinking")
                if det.last_motion > det.motion_thr:
                    stuck_announced = False

                if (trigger or on_demand) and not self.busy.locked():
                    self.check_requested.clear()
                    det.mark_analyzed(flat)
                    await self.run_check(flat, on_demand)
                await asyncio.sleep(0.03)
        finally:
            cam.release()

    async def handle_app_cmd(self, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        if cmd == "check_now":
            if self.latest_flat is not None and CAMERA_ENABLED:
                self.check_requested.set()
            else:
                await self.broadcast({"event": "error", "text": "no camera frame; POST /check with an image"})
        elif cmd == "student_said":
            self.session.add_heard(str(msg.get("text", "")))
            await self.set_state("listening")
            if CAMERA_ENABLED:
                self.check_requested.set()  # answer against the current board
        elif cmd == "stuck":
            await self.set_state("thinking")
            if CAMERA_ENABLED:
                self.check_requested.set()
        elif cmd == "end_session":
            summary = self.session.summary()
            await self.broadcast(summary.model_dump(mode="json"))
            await self.robot.home()
            self.session = Session()
            self.policy.reset()
        elif cmd == "robot":  # raw passthrough for calibration / A's testing
            from .schemas import RobotCommand
            await self.robot.send(RobotCommand(**msg.get("command", {})))
        else:
            await self.broadcast({"event": "error", "text": f"unknown cmd {cmd!r}"})


brain = Brain()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    brain.loop = asyncio.get_running_loop()
    task = asyncio.create_task(brain.camera_loop()) if CAMERA_ENABLED else None
    log.info("brain up. camera=%s vision=%s models=%s%s", CAMERA_ENABLED, BACKEND,
             [m for m, _ in brain.gemini.chain], "  (MOCK MODE, no Gemini calls)" if config.GEMINI_MOCK else "")
    yield
    if task:
        task.cancel()


app = FastAPI(title="Otter Tutor brain", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "robot": brain.robot.connected, "robot_ready": brain.robot.ready,
            "apps": len(brain.apps), "checks": len(brain.session.checks), "gemini_calls": brain.gemini.calls,
            "vision": BACKEND, "camera": CAMERA_ENABLED, "voice_live": brain.voice.live, "state": brain.state,
            "mock": config.GEMINI_MOCK}


@app.post("/check")
async def check(image: UploadFile = File(...)) -> dict[str, Any]:
    data = np.frombuffer(await image.read(), np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        return {"ok": False, "error": "not an image"}
    flat, _ = flatten(frame)
    return await brain.run_check(flat, on_demand=True)


@app.websocket("/ws/robot")
async def ws_robot(ws: WebSocket) -> None:
    await ws.accept()
    brain.robot.attach(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("robot sent non-JSON: %r", raw)
                continue
            log.info("robot: %s", msg)
            brain.robot.on_status(msg)
            await brain.broadcast({"event": "robot", **msg})
    except WebSocketDisconnect:
        pass
    finally:
        brain.robot.detach()


@app.websocket("/ws/app")
async def ws_app(ws: WebSocket) -> None:
    await ws.accept()
    brain.apps.add(ws)
    await ws.send_text(json.dumps({"event": "state", "state": brain.state}))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"event": "error", "text": "send JSON"}))
                continue
            log.info("app: %s", msg)
            await brain.handle_app_cmd(msg)
    except WebSocketDisconnect:
        pass
    finally:
        brain.apps.discard(ws)


_app_dir = Path(__file__).resolve().parent.parent / "app"
if _app_dir.is_dir():
    app.mount("/", StaticFiles(directory=_app_dir, html=True), name="app")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("brain.server:app", host=config.HOST, port=config.PORT, reload=False)
