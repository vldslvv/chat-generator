import json
import logging
from dataclasses import asdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from chat import delivery
from chat.handling import handle
from chat.models import Message, User
from chat.protocol import Login, Send, correlation_id, event, request_adapter, server_timestamp
from chat.sessions import Sessions, disconnect, online_connection
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
    outbound = delivery.Delivery()

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
                    recipient = (
                        request.data.name
                        if isinstance(request, Login)
                        else request.data.recipient
                        if isinstance(request, Send)
                        else None
                    )
                    async with delivery.recipient_turn(outbound, recipient):
                        result = handle(store, active, connection, request, received_at)
                        try:
                            if result is not None:
                                kind = (
                                    "login_ok" if isinstance(result, User) else "message_accepted"
                                )
                                await connection.send_json(
                                    event(kind, jsonable_encoder(asdict(result)), correlation)
                                )
                        finally:
                            if (
                                isinstance(result, Message)
                                and online_connection(active, result.recipient_id) is not None
                            ):
                                await delivery.deliver_message(store, active, result, correlation)
                        if isinstance(result, User):
                            await delivery.flush_messages(store, active, result.id, correlation)
                except (ValueError, ValidationError) as error:
                    logger.warning(
                        "Request rejected correlation_id=%s cause=%s",
                        correlation,
                        rejection_cause(error),
                    )
                    await connection.send_json(
                        event("error", {"message": "Invalid request"}, correlation)
                    )
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
