from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter


def client_timestamp(value: object) -> str | int:
    if not isinstance(value, str):
        return 0
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return 0
    if "T" not in value or parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        return 0
    return value


def server_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Payload(BaseModel):
    model_config = ConfigDict(strict=True)


class LoginData(Payload):
    name: str = Field(pattern=r"^[a-z0-9_]{1,32}$")


class SendData(Payload):
    recipient: str
    text: str
    client_sent_at: Annotated[str | int, BeforeValidator(client_timestamp)] = 0


class AckData(Payload):
    message_id: UUID
    recipient_received_at: Annotated[str | int, BeforeValidator(client_timestamp)] = 0


class Login(BaseModel):
    type: Literal["login"]
    correlation_id: UUID
    data: LoginData


class Send(BaseModel):
    type: Literal["send"]
    correlation_id: UUID
    data: SendData


class Ack(BaseModel):
    type: Literal["ack"]
    correlation_id: UUID
    data: AckData


request_adapter = TypeAdapter(Annotated[Login | Send | Ack, Field(discriminator="type")])


def correlation_id(raw: object) -> str | None:
    if isinstance(raw, dict) and isinstance(raw.get("correlation_id"), str):
        try:
            UUID(raw["correlation_id"])
            return raw["correlation_id"]
        except ValueError:
            pass
    return None


def event(kind: str, data: dict, correlation: str | None = None) -> dict:
    result = {"type": kind, "data": data}
    if correlation is not None:
        result["correlation_id"] = correlation
    return result
