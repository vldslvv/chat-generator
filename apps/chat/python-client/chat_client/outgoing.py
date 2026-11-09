"""Retain sends until acceptance and flush only the authenticated user's queue."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from .protocol import Request, send_request
from .state import ClientState, QueuedMessage, SessionState


def enqueue(state: ClientState, recipient: str, text: str) -> None:
    if state.session_state == SessionState.LOGGED_IN:
        assert state.authenticated_user is not None
        sender = state.authenticated_user.name
    else:
        sender = state.remembered_username
    assert sender is not None
    state.outgoing_queue.append(QueuedMessage(sender, recipient, text))


async def flush_messages(
    state: ClientState, write: Callable[[Request], Awaitable[None]]
) -> None:
    socket = state.connection
    # Select each next entry after transmitting: replies can remove entries while
    # transport backpressure yields, and new sends may append to the same queue.
    while (
        state.connection is socket
        and state.session_state == SessionState.LOGGED_IN
        and state.authenticated_user is not None
    ):
        entry = next(
            (
                entry
                for entry in state.outgoing_queue
                if entry.sender_name == state.authenticated_user.name
                and entry.correlation_id is None
            ),
            None,
        )
        if entry is None:
            return
        request = send_request(entry.recipient, entry.text)
        entry.correlation_id = request.correlation_id
        await write(request)


def accept(state: ClientState, correlation_id: UUID) -> None:
    for index, entry in enumerate(state.outgoing_queue):
        if entry.correlation_id == correlation_id:
            del state.outgoing_queue[index]
            return
    raise ValueError("Unexpected send reply")


def outstanding_correlation(state: ClientState) -> UUID | None:
    return next(
        (
            entry.correlation_id
            for entry in state.outgoing_queue
            if entry.correlation_id is not None
        ),
        None,
    )
