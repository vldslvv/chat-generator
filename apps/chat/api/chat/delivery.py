import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect

from chat import storage
from chat.models import Message
from chat.protocol import event
from chat.sessions import Sessions, disconnect, online_connection

logger = logging.getLogger("chat.delivery")


@dataclass
class Delivery:
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)


@asynccontextmanager
async def recipient_turn(delivery: Delivery, name: str | None):
    if name is None:
        yield
    else:
        # Reserve the turn before binding login, including the login reply and replay.
        async with delivery.locks.setdefault(name, asyncio.Lock()):
            yield


async def deliver(
    sessions: Sessions, user_id: UUID, notification: dict, correlation: str | None
) -> bool:
    connection = online_connection(sessions, user_id)
    logger.info(
        "Delivery attempt user=%s type=%s correlation_id=%s",
        user_id,
        notification["type"],
        correlation,
    )
    if connection is None:
        logger.warning(
            "Delivery failed user=%s correlation_id=%s cause=recipient disconnected",
            user_id,
            correlation,
        )
        return False
    try:
        await connection.send_json(notification)
    except (OSError, RuntimeError, WebSocketDisconnect):
        disconnect(sessions, connection)
        logger.exception("Delivery failed user=%s correlation_id=%s", user_id, correlation)
        return False
    logger.info("Delivery succeeded user=%s correlation_id=%s", user_id, correlation)
    return True


async def deliver_message(
    store: storage.Storage, sessions: Sessions, message: Message, correlation: str | None
) -> bool:
    sender = storage.find_user_by_id(store, message.sender_id)
    if sender is None:
        logger.error(
            "Delivery failed message=%s correlation_id=%s cause=sender record missing",
            message.id,
            correlation,
        )
        return False
    data = jsonable_encoder(asdict(message))
    return await deliver(
        sessions,
        message.recipient_id,
        event("message_received", {**data, "sender_name": sender.name}),
        correlation,
    )


async def flush_messages(
    store: storage.Storage, sessions: Sessions, recipient_id: UUID, correlation: str | None
) -> None:
    for message in storage.list_pending_messages(store, recipient_id):
        if online_connection(sessions, recipient_id) is None:
            break
        if not await deliver_message(store, sessions, message, correlation):
            break
