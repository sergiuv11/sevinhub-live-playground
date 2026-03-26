# 🚀 SevinHub Live Playground


Real-time multiplayer interactive canvas with audio, particles, and dynamic behavior.

---

## ✨ Features

- 🎨 Real-time multiplayer drawing (WebSocket)
- 🌈 Unique color per user (auto-generated)
- 🧠 AI-style particle behavior (calm / flow / storm modes)
- 🔊 Touch sound interaction (Web Audio API)
- 🎤 Beat sync using microphone input
- 💾 Save artwork as PNG
- 🧑‍🤝‍🧑 Multi-room support (`?room=roomname`)
- 👤 Custom usernames per session
- 📊 Live event log panel (frontend)
- 📝 Server-side logging (SOC-style logs)
- 📱 Fully mobile-friendly

---

## 🧠 How It Works

- Users connect via WebSocket
- Each user gets a unique color
- Drawing generates particle bursts
- Room activity dynamically changes behavior:
  - Calm → smooth particles
  - Flow → dynamic motion
  - Storm → aggressive energy
- Optional microphone input influences particles in real-time

---

## 🏗 Tech Stack

- ⚙️ FastAPI (backend)
- 🔌 WebSocket (real-time communication)
- 🌐 Vanilla JavaScript (frontend)
- 🎨 HTML5 Canvas (rendering)
- 🔊 Web Audio API (sound + mic)

---

## 🚀 Run Locally

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8090
