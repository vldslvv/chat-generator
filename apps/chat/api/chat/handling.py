from starlette.websockets import WebSocket

from chat import sessions, storage
from chat.models import Message, User
from chat.protocol import Ack, Login, Send


def handle(
    store: storage.Storage,
    active: sessions.Sessions,
    connection: WebSocket,
    request: Login | Send | Ack,
    received_at: str,
) -> User | Message | None:
    actor = sessions.current_user(active, connection)
    if isinstance(request, Login):
        if actor is not None:
            raise ValueError("Connection is already logged in")
        user = storage.find_user(store, request.data.name)
        if user is not None and sessions.online_connection(active, user.id) is not None:
            raise ValueError("User is already online")
        user = storage.find_or_create_user(store, request.data.name)
        sessions.bind(active, connection, user)
        return user
    if actor is None:
        raise ValueError("Login required")
    if isinstance(request, Send):
        recipient = storage.find_user(store, request.data.recipient)
        if recipient is None:
            raise ValueError("Recipient does not exist")
        message = storage.store_message(
            store,
            actor.id,
            recipient.id,
            request.data.text,
            request.data.client_sent_at,
            received_at,
        )
        return message
    message = storage.find_message(store, request.data.message_id)
    if message is None:
        raise ValueError("Message does not exist")
    if message.recipient_id != actor.id:
        raise ValueError("Only the recipient may acknowledge this message")
    storage.record_acknowledgment(
        store,
        message.id,
        request.data.recipient_received_at,
        received_at,
    )
    return None
