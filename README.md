# realtime-ws-server

A WebSocket server for real-time messaging, presence tracking, and pub/sub channels.

## Stack
- Python 3.12+
- FastAPI + Uvicorn + WebSockets
- asyncio-native, no external message broker required

## Quickstart

```bash
pip install -r requirements.txt
uvicorn server:app --reload
```

## Connecting

```js
const ws = new WebSocket("ws://localhost:8000/ws?token=JWT&channel=general");

ws.send(JSON.stringify({ type: "message", text: "Hello!", ref: "abc123" }));
```

## Message Types (client → server)

| Type | Fields | Description |
|------|--------|-------------|
| `message` | `channel`, `text`, `ref` | Send a chat message |
| `typing` | `channel` | Broadcast typing indicator |
| `react` | `channel`, `message_id`, `emoji` | React to a message |
| `subscribe` | `channel` | Join a channel |
| `unsubscribe` | `channel` | Leave a channel |
| `ping` | `ref` | Keepalive ping |

## Server Events (server → client)

| Type | Description |
|------|-------------|
| `message` | Incoming message from another user |
| `ack` | Delivery confirmation for your message |
| `typing` | Another user is typing |
| `react` | Emoji reaction on a message |
| `user_joined` | User joined the channel |
| `user_left` | User left the channel |
| `channel_state` | Full channel snapshot on join |
| `pong` | Response to ping |
| `error` | Error with code and detail |

## REST API

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/channels | List channels and member counts |
| GET | /api/presence | List online users |
| GET | /health | Server health + connection stats |
