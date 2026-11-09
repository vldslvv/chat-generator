"""Observe retention and retries through the real CLI and WebSocket boundary."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aiohttp import WSMsgType, web
from test_cli import client, next_item, reply, server
from test_protocol import message_data


async def test_offline_fifo_acceptance_errors_and_user_isolation():
    sockets = asyncio.Queue()
    requests = asyncio.Queue()

    async def handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        login = await ws.receive_json()
        await ws.send_json(
            reply(
                "login_ok", login, {"id": str(uuid4()), "name": login["data"]["name"]}
            )
        )
        await sockets.put(ws)
        async for frame in ws:
            await requests.put(frame.json())
        return ws

    async with server(handler) as url, client(url) as cli:
        await cli.command("/connect alice")
        await next_item(sockets)
        await cli.until("Logged in as alice")
        await cli.command("/disconnect")
        await cli.until("Disconnected")
        for recipient, text in [("bob", "first  message  "), ("carol", "second")]:
            await cli.command(f"/send {recipient} {text}")
            await cli.until("✓ Queued locally")
        assert requests.empty()

        # Another login must neither transmit nor discard Alice's entries.
        await cli.command("/connect bob")
        bob = await next_item(sockets)
        await cli.until("Logged in as bob")
        await cli.command("/send alice bob's message")
        bob_send = await next_item(requests)
        assert bob_send["data"]["text"] == "bob's message"
        await bob.send_json(reply("message_accepted", bob_send, message_data()))
        await cli.until("✓ Accepted")
        assert requests.empty()
        await cli.command("/disconnect")
        await cli.until("Disconnected")

        before_flush = datetime.now(UTC)
        await cli.command("/connect alice")
        alice = await next_item(sockets)
        await cli.until("Logged in as alice")
        first, second = await next_item(requests), await next_item(requests)
        assert [
            (m["data"]["recipient"], m["data"]["text"]) for m in [first, second]
        ] == [
            ("bob", "first  message  "),
            ("carol", "second"),
        ]
        for send in [first, second]:
            assert (
                before_flush
                <= datetime.fromisoformat(send["data"]["client_sent_at"])
                <= datetime.now(UTC)
            )
        assert first["correlation_id"] != second["correlation_id"]

        # A stale acceptance must not remove any entry; matching may be out of order.
        unrelated = {"correlation_id": str(uuid4())}
        await alice.send_json(reply("message_accepted", unrelated, message_data()))
        assert unrelated["correlation_id"] in await cli.error_until(
            "Unexpected send reply"
        )
        await alice.send_json(reply("message_accepted", second, message_data()))
        await cli.until("✓ Accepted")
        await alice.send_json(reply("error", first, {"message": "Recipient rejected"}))
        assert first["correlation_id"] in await cli.error_until("Recipient rejected")
        await cli.command("/send bob third")
        third = await next_item(requests)
        assert third["data"]["text"] == "third"
        await cli.status()
        assert requests.empty(), "Rejected entry retried on the same connection"

        # Abrupt loss keeps the rejected and unaccepted entries, clearing attempts.
        alice._req.transport.abort()
        await cli.until("Disconnected")
        await cli.command("/send bob fourth")
        await cli.until("✓ Queued locally")
        retry_at = datetime.now(UTC)
        await cli.command("/connect")
        alice = await next_item(sockets)
        await cli.until("Logged in as alice")
        retries = [await next_item(requests) for _ in range(3)]
        assert [item["data"]["text"] for item in retries] == [
            "first  message  ",
            "third",
            "fourth",
        ]
        initial_ids = {
            first["correlation_id"],
            second["correlation_id"],
            third["correlation_id"],
        }
        retry_ids = {item["correlation_id"] for item in retries}
        assert initial_ids.isdisjoint(retry_ids)
        assert len(retry_ids) == 3
        assert all(UUID(value) for value in retry_ids)
        for item in retries:
            assert (
                retry_at
                <= datetime.fromisoformat(item["data"]["client_sent_at"])
                <= datetime.now(UTC)
            )
            await alice.send_json(reply("message_accepted", item, message_data()))
            await cli.until("✓ Accepted")
        await cli.command("/disconnect")
        await cli.until("Disconnected")
        await cli.command("/connect")
        await next_item(sockets)
        await cli.until("Logged in as alice")
        await cli.status()
        assert requests.empty(), "Accepted entries must never be resent"
        assert sum("Recipient rejected" in line for line in cli.diagnostics) == 1
        assert sum("Unexpected send reply" in line for line in cli.diagnostics) == 1


@pytest.mark.parametrize("flush_trigger", ["login", "send"])
async def test_backpressured_flush_keeps_events_commands_and_disconnect_responsive(
    flush_trigger,
):
    sockets = asyncio.Queue()
    frames = asyncio.Queue()
    release = asyncio.Event()
    connection_number = 0
    incoming_ids = []

    async def handler(request):
        nonlocal connection_number
        connection_number += 1
        number = connection_number
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        login = await ws.receive_json()
        await ws.send_json(
            reply("login_ok", login, {"id": str(uuid4()), "name": "alice"})
        )
        await sockets.put(ws)
        blocked_connection = 1 if flush_trigger == "send" else 2
        if number == blocked_connection:
            assert (await ws.receive_json())["type"] == "send"
            # Let outgoing sends saturate socket buffers before the burst.
            await asyncio.sleep(0.2)
            for index in range(3000):
                identifier = str(uuid4())
                incoming_ids.append(identifier)
                await ws.send_json(
                    {
                        "type": "message_received",
                        "data": {
                            **message_data(),
                            "id": identifier,
                            "sender_name": "bob",
                            "text": f"event during flush {index}",
                        },
                    }
                )
            await ws.ping(b"flush-heartbeat")
            await release.wait()
        async for frame in ws:
            await frames.put(
                {"type": "pong", "data": frame.data}
                if frame.type == WSMsgType.PONG
                else frame.json()
            )
        return ws

    async with server(handler) as url:
        try:
            async with client(url) as cli:
                await cli.command("/connect alice")
                await next_item(sockets)
                await cli.until("Logged in as alice")
                if flush_trigger == "login":
                    await cli.command("/disconnect")
                    await cli.until("Disconnected")
                # Exceed socket buffers so the real transport must yield while
                # the peer deliberately stops consuming sends.
                async with asyncio.timeout(4):
                    for _ in range(512):
                        await cli.command("/send bob " + "x" * 32768)
                        if flush_trigger == "login":
                            await cli.until("Queued locally")
                if flush_trigger == "login":
                    await cli.command("/connect")
                    await next_item(sockets)
                    await cli.until("Logged in as alice")
                await cli.until("← bob: event during flush 2999")
                status = await cli.status()
                assert "Session: logged in" in status
                async with asyncio.timeout(4):
                    while "Last heartbeat: never" in status:
                        status = await cli.status()
                if flush_trigger == "login":
                    resumed_at = datetime.now(UTC)
                    release.set()
                    acknowledgments = []
                    while True:
                        frame = await next_item(frames)
                        if frame["type"] == "pong":
                            assert frame["data"] == b"flush-heartbeat"
                            break
                        if frame["type"] == "ack":
                            acknowledgments.append(frame["data"]["message_id"])
                            assert (
                                datetime.fromisoformat(
                                    frame["data"]["recipient_received_at"]
                                )
                                <= resumed_at
                            )
                    assert acknowledgments == incoming_ids
                await cli.command("/drop-connection")
                await cli.until("Disconnected")
                assert "Connection: disconnected" in await cli.status()
                release.set()
                if flush_trigger == "send":
                    await cli.command("/connect")
                    await next_item(sockets)
                    await cli.until("Logged in as alice")
                    first_retry = await next_item(frames)
                    assert first_retry["type"] == "send", "Stale controls survived drop"
        finally:
            release.set()
