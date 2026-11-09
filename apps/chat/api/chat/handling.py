from dataclasses import asdict

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocket

from chat import sessions, storage
from chat.delivery import deliver
from chat.protocol import Ack, Login, Send, event


async def handle(
    store: storage.Storage,
    active: sessions.Sessions,
    connection: WebSocket,
    request: Login | Send | Ack,
    received_at: str,
) -> dict | None:
    correlation = str(request.correlation_id)
    actor = sessions.current_user(active, connection)
    if isinstance(request, Login):
        if actor is not None:
            raise ValueError("Connection is already logged in")
        user = storage.find_user(store, request.data.name)
        if user is not None and sessions.online_connection(active, user.id) is not None:
            raise ValueError("User is already online")
        user = storage.find_or_create_user(store, request.data.name)
        sessions.bind(active, connection, user)
        return event("login_ok", jsonable_encoder(asdict(user)), correlation)
    if actor is None:
        raise ValueError("Login required")
    if isinstance(request, Send):
        recipient = storage.find_user(store, request.data.recipient)
        if recipient is None:
            raise ValueError("Recipient does not exist")
        if sessions.online_connection(active, recipient.id) is None:
            raise ValueError("Recipient is offline")
        message = storage.store_message(
            store,
            actor.id,
            recipient.id,
            request.data.text,
            request.data.client_sent_at,
            received_at,
        )
        data = jsonable_encoder(asdict(message))
        await deliver(active, recipient.id, event("message_received", data), correlation)
        return event("message_accepted", data, correlation)
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
