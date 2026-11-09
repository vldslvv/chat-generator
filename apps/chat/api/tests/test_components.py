import json
from dataclasses import asdict
from uuid import uuid4

import pytest

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
    assert handle(store, active, connection, first, "ack-event") is None
    stored = storage.find_message(store, message.id)
    assert asdict(stored) == {
        **asdict(message),
        "recipient_received_at": expected,
        "server_ack_received_at": "ack-event",
    }
    repeated = ack({"message_id": str(message.id), "recipient_received_at": "later"})
    assert handle(store, active, connection, repeated, "later-event") is None
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
            handle(store, active, connection, request, "ack-event")
        assert storage.find_message(store, message.id) == message


def test_pending_storage_filters_recipient_and_acknowledgment_in_acceptance_order():
    store = storage.Storage()
    alice, bob = (storage.find_or_create_user(store, name) for name in ("alice", "bob"))
    assert storage.find_user_by_id(store, alice.id) == alice
    assert storage.find_user_by_id(store, uuid4()) is None
    first = storage.store_message(store, alice.id, bob.id, "first", "later", "received-first")
    other = storage.store_message(store, bob.id, alice.id, "other", 0, "received-second")
    acknowledged = storage.store_message(store, alice.id, bob.id, "acked", 0, "received-third")
    last = storage.store_message(store, alice.id, bob.id, "last", "earlier", "received-last")
    storage.record_acknowledgment(store, acknowledged.id, 0, "ack-time")
    assert storage.list_pending_messages(store, bob.id) == [first, last]
    assert storage.list_pending_messages(store, alice.id) == [other]
    assert storage.list_pending_messages(store, uuid4()) == []
    assert storage.find_message(store, acknowledged.id).server_ack_received_at == "ack-time"


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
