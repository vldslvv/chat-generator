import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from conftest import running_server
from helpers import login, receive, request, sent_message
from websockets.sync.client import connect


def test_message_and_silent_acknowledgments(clients):
    alice, bob = clients
    sender, recipient = login(alice, "alice"), login(bob, "bob")
    before = datetime.now(UTC)
    message = sent_message(
        alice,
        bob,
        client_sent_at="2026-11-08T12:00:00Z",
        server_received_at="1900-01-01T00:00:00Z",
        sender_id=recipient["id"],
    )
    UUID(message["id"])
    assert message["sender_id"] == sender["id"]
    assert message["recipient_id"] == recipient["id"]
    assert message["text"] == "hello 🌎"
    assert message["client_sent_at"] == "2026-11-08T12:00:00Z"
    assert before <= datetime.fromisoformat(message["server_received_at"]) <= datetime.now(UTC)
    assert message["recipient_received_at"] is None
    assert message["server_ack_received_at"] is None
    request(
        bob,
        "ack",
        {
            "message_id": message["id"],
            "recipient_received_at": "2026-11-08T12:01:00+00:00",
            "server_ack_received_at": "1900-01-01T00:00:00Z",
        },
    )
    request(bob, "ack", {"message_id": message["id"], "recipient_received_at": 17})
    # A later request on Bob's connection establishes that both acks were handled.
    request(bob, "send", {"recipient": "alice", "text": "acknowledged"})
    assert receive(bob)["type"] == "message_accepted"
    reply = receive(alice)
    assert reply["type"] == "message_received"
    assert reply["data"]["text"] == "acknowledged"
    for client in (alice, bob):
        with pytest.raises(TimeoutError):
            client.recv(timeout=0.05)


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        0,
        42,
        True,
        {},
        [],
        "bad",
        "2026-11-08",
        "2026-11-08T12:00:00",
        "2026-11-08T12:00:00+01:00",
    ],
)
def test_timestamp_fallback(clients, timestamp):
    alice, bob = clients
    login(alice, "alice")
    login(bob, "bob")
    message = sent_message(alice, bob, client_sent_at=timestamp)
    assert message["client_sent_at"] == 0


def test_missing_timestamps_and_empty_text(clients):
    alice, bob = clients
    login(alice, "alice")
    login(bob, "bob")
    message = sent_message(alice, bob, text="")
    assert message["text"] == ""
    assert message["client_sent_at"] == 0


@pytest.mark.parametrize("name", ["", "Alice", "a-b", "a b", "é", "x" * 33, "alice\n", 1])
def test_invalid_names_keep_connection_usable(clients, name):
    alice, _ = clients
    correlation = request(alice, "login", {"name": name})
    assert receive(alice)["correlation_id"] == correlation
    login(alice, "valid_name_9")


def test_name_boundary_and_repeated_login(clients):
    alice, bob = clients
    first = login(alice, "x" * 32)
    for client, name in [(alice, "x" * 32), (alice, "other"), (bob, "x" * 32)]:
        correlation = request(client, "login", {"name": name})
        assert receive(client) == {
            "type": "error",
            "correlation_id": correlation,
            "data": {"message": "Invalid request"},
        }
    login(bob, "bob")
    assert sent_message(alice, bob)["sender_id"] == first["id"]


@pytest.mark.parametrize(
    "raw,valid_id",
    [
        ("{", False),
        ("null", False),
        ("[]", False),
        (json.dumps({"type": "login", "correlation_id": "bad", "data": {"name": "a"}}), False),
        (json.dumps({"type": "login", "correlation_id": 123, "data": {"name": "a"}}), False),
        (json.dumps({"type": "unknown", "correlation_id": "ID", "data": {}}), True),
        (json.dumps({"type": "login", "correlation_id": "ID", "data": []}), True),
        (json.dumps({"type": "login", "correlation_id": "ID"}), True),
        (b"binary", False),
    ],
)
def test_invalid_envelope_keeps_connection_usable(clients, raw, valid_id):
    alice, _ = clients
    correlation = str(uuid4()).upper()
    if isinstance(raw, str):
        raw = raw.replace("ID", correlation)
    alice.send(raw)
    error = receive(alice)
    assert error["type"] == "error"
    assert error.get("correlation_id") == (correlation if valid_id else None)
    login(alice, "alice")


def test_valid_correlation_echo_preserves_representation(clients):
    alice, _ = clients
    correlation = str(uuid4()).upper()
    request(alice, "login", {"name": "alice"}, correlation)
    assert receive(alice)["correlation_id"] == correlation


def test_rejected_actions_keep_connections_usable(clients):
    alice, bob = clients
    for kind, data in [
        ("send", {"recipient": "bob", "text": "x"}),
        ("ack", {"message_id": str(uuid4())}),
    ]:
        correlation = request(alice, kind, data)
        reply = receive(alice)
        assert reply["type"] == "error"
        assert reply["correlation_id"] == correlation
    login(alice, "alice")
    login(bob, "bob")
    message = sent_message(alice, bob)
    invalid = [
        (alice, "send", {"recipient": "unknown", "text": "x"}),
        (alice, "send", {"recipient": "bob"}),
        (alice, "send", {"recipient": "bob", "text": 7}),
        (alice, "send", {"recipient": 3, "text": "x"}),
        (
            alice,
            "ack",
            {"message_id": message["id"], "recipient_received_at": "2026-11-08T12:00:00Z"},
        ),
        (bob, "ack", {}),
        (bob, "ack", {"message_id": "bad"}),
        (bob, "ack", {"message_id": str(uuid4())}),
    ]
    for client, kind, data in invalid:
        correlation = request(client, kind, data)
        reply = receive(client)
        assert reply["type"] == "error"
        assert reply["correlation_id"] == correlation
    request(bob, "ack", {"message_id": message["id"]})
    with pytest.raises(TimeoutError):
        bob.recv(timeout=0.05)
    with pytest.raises(TimeoutError):
        alice.recv(timeout=0.05)


def test_disconnect_persistence_offline_rejection_and_no_replay(server):
    url, _ = server
    with connect(url) as alice:
        alice_user = login(alice, "alice")
        with connect(url) as bob:
            bob_user = login(bob, "bob")
            message = sent_message(alice, bob)
        deadline = time.monotonic() + 2
        while True:
            request(alice, "send", {"recipient": "bob", "text": "offline"})
            reply = receive(alice)
            if reply["type"] == "error":
                break
            assert reply["type"] == "message_accepted"
            assert time.monotonic() < deadline, "Disconnect was not detected"
            time.sleep(0.01)
    with connect(url) as bob:
        assert login(bob, "bob") == bob_user
        request(bob, "ack", {"message_id": message["id"]})
        with pytest.raises(TimeoutError):
            bob.recv(timeout=0.1)
    with connect(url) as alice:
        assert login(alice, "alice") == alice_user
        with pytest.raises(TimeoutError):
            alice.recv(timeout=0.1)


def test_new_server_discards_users_and_messages():
    with running_server() as (url, _), connect(url) as client:
        original_user = login(client, "alice")
        request(client, "send", {"recipient": "alice", "text": "self"})
        incoming = receive(client)
        assert incoming["type"] == "message_received"
        assert receive(client)["type"] == "message_accepted"
    with running_server() as (url, _), connect(url) as client:
        assert login(client, "alice")["id"] != original_user["id"]
        request(client, "ack", {"message_id": incoming["data"]["id"]})
        assert receive(client)["type"] == "error"
