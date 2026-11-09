"""Cause-bearing stderr diagnostics without protocol or terminal dependencies."""

import logging
from uuid import UUID


def failure(action: str, cause: object, correlation_id: UUID | None = None) -> None:
    suffix = f" correlation_id={correlation_id}" if correlation_id is not None else ""
    description = str(cause) or type(cause).__name__
    if isinstance(cause, BaseException):
        description = f"{type(cause).__name__}: {description}"
    description = description.replace("\n", "\\n")
    logging.getLogger("chat_client").error("%s: %s%s", action, description, suffix)
