from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class User:
    id: UUID
    name: str


@dataclass(frozen=True)
class Message:
    id: UUID
    sender_id: UUID
    recipient_id: UUID
    text: str
    client_sent_at: str | int
    server_received_at: str
    recipient_received_at: str | int | None = None
    server_ack_received_at: str | None = None
