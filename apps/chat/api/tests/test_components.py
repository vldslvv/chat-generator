import asyncio
import json
import logging
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest
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
    fresh = storage.Storage()
    assert storage.find_user(fresh, "alice") is None
    assert storage.find_user(fresh, "bob") is None
    assert storage.find_message(fresh, message.id) is None


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ({}, 0),
        ({"recipient_received_at": None}, 0),
        ({"recipient_received_at": 42}, 0),
        ({"recipient_received_at": True}, 0),
        ({"recipient_received_at": {}}, 0),
        ({"recipient_received_at": []}, 0),
        ({"recipient_received_at": "bad"}, 0),
        ({"recipient_received_at": "2026-11-08"}, 0),
        ({"recipient_received_at": "2026-11-08T12:00:00"}, 0),
        ({"recipient_received_at": "2026-11-08T12:00:00+01:00"}, 0),
        ({"recipient_received_at": "2026-11-08T12:00:00Z"}, "2026-11-08T12:00:00Z"),
        (
            {"recipient_received_at": "2026-11-08T12:00:00+00:00"},
            "2026-11-08T12:00:00+00:00",
        ),
    ],
)
def test_ack_validation_records_first_event_timestamps(timestamp, expected):
    # Observe stored ack values through public storage operations because a valid
    # acknowledgment deliberately produces no response or notification.
    store, active = storage.Storage(), sessions.Sessions()
    alice, bob = (storage.find_or_create_user(store, name) for name in ("alice", "bob"))
    message = storage.store_message(store, alice.id, bob.id, "original", 0, "send-event")
    connection = object()
    sessions.bind(active, connection, bob)

    def ack(data):
        return request_adapter.validate_json(
            json.dumps({"type": "ack", "correlation_id": str(uuid4()), "data": data})
        )

    first = ack({"message_id": str(message.id), "server_ack_received_at": "forged", **timestamp})
    assert asyncio.run(handle(store, active, connection, first, "ack-event")) is None
    stored = storage.find_message(store, message.id)
    assert asdict(stored) == {
        **asdict(message),
        "recipient_received_at": expected,
        "server_ack_received_at": "ack-event",
    }
    repeated = ack({"message_id": str(message.id), "recipient_received_at": "later"})
    assert asyncio.run(handle(store, active, connection, repeated, "later-event")) is None
    assert storage.find_message(store, message.id) == stored


def test_invalid_ack_does_not_change_storage():
    store, active = storage.Storage(), sessions.Sessions()
    alice, bob = (storage.find_or_create_user(store, name) for name in ("alice", "bob"))
    message = storage.store_message(store, alice.id, bob.id, "original", 0, "send-event")
    connection = object()
    for actor, message_id in [(None, message.id), (alice, message.id), (bob, uuid4())]:
        sessions.disconnect(active, connection)
        if actor is not None:
            sessions.bind(active, connection, actor)
        request = request_adapter.validate_json(
            json.dumps(
                {
                    "type": "ack",
                    "correlation_id": str(uuid4()),
                    "data": {"message_id": str(message_id)},
                }
            )
        )
        with pytest.raises(ValueError):
            asyncio.run(handle(store, active, connection, request, "ack-event"))
        assert storage.find_message(store, message.id) == message


def test_delivery_failure_retains_message_and_never_retries(caplog):
    # A real Starlette connection with a failing ASGI transport deterministically
    # models the failure after online validation and storage, without a socket race.
    transport_calls = []
    correlation = str(uuid4())

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
            + correlation
            + '","data":{"recipient":"bob","text":"retained"}}'
        )
        reply = await handle(store, active, alice_connection, request, "event-received-time")
        assert reply["type"] == "message_accepted"
        message = storage.find_message(store, UUID(reply["data"]["id"]))
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
    assert "transport lost" in caplog.text
    assert all(correlation in record.message for record in caplog.records)
    failure = next(record for record in caplog.records if "Delivery failed" in record.message)
    assert failure.levelno >= logging.WARNING


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
