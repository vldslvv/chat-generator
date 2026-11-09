import asyncio
import json
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from chat.api import create_app


class ASGIClient:
    def __init__(self, intercept):
        self.inbound = asyncio.Queue()
        self.outbound = asyncio.Queue()
        self.intercept = intercept

    async def send_frame(self, frame):
        if frame["type"] == "websocket.send":
            event = json.loads(frame["text"])
            if self.intercept is not None:
                await self.intercept(event)
            await self.outbound.put(event)

    async def receive_frame(self):
        frame = await self.inbound.get()
        self.inbound.task_done()
        return frame

    def request(self, kind, data):
        correlation = str(uuid4())
        self.inbound.put_nowait(
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": kind, "correlation_id": correlation, "data": data}),
            }
        )
        return correlation

    async def receive(self, timeout=2):
        return await asyncio.wait_for(self.outbound.get(), timeout)

    async def login(self, name):
        correlation = self.request("login", {"name": name})
        result = await self.receive()
        assert result["type"] == "login_ok"
        assert result["correlation_id"] == correlation
        return result["data"]


@asynccontextmanager
async def connected(app, intercept=None):
    # The public ASGI boundary permits deterministic failures and scheduling
    # barriers without changing application state or introducing test hooks.
    client = ASGIClient(intercept)
    client.inbound.put_nowait({"type": "websocket.connect"})
    scope = {"type": "websocket", "path": "/ws", "headers": [], "query_string": b""}
    task = asyncio.create_task(app(scope, client.receive_frame, client.send_frame))
    try:
        yield client
    finally:
        client.inbound.put_nowait({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, 2)


@pytest.mark.parametrize("blocked_event", ["login_ok", "message_received"])
def test_login_replay_finishes_before_new_delivery(blocked_event):
    async def scenario():
        app = create_app()
        async with connected(app) as alice:
            await alice.login("alice")
            async with connected(app) as bob:
                await bob.login("bob")
            messages = []
            for text in ["old first", "old second"]:
                alice.request("send", {"recipient": "bob", "text": text})
                accepted = await alice.receive()
                assert accepted["type"] == "message_accepted"
                messages.append(accepted["data"])

            blocked, release = asyncio.Event(), asyncio.Event()

            async def pause(event):
                if event["type"] == blocked_event and not blocked.is_set():
                    blocked.set()
                    await release.wait()

            async with connected(app, pause) as bob:
                login_correlation = bob.request("login", {"name": "bob"})
                await asyncio.wait_for(blocked.wait(), 2)
                alice.request("send", {"recipient": "bob", "text": "new"})
                try:
                    # Deliver the new request to ASGI before releasing the old
                    # notification; sender acceptance may arrive at either time.
                    await asyncio.wait_for(alice.inbound.join(), 2)
                finally:
                    release.set()
                events = [await bob.receive() for _ in range(4)]
                replies = [event for event in events if event["type"] == "login_ok"]
                assert len(replies) == 1
                assert replies[0]["correlation_id"] == login_correlation
                received = [event for event in events if event["type"] == "message_received"]
                newer = await alice.receive()
                assert newer["type"] == "message_accepted"
                messages.append(newer["data"])
                assert received == [
                    {"type": "message_received", "data": {**message, "sender_name": "alice"}}
                    for message in messages
                ]

    asyncio.run(scenario())


def test_delivery_failure_is_accepted_logged_and_replayed_after_reconnect(caplog):
    failed_attempts = []

    async def fail_delivery(event):
        if event["type"] == "message_received":
            failed_attempts.append(event)
            raise OSError("recipient transport lost")

    async def scenario():
        app = create_app()
        async with connected(app) as alice:
            await alice.login("alice")
            async with connected(app, fail_delivery) as bob:
                original = await bob.login("bob")
                correlation = alice.request("send", {"recipient": "bob", "text": "retained"})
                accepted = await alice.receive()
                assert accepted["type"] == "message_accepted"
                assert accepted["correlation_id"] == correlation
                assert accepted["data"]["server_ack_received_at"] is None
                # A later request confirms the failed attempt has completed.
                alice.request("login", {"name": "alice"})
                assert (await alice.receive())["type"] == "error"
                assert len(failed_attempts) == 1
                with pytest.raises(TimeoutError):
                    await alice.receive(timeout=0.05)
            async with connected(app) as bob:
                assert await bob.login("bob") == original
                assert await bob.receive() == {
                    "type": "message_received",
                    "data": {**accepted["data"], "sender_name": "alice"},
                }
                with pytest.raises(TimeoutError):
                    await bob.receive(timeout=0.05)
            return correlation

    with caplog.at_level(logging.INFO, logger="chat.delivery"):
        correlation = asyncio.run(scenario())
    assert any(
        "Delivery attempt" in record.message and correlation in record.message
        for record in caplog.records
    )
    assert any(
        "Delivery failed" in record.message
        and correlation in record.message
        and record.levelno >= logging.WARNING
        for record in caplog.records
    )
    assert "recipient transport lost" in caplog.text
    assert "Delivery succeeded" in caplog.text


def test_sender_reply_failure_does_not_suppress_online_delivery(caplog):
    async def lose_acceptance(event):
        if event["type"] == "message_accepted":
            raise OSError("sender acceptance transport lost")

    async def scenario():
        app = create_app()
        async with connected(app) as bob:
            await bob.login("bob")
            async with connected(app, lose_acceptance) as alice:
                sender = await alice.login("alice")
                correlation = alice.request("send", {"recipient": "bob", "text": "deliver now"})
                incoming = await bob.receive()
                assert incoming["type"] == "message_received"
                assert "correlation_id" not in incoming
                assert incoming["data"]["sender_id"] == sender["id"]
                assert incoming["data"]["sender_name"] == "alice"
                assert incoming["data"]["text"] == "deliver now"
                assert incoming["data"]["server_ack_received_at"] is None
                return correlation

    correlation = asyncio.run(scenario())
    assert "sender acceptance transport lost" in caplog.text
    assert any(
        "WebSocket operation failed" in record.message and correlation in record.message
        for record in caplog.records
    )
