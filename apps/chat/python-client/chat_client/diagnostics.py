"""Readable cause-bearing stderr diagnostics."""

from uuid import UUID

from .terminal import output


class ReportedFailure(Exception):
    """An I/O failure whose user-facing diagnostic has already been emitted."""


def describe(cause: object) -> str:
    return (str(cause) or "operation timed out").replace("\n", "\\n")


async def failure(
    action: str, cause: object, correlation_id: UUID | None = None
) -> None:
    suffix = f" correlation_id={correlation_id}" if correlation_id is not None else ""
    prefix = f"{action}: " if action else ""
    await output(f"✗ Error: {prefix}{describe(cause)}{suffix}", error=True)
