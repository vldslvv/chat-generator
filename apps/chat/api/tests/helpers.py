import json
from uuid import uuid4


def request(client, kind, data, correlation=None):
    correlation = correlation or str(uuid4())
    client.send(json.dumps({"type": kind, "correlation_id": correlation, "data": data}))
    return correlation


def receive(client):
    return json.loads(client.recv(timeout=2))


def login(client, name):
    correlation = request(client, "login", {"name": name})
    reply = receive(client)
    assert reply["type"] == "login_ok"
    assert reply["correlation_id"] == correlation
    assert reply["data"]["name"] == name
    return reply["data"]


def sent_message(alice, bob, *, expected_sender="alice", **extra):
    correlation = request(alice, "send", {"recipient": "bob", "text": "hello 🌎", **extra})
    accepted, incoming = receive(alice), receive(bob)
    assert accepted["type"] == "message_accepted"
    assert accepted["correlation_id"] == correlation
    assert "sender_name" not in accepted["data"]
    assert incoming == {
        "type": "message_received",
        "data": {**accepted["data"], "sender_name": expected_sender},
    }
    return accepted["data"]
