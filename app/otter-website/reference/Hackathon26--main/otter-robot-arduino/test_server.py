"""Tiny stand-in for B's server, so A and D can test the robot alone.
pip install websockets  ->  python tools/test_server.py
Type JSON commands, or shortcuts: happy, think, talk, look -20 10, laser -15 -5, off, home
"""
import asyncio, json, math
import websockets

robot = None

SHORT = {
    "idle": {"action": "face", "state": "idle"}, "listen": {"action": "face", "state": "listening"},
    "think": {"action": "face", "state": "thinking"}, "happy": {"action": "face", "state": "happy"},
    "confused": {"action": "face", "state": "confused"}, "off": {"action": "laser", "on": False},
    "home": {"action": "home"},
}

async def talk_demo(ws, seconds=3.0):
    await ws.send(json.dumps({"action": "face", "state": "talking"}))
    t = 0.0
    while t < seconds:
        level = abs(math.sin(t * 11) * math.sin(t * 7.3 + 1))
        await ws.send(json.dumps({"action": "mouth", "level": round(level, 2)}))
        await asyncio.sleep(1 / 15); t += 1 / 15
    await ws.send(json.dumps({"action": "face", "state": "idle"}))

async def handler(ws):
    global robot
    robot = ws
    print("robot connected")
    try:
        async for msg in ws:
            print("<-", msg)
    finally:
        robot = None
        print("robot disconnected")

async def console():
    loop = asyncio.get_running_loop()
    while True:
        line = (await loop.run_in_executor(None, input, "> ")).strip()
        if not line or robot is None:
            print("(no robot connected)" if robot is None else ""); continue
        parts = line.split()
        if parts[0] == "talk":
            await talk_demo(robot); continue
        if parts[0] in ("look", "laser") and len(parts) == 3:
            cmd = {"action": parts[0], "pan": float(parts[1]), "tilt": float(parts[2])}
            if parts[0] == "laser": cmd["on"] = True
        else:
            cmd = SHORT.get(parts[0]) or json.loads(line)
        await robot.send(json.dumps(cmd)); print("->", cmd)

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("test server on ws://0.0.0.0:8765/robot - put this laptop's IP in secrets.h")
        await console()

asyncio.run(main())
