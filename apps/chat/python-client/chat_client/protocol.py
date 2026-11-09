"""Typed wire payloads and correlated direct replies."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, TypeAdapter

from .diagnostics import failure

if TYPE_CHECKING:
    from .state import ClientState


def _timestamp_input(value: object) -> object:
    if not isinstance(value, (str, datetime)):
        raise ValueError("Timestamp must be an ISO 8601 string")
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _zero(value: object) -> object:
    if type(value) is not int or value != 0:
        raise ValueError("Unknown timestamp must be the JSON number 0")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("Timestamp must be UTC")
    return value


UtcTimestamp = Annotated[
    datetime, BeforeValidator(_timestamp_input), AfterValidator(_utc)
]
UnknownTimestamp = Annotated[Literal[0], BeforeValidator(_zero)]


class WireModel(BaseModel):
    model_config = {"extra": "forbid"}


class User(WireModel):
    id: UUID
    name: str = Field(pattern=r"^[a-z0-9_]{1,32}$")


class Message(WireModel):
    id: UUID
    sender_id: UUID
    recipient_id: UUID
    text: str
    client_sent_at: UtcTimestamp | UnknownTimestamp
    server_received_at: UtcTimestamp
    recipient_received_at: UtcTimestamp | UnknownTimestamp | None
    server_ack_received_at: UtcTimestamp | None


class IncomingMessage(Message):
    sender_name: str


class Login(WireModel):
    name: str


class Send(WireModel):
    recipient: str
    text: str
    client_sent_at: UtcTimestamp


class Ack(WireModel):
    message_id: UUID
    recipient_received_at: UtcTimestamp


class Request(WireModel):
    type: Literal["login", "send", "ack"]
    correlation_id: UUID = Field(default_factory=uuid4)
    data: Login | Send | Ack


class LoginOk(WireModel):
    type: Literal["login_ok"]
    correlation_id: UUID
    data: User


class Accepted(WireModel):
    type: Literal["message_accepted"]
    correlation_id: UUID
    data: Message


class Received(WireModel):
    type: Literal["message_received"]
    data: IncomingMessage


class ErrorData(WireModel):
    message: str


class Error(WireModel):
    type: Literal["error"]
    correlation_id: UUID | None = None
    data: ErrorData


Event = Annotated[LoginOk | Accepted | Received | Error, Field(discriminator="type")]
_EVENT = TypeAdapter(Event)


def decode_event(raw: str) -> tuple[LoginOk | Accepted | Received | Error, datetime]:
    event = _EVENT.validate_json(raw)
    return event, datetime.now(UTC)


def event_correlation(raw: str) -> UUID | None:
    try:
        envelope = json.loads(raw)
        value = envelope.get("correlation_id") if isinstance(envelope, dict) else None
        return UUID(value) if isinstance(value, str) else None
    except (ValueError, TypeError):
        return None


def login_request(username: str) -> Request:
    return Request(type="login", data=Login(name=username))


def send_request(recipient: str, text: str) -> Request:
    return Request(
        type="send",
        data=Send(recipient=recipient, text=text, client_sent_at=datetime.now(UTC)),
    )


def ack_request(message_id: UUID, received_at: datetime) -> Request:
    return Request(
        type="ack",
        data=Ack(message_id=message_id, recipient_received_at=received_at),
    )


@dataclass
class Correlations:
    login: UUID | None = None
    send: UUID | None = None


async def handle_event(
    raw: str,
    state: ClientState,
    correlations: Correlations,
    write: Callable[[Request], Awaitable[None]],
    emit: Callable[[str], Awaitable[None]],
) -> None:
    from .state import SessionState, complete_login

    event, received_at = decode_event(raw)
    if isinstance(event, LoginOk):
        if event.correlation_id != correlations.login:
            raise ValueError("Unexpected login reply")
        complete_login(state, event.data)
        await emit(f"✓ Logged in as {event.data.name}")
        correlations.login = None
    elif isinstance(event, Accepted):
        if event.correlation_id != correlations.send:
            raise ValueError("Unexpected send reply")
        await emit(f"✓ Accepted {event.data.id}")
        correlations.send = None
    elif isinstance(event, Received):
        await emit(f"← {event.data.sender_name}: {event.data.text}")
        await write(ack_request(event.data.id, received_at))
    else:
        await failure("", event.data.message, event.correlation_id)
        if (
            correlations.login is not None
            and event.correlation_id == correlations.login
        ):
            correlations.login = None
            state.login_username = None
            state.session_state = SessionState.NONE
        if correlations.send is not None and event.correlation_id == correlations.send:
            correlations.send = None
