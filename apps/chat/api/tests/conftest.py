import socket
import threading
import time
from contextlib import contextmanager

import pytest
from websockets.sync.client import connect

from chat.api import create_app
from chat.server import create_server


@contextmanager
def running_server():
    app = create_app()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = create_server(app, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Server did not start")
            time.sleep(0.01)
        yield f"ws://127.0.0.1:{port}/ws", port
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        listener.close()
        assert not thread.is_alive(), "Server failed to shut down"


@pytest.fixture
def server():
    with running_server() as running:
        yield running


@pytest.fixture
def clients(server):
    with connect(server[0]) as alice, connect(server[0]) as bob:
        yield alice, bob
