import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from chat_client.protocol import decode_event


def message_data():
    return {
        "id": "6ab59054-8e3c-4b20-9a11-32922d384f68",
        "sender_id": "636dc4d7-ddcc-48a5-b597-5d2bd95f6163",
        "recipient_id": "bd981c3b-9620-4970-a22e-05ce9c7d139c",
        "text": "Hi Bob",
        "client_sent_at": 0,
        "server_received_at": "2026-11-08T12:00:00Z",
        "recipient_received_at": None,
        "server_ack_received_at": None,
    }


def test_records_preserve_uuid_utc_zero_and_null_wire_alternatives():
    raw = {
        "type": "message_received",
        "data": {**message_data(), "sender_name": "alice"},
    }
    before = datetime.now(UTC)
    event, decoded_at = decode_event(json.dumps(raw))
    assert isinstance(event.data.id, UUID)
    assert event.data.client_sent_at == 0
    assert event.data.recipient_received_at is None
    assert before <= decoded_at <= datetime.now(UTC)
    assert json.loads(event.model_dump_json()) == raw


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("server_received_at", 0),
        ("client_sent_at", 123),
        ("client_sent_at", False),
        ("client_sent_at", "123"),
        ("server_received_at", "2026-11-08T12:00:00"),
        ("recipient_received_at", "2026-11-08T12:00:00+03:00"),
        ("id", "bad-id"),
    ],
)
def test_invalid_wire_records_are_rejected(field, invalid):
    data = {**message_data(), "sender_name": "alice"}
    data[field] = invalid
    with pytest.raises(ValidationError):
        decode_event(json.dumps({"type": "message_received", "data": data}))
