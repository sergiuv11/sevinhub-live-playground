from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import json
import os

app = FastAPI(title="SevinHub Live Playground V2")

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

    def disconnect(self, websocket: WebSocket):
        client = self.clients.get(websocket)
        if not client:
            return

        room = client["room"]
        if room in self.rooms and websocket in self.rooms[room]:
            self.rooms[room].remove(websocket)

        del self.clients[websocket]

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
                username = str(payload.get("username", "anon")).strip() or "anon"
                try:
                    hue = int(payload.get("hue", 180))
                except Exception:
                    hue = 180

                await manager.connect(websocket, room, username, hue)
                joined = True

                log_event(f"[JOIN] user={username} room={room} hue={hue}")
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

                mode = manager.update_room_mode(room, increment=3)

                await manager.broadcast(room, {
                    "type": "draw",
                    "x": payload.get("x"),
                    "y": payload.get("y"),
                    "vx": payload.get("vx", 0),
                    "vy": payload.get("vy", 0),
                    "strength": payload.get("strength", 1),
                    "hue": payload.get("hue", hue),
                    "username": username,
                    "mode": mode,
                })

            elif msg_type == "clear":
                if not joined:
                    continue

                log_event(f"[CLEAR] user={username} room={room}")
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
            log_event(f"[LEAVE] user={old_username} room={old_room}")
            await manager.broadcast_system(old_room, f"{old_username} left")
    except Exception as exc:
        if joined:
            old_room = room
            old_username = username
            manager.disconnect(websocket)
            log_event(f"[ERROR] user={old_username} room={old_room} error={repr(exc)}")
            await manager.broadcast_system(old_room, f"{old_username} disconnected")
        try:
            await websocket.close()
        except Exception:
            pass
