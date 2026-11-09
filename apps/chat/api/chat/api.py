import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from chat.handling import handle
from chat.protocol import correlation_id, event, request_adapter, server_timestamp
from chat.sessions import Sessions, disconnect
from chat.storage import Storage

logger = logging.getLogger("chat.api")


def rejection_cause(error: ValueError) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(map(str, detail['loc']))}: {detail['msg']}"
            for detail in error.errors(include_input=False, include_url=False)
        )
    return str(error)


def log_disconnect(code: int, reason: str, correlation: str | None) -> None:
    if code not in (1000, 1001):
        logger.warning(
            "Abnormal WebSocket disconnect correlation_id=%s cause=close code %s reason=%s",
            correlation,
            code,
            reason or "no close reason received",
        )


def create_app() -> FastAPI:
    app = FastAPI()
    store = Storage()
    active = Sessions()

    @app.websocket("/ws")
    async def websocket(connection: WebSocket) -> None:
        correlation = None
        try:
            await connection.accept()
            while True:
                correlation = None
                frame = await connection.receive()
                received_at = server_timestamp()
                if frame["type"] == "websocket.disconnect":
                    log_disconnect(frame["code"], frame.get("reason", ""), correlation)
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
                except (ValueError, ValidationError) as error:
                    logger.warning(
                        "Request rejected correlation_id=%s cause=%s",
                        correlation,
                        rejection_cause(error),
                    )
                    reply = event("error", {"message": "Invalid request"}, correlation)
                if reply is not None:
                    await connection.send_json(reply)
        except WebSocketDisconnect as error:
            if error.code not in (1000, 1001):
                logger.exception(
                    "WebSocket operation failed correlation_id=%s cause=close code %s reason=%s",
                    correlation,
                    error.code,
                    error.reason or "no close reason received",
                )
        except (OSError, RuntimeError):
            logger.exception("WebSocket operation failed correlation_id=%s", correlation)
        except Exception:
            logger.exception("WebSocket operation failed correlation_id=%s", correlation)
            raise
        finally:
            disconnect(active, connection)

    return app
