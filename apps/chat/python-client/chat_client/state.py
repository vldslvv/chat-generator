"""Connection data and explicit session transitions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from aiohttp import ClientWebSocketResponse

from .protocol import User


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class SessionState(StrEnum):
    NONE = "none"
    LOGIN_PENDING = "login_pending"
    LOGGED_IN = "logged_in"


@dataclass
class QueuedMessage:
    sender_name: str
    recipient: str
    text: str
    correlation_id: UUID | None = None


@dataclass
class ClientState:
    server_url: str
    connection: ClientWebSocketResponse | None = None
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    session_state: SessionState = SessionState.NONE
    login_username: str | None = None
    authenticated_user: User | None = None
    remembered_username: str | None = None
    last_heartbeat_at: datetime | None = None
    outgoing_queue: list[QueuedMessage] = field(default_factory=list)


def begin_connection(state: ClientState, username: str) -> None:
    state.connection_state = ConnectionState.CONNECTING
    state.login_username = username


def complete_login(state: ClientState, user: User) -> None:
    state.authenticated_user = user
    state.remembered_username = user.name
    state.login_username = None
    state.session_state = SessionState.LOGGED_IN


def reset_connection(state: ClientState) -> None:
    state.connection = None
    state.connection_state = ConnectionState.DISCONNECTED
    state.session_state = SessionState.NONE
    state.login_username = None
    state.authenticated_user = None
    for entry in state.outgoing_queue:
        entry.correlation_id = None
