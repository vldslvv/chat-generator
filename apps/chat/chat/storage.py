from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from chat.models import Message, User


@dataclass
class Storage:
    users: dict[str, User] = field(default_factory=dict)
    messages: dict[UUID, Message] = field(default_factory=dict)


def find_user(store: Storage, name: str) -> User | None:
    return store.users.get(name)


def find_or_create_user(store: Storage, name: str) -> User:
    if name not in store.users:
        store.users[name] = User(uuid4(), name)
    return store.users[name]


def store_message(
    store: Storage,
    sender_id: UUID,
    recipient_id: UUID,
    text: str,
    client_sent_at: str | int,
    server_received_at: str,
) -> Message:
    message = Message(uuid4(), sender_id, recipient_id, text, client_sent_at, server_received_at)
    store.messages[message.id] = message
    return message


def find_message(store: Storage, message_id: UUID) -> Message | None:
    return store.messages.get(message_id)


def record_acknowledgment(
    store: Storage,
    message_id: UUID,
    recipient_received_at: str | int,
    server_ack_received_at: str,
) -> Message:
    message = store.messages[message_id]
    if message.server_ack_received_at is None:
        message = replace(
            message,
            recipient_received_at=recipient_received_at,
            server_ack_received_at=server_ack_received_at,
        )
        store.messages[message_id] = message
    return message
