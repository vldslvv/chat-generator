import logging
from uuid import UUID

from starlette.websockets import WebSocketDisconnect

from chat.sessions import Sessions, disconnect, online_connection

logger = logging.getLogger("chat.delivery")


async def deliver(sessions: Sessions, user_id: UUID, event: dict) -> bool:
    connection = online_connection(sessions, user_id)
    logger.info("Delivery attempt user=%s type=%s", user_id, event["type"])
    if connection is None:
        logger.info("Delivery failed user=%s: disconnected", user_id)
        return False
    try:
        await connection.send_json(event)
    except (OSError, RuntimeError, WebSocketDisconnect):
        disconnect(sessions, connection)
        logger.info("Delivery failed user=%s", user_id, exc_info=True)
        return False
    logger.info("Delivery succeeded user=%s", user_id)
    return True
