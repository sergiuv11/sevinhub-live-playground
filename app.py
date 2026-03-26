from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import json
from typing import List

app = FastAPI(title="SevinHub Live Playground")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.activity_counter = 0
        self.last_mode = "calm"

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        await self.broadcast_system_state()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal(self, websocket: WebSocket, message: dict):
        await websocket.send_text(json.dumps(message))

    async def broadcast(self, message: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

    async def broadcast_system_state(self):
        await self.broadcast({
            "type": "system",
            "users": len(self.active_connections),
            "mode": self.last_mode
        })

    def detect_mode(self):
        # simple "AI mode" behavior based on recent activity intensity
        if self.activity_counter > 250:
            self.last_mode = "storm"
        elif self.activity_counter > 120:
            self.last_mode = "flow"
        else:
            self.last_mode = "calm"

        # decay activity over time
        self.activity_counter = max(0, self.activity_counter - 15)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        await manager.send_personal(websocket, {
            "type": "welcome",
            "users": len(manager.active_connections),
            "mode": manager.last_mode
        })

        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)

            if payload.get("type") == "draw":
                manager.activity_counter += 3
                manager.detect_mode()

                await manager.broadcast({
                    "type": "draw",
                    "x": payload.get("x"),
                    "y": payload.get("y"),
                    "vx": payload.get("vx", 0),
                    "vy": payload.get("vy", 0),
                    "strength": payload.get("strength", 1),
                    "userId": payload.get("userId", "anon"),
		    "hue": payload.get("hue", 180),
                    "mode": manager.last_mode
                })

                await manager.broadcast_system_state()

            elif payload.get("type") == "clear":
                await manager.broadcast({
                    "type": "clear"
                })

            elif payload.get("type") == "ping":
                await manager.send_personal(websocket, {
                    "type": "pong",
                    "users": len(manager.active_connections),
                    "mode": manager.last_mode
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast_system_state()
    except Exception:
        manager.disconnect(websocket)
        await manager.broadcast_system_state()
