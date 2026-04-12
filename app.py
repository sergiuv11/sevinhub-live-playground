from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import json
import os
import re
import time

app = FastAPI(
    title="SevinHub Live Playground V2",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

MAX_USERNAME_LENGTH = 30
MAX_ROOM_LENGTH = 30
MAX_DRAW_COORD = 10000
MAX_DRAW_VELOCITY = 100
MAX_DRAW_STRENGTH = 10
RATE_LIMIT_MESSAGES = 30
RATE_LIMIT_WINDOW = 1.0

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "events.log")
os.makedirs(LOG_DIR, exist_ok=True)
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "a", encoding="utf-8"):
        pass


def sanitize_log_value(value: str) -> str:
    """Remove control characters and limit length to prevent log injection."""
    return re.sub(r"[\x00-\x1f\x7f]", "", value)[:100]


def log_event(message: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {message}\n")


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}
        self.clients: dict[WebSocket, dict] = {}
        self.room_modes: dict[str, str] = {}
        self.room_activity: dict[str, int] = {}
        self.client_rate: dict[WebSocket, list[float]] = {}

    async def connect(self, websocket: WebSocket, room: str, username: str, hue: int):
        if room not in self.rooms:
            self.rooms[room] = []
        if room not in self.room_modes:
            self.room_modes[room] = "calm"
        if room not in self.room_activity:
            self.room_activity[room] = 0

        self.rooms[room].append(websocket)
        self.clients[websocket] = {
            "room": room,
            "username": username,
            "hue": hue,
        }
        self.client_rate[websocket] = []

    def disconnect(self, websocket: WebSocket):
        client = self.clients.get(websocket)
        if not client:
            return

        room = client["room"]
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)

        del self.clients[websocket]
        self.client_rate.pop(websocket, None)

        if room in self.rooms and not self.rooms[room]:
            del self.rooms[room]
            self.room_modes.pop(room, None)
            self.room_activity.pop(room, None)

    def get_room_user_count(self, room: str) -> int:
        return len(self.rooms.get(room, []))

    def get_room_mode(self, room: str) -> str:
        return self.room_modes.get(room, "calm")

    def update_room_mode(self, room: str, increment: int = 0) -> str:
        current = self.room_activity.get(room, 0) + increment
        current = max(0, current - 1)
        self.room_activity[room] = current

        if current > 220:
            mode = "storm"
        elif current > 90:
            mode = "flow"
        else:
            mode = "calm"

        self.room_modes[room] = mode
        return mode

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        """Return True if the client is within the rate limit, False otherwise."""
        now = time.monotonic()
        timestamps = self.client_rate.get(websocket, [])
        cutoff = now - RATE_LIMIT_WINDOW
        timestamps = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= RATE_LIMIT_MESSAGES:
            self.client_rate[websocket] = timestamps
            return False
        timestamps.append(now)
        self.client_rate[websocket] = timestamps
        return True

    async def send_json(self, websocket: WebSocket, message: dict):
        await websocket.send_text(json.dumps(message))

    async def broadcast(self, room: str, message: dict):
        dead = []
        for conn in self.rooms.get(room, []):
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                dead.append(conn)

        for conn in dead:
            self.disconnect(conn)

    async def broadcast_system(self, room: str, text: str | None = None):
        payload = {
            "type": "system",
            "users": self.get_room_user_count(room),
            "mode": self.get_room_mode(room),
        }
        if text:
            payload["message"] = text
        await self.broadcast(room, payload)


manager = RoomManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    joined = False
    room = "main"
    username = "anon"
    hue = 180

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type")

            if msg_type == "join":
                if joined:
                    continue

                room = str(payload.get("room", "main")).strip() or "main"
                room = room[:MAX_ROOM_LENGTH]
                username = str(payload.get("username", "anon")).strip() or "anon"
                username = username[:MAX_USERNAME_LENGTH]
                try:
                    hue = max(0, min(360, int(payload.get("hue", 180))))
                except Exception:
                    hue = 180

                await manager.connect(websocket, room, username, hue)
                joined = True

                safe_user = sanitize_log_value(username)
                safe_room = sanitize_log_value(room)
                log_event(f"[JOIN] user={safe_user} room={safe_room} hue={hue}")
                await manager.send_json(websocket, {
                    "type": "welcome",
                    "room": room,
                    "username": username,
                    "users": manager.get_room_user_count(room),
                    "mode": manager.get_room_mode(room),
                })
                await manager.broadcast_system(room, f"{username} joined")

            elif msg_type == "draw":
                if not joined:
                    continue

                if not manager.check_rate_limit(websocket):
                    continue

                def clamp_float(val, default, lo, hi):
                    try:
                        v = float(val)
                        if v != v:  # NaN check
                            return default
                        return max(lo, min(hi, v))
                    except (TypeError, ValueError):
                        return default

                draw_x = clamp_float(payload.get("x"), 0, -MAX_DRAW_COORD, MAX_DRAW_COORD)
                draw_y = clamp_float(payload.get("y"), 0, -MAX_DRAW_COORD, MAX_DRAW_COORD)
                draw_vx = clamp_float(payload.get("vx", 0), 0, -MAX_DRAW_VELOCITY, MAX_DRAW_VELOCITY)
                draw_vy = clamp_float(payload.get("vy", 0), 0, -MAX_DRAW_VELOCITY, MAX_DRAW_VELOCITY)
                draw_strength = clamp_float(payload.get("strength", 1), 1, 0, MAX_DRAW_STRENGTH)
                draw_hue = clamp_float(payload.get("hue", hue), hue, 0, 360)

                mode = manager.update_room_mode(room, increment=3)

                await manager.broadcast(room, {
                    "type": "draw",
                    "x": draw_x,
                    "y": draw_y,
                    "vx": draw_vx,
                    "vy": draw_vy,
                    "strength": draw_strength,
                    "hue": draw_hue,
                    "username": username,
                    "mode": mode,
                })

            elif msg_type == "clear":
                if not joined:
                    continue

                safe_user = sanitize_log_value(username)
                safe_room = sanitize_log_value(room)
                log_event(f"[CLEAR] user={safe_user} room={safe_room}")
                await manager.broadcast(room, {
                    "type": "clear",
                    "by": username,
                })
                await manager.broadcast_system(room, f"{username} cleared the canvas")

            elif msg_type == "ping":
                if not joined:
                    await manager.send_json(websocket, {"type": "pong"})
                else:
                    await manager.send_json(websocket, {
                        "type": "pong",
                        "users": manager.get_room_user_count(room),
                        "mode": manager.get_room_mode(room),
                    })

    except WebSocketDisconnect:
        if joined:
            old_room = room
            old_username = username
            manager.disconnect(websocket)
            log_event(f"[LEAVE] user={sanitize_log_value(old_username)} room={sanitize_log_value(old_room)}")
            await manager.broadcast_system(old_room, f"{old_username} left")
    except Exception as exc:
        if joined:
            old_room = room
            old_username = username
            manager.disconnect(websocket)
            log_event(f"[ERROR] user={sanitize_log_value(old_username)} room={sanitize_log_value(old_room)} error={repr(exc)}")
            await manager.broadcast_system(old_room, f"{old_username} disconnected")
        try:
            await websocket.close()
        except Exception:
            pass
