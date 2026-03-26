# SevinHub Live Playground

Real-time multiplayer interactive canvas with audio and particle system.

## Features

- 🎨 Real-time multiplayer drawing (WebSocket)
- 🌈 Unique color per user
- 🔊 Touch sound interaction
- 🎤 Beat sync using microphone
- 💾 Save artwork as PNG
- 📱 Mobile-friendly

## Tech Stack

- FastAPI (backend)
- WebSocket
- Vanilla JavaScript (frontend)
- HTML5 Canvas
- Web Audio API

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
