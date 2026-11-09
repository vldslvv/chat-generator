import logging
from uuid import UUID

from starlette.websockets import WebSocketDisconnect

from chat.sessions import Sessions, disconnect, online_connection

logger = logging.getLogger("chat.delivery")


async def deliver(sessions: Sessions, user_id: UUID, event: dict, correlation: str) -> bool:
    connection = online_connection(sessions, user_id)
    logger.info(
        "Delivery attempt user=%s type=%s correlation_id=%s", user_id, event["type"], correlation
    )
    if connection is None:
        logger.warning(
            "Delivery failed user=%s correlation_id=%s cause=recipient disconnected",
            user_id,
            correlation,
        )
        return False
    try:
        await connection.send_json(event)
    except (OSError, RuntimeError, WebSocketDisconnect):
        disconnect(sessions, connection)
        logger.exception("Delivery failed user=%s correlation_id=%s", user_id, correlation)
        return False
    logger.info("Delivery succeeded user=%s correlation_id=%s", user_id, correlation)
    return True
