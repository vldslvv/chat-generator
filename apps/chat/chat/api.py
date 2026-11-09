import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from chat.handling import handle
from chat.protocol import correlation_id, event, request_adapter, server_timestamp
from chat.sessions import Sessions, disconnect
from chat.storage import Storage


def create_app() -> FastAPI:
    app = FastAPI()
    store = Storage()
    active = Sessions()

    @app.websocket("/ws")
    async def websocket(connection: WebSocket) -> None:
        await connection.accept()
        try:
            while True:
                frame = await connection.receive()
                received_at = server_timestamp()
                if frame["type"] == "websocket.disconnect":
                    break
                raw = None
                correlation = None
                try:
                    if "text" not in frame:
                        raise ValueError("Expected a JSON text message")
                    raw = json.loads(frame["text"])
                    correlation = correlation_id(raw)
                    # JSON-mode validation accepts wire UUID strings while retaining strict fields.
                    request = request_adapter.validate_json(frame["text"])
                    reply = await handle(store, active, connection, request, received_at)
                    if reply is not None:
                        reply["correlation_id"] = correlation
                except (ValueError, ValidationError):
                    reply = event("error", {"message": "Invalid request"}, correlation)
                if reply is not None:
                    await connection.send_json(reply)
        except (WebSocketDisconnect, OSError, RuntimeError):
            pass
        finally:
            disconnect(active, connection)

    return app
