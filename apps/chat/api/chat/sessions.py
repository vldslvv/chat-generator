from dataclasses import dataclass, field
from uuid import UUID

from starlette.websockets import WebSocket

from chat.models import User


@dataclass
class Sessions:
    connections: dict[WebSocket, User] = field(default_factory=dict)
    online: dict[UUID, WebSocket] = field(default_factory=dict)


def current_user(sessions: Sessions, connection: WebSocket) -> User | None:
    return sessions.connections.get(connection)


def online_connection(sessions: Sessions, user_id: UUID) -> WebSocket | None:
    return sessions.online.get(user_id)


def bind(sessions: Sessions, connection: WebSocket, user: User) -> None:
    if connection in sessions.connections:
        raise ValueError("Connection is already logged in")
    if user.id in sessions.online:
        raise ValueError("User is already online")
    sessions.connections[connection] = user
    sessions.online[user.id] = connection


def disconnect(sessions: Sessions, connection: WebSocket) -> None:
    user = sessions.connections.pop(connection, None)
    if user is not None and sessions.online.get(user.id) is connection:
        del sessions.online[user.id]
