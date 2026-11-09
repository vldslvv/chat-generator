import pytest

from chat_client.terminal import Command, parse_command


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("/send bob hello  there  \n", Command("/send", ("bob", "hello  there  "))),
        ("/connect alice\n", Command("/connect", ("alice",))),
        ("/connect", Command("/connect")),
        ("  /status\n", Command("/status")),
        ("\n", Command("")),
    ],
)
def test_terminal_preserves_message_text_and_parses_commands(line, expected):
    assert parse_command(line) == expected


@pytest.mark.parametrize(
    "line",
    ["/send", "/send bob", "/send bob    ", "/connect alice bob", "/status x", "hi"],
)
def test_invalid_commands_are_rejected_locally(line):
    with pytest.raises(ValueError):
        parse_command(line)
