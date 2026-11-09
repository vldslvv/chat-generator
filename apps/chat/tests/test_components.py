import asyncio
import logging
from dataclasses import asdict
from uuid import uuid4

from starlette.websockets import WebSocket

from chat import sessions, storage
from chat.handling import handle
from chat.models import User
from chat.protocol import request_adapter


def test_storage_first_ack_is_atomic_and_users_are_stable():
    store = storage.Storage()
    assert storage.find_user(store, "alice") is None
    alice = storage.find_or_create_user(store, "alice")
    assert storage.find_or_create_user(store, "alice") == alice
    bob = storage.find_or_create_user(store, "bob")
    assert alice.id != bob.id
    message = storage.store_message(store, alice.id, bob.id, "original", 0, "receive-time")
    assert message.recipient_received_at is None
    assert message.server_ack_received_at is None
    first = storage.record_acknowledgment(store, message.id, 0, "ack-time")
    again = storage.record_acknowledgment(store, message.id, "later", "later-ack")
    assert first == again
    assert asdict(first) == {
        **asdict(message),
        "recipient_received_at": 0,
        "server_ack_received_at": "ack-time",
    }
    assert storage.find_message(store, message.id) == first
    assert storage.find_message(store, uuid4()) is None
    assert storage.Storage().users == storage.Storage().messages == {}


def test_delivery_failure_retains_message_and_never_retries(caplog):
    # A real Starlette connection with a failing ASGI transport deterministically
    # models the failure after online validation and storage, without a socket race.
    transport_calls = []

    async def receive():
        return {"type": "websocket.connect"}

    async def broken_send(frame):
        transport_calls.append(frame)
        if frame["type"] == "websocket.send":
            raise OSError("transport lost")

    async def normal_send(frame):
        pass

    async def scenario():
        alice_connection = WebSocket({"type": "websocket"}, receive, normal_send)
        bob_connection = WebSocket({"type": "websocket"}, receive, broken_send)
        await alice_connection.accept()
        await bob_connection.accept()
        transport_calls.clear()
        store, active = storage.Storage(), sessions.Sessions()
        alice, bob = (storage.find_or_create_user(store, name) for name in ("alice", "bob"))
        sessions.bind(active, alice_connection, alice)
        sessions.bind(active, bob_connection, bob)
        request = request_adapter.validate_json(
            '{"type":"send","correlation_id":"'
            + str(uuid4())
            + '","data":{"recipient":"bob","text":"retained"}}'
        )
        reply = await handle(store, active, alice_connection, request, "event-received-time")
        assert reply["type"] == "message_accepted"
        assert len(store.messages) == 1
        message = next(iter(store.messages.values()))
        assert message.text == "retained"
        assert message.server_received_at == "event-received-time"
        assert message.server_ack_received_at is None
        assert sessions.online_connection(active, bob.id) is None
        assert sessions.current_user(active, bob_connection) is None
        assert sessions.current_user(active, alice_connection) == alice
        assert len(transport_calls) == 1
        await asyncio.sleep(0.05)
        assert len(transport_calls) == 1
        return active, alice_connection, bob

    with caplog.at_level(logging.INFO, logger="chat.delivery"):
        asyncio.run(scenario())
    assert sum("Delivery attempt" in record.message for record in caplog.records) == 1
    assert sum("Delivery failed" in record.message for record in caplog.records) == 1


def test_session_resolver_prevents_duplicate_and_rebinding():
    active = sessions.Sessions()
    # Resolver behavior doesn't depend on transport methods.
    first, second = object(), object()
    alice, bob = User(uuid4(), "alice"), User(uuid4(), "bob")
    sessions.bind(active, first, alice)
    for connection, user in [(first, alice), (first, bob), (second, alice)]:
        try:
            sessions.bind(active, connection, user)
        except ValueError:
            pass
        else:
            raise AssertionError("Duplicate login was permitted")
    assert sessions.current_user(active, first) == alice
    sessions.disconnect(active, first)
    sessions.disconnect(active, first)
    sessions.bind(active, second, alice)
    assert sessions.online_connection(active, alice.id) is second
