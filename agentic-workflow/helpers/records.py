#!/usr/bin/env python3
"""Start a new implementation with allocate; resume a task with resolve.

Choose a subcommand; read its --help for arguments and restrictions.

Allocates directories or resolves an existing task and attempts native capture;
starts no service.

Prints the selected path; capture diagnostics go to stderr. Exit 0 means
success, not complete telemetry; exit 2 means invalid input or an operation
error (stderr).

Retain the returned path for later commands.

Examples:
  python3 agentic-workflow/helpers/records.py allocate example
  python3 agentic-workflow/helpers/records.py resolve .agentic-workflow/records/001_example 01_task
"""
import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import tempfile
import sys


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError(f'unsafe identifier: {value!r}')
    return value


@contextmanager
def locked(path):
    """Serialize allocation/native capture/report refresh; locks release on process exit."""
    flags = os.O_RDONLY if Path(path).is_dir() else os.O_WRONLY | os.O_CREAT
    descriptor = os.open(path, flags, 0o666)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def write_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb' if isinstance(data, bytes) else 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def report_capture(diagnostics):
    for diagnostic in diagnostics:
        print('records: ' + diagnostic['code'], file=sys.stderr)
        if diagnostic['code'] == 'current_session_unavailable':
            print('records: run capture in an OpenCode agent shell with OPENCODE_SESSION_ID; see '
                  'agentic-workflow/guides/TRACING.md#enable-opencode-capture', file=sys.stderr)
        elif diagnostic['code'] == 'opencode_export_unavailable':
            print('records: check opencode session export SESSION_ID and the selected session; '
                  'saved evidence is retained', file=sys.stderr)


def allocate(records_root, name):
    identifier(name)
    records_root = Path(records_root)
    records_root.mkdir(parents=True, exist_ok=True)
    with locked(records_root):
        numbers = [int(match[1]) for p in records_root.iterdir()
                   if p.is_dir() and (match := re.fullmatch(r'(\d{3,})_.+', p.name))]
        root = records_root / f'{max(numbers, default=0) + 1:03d}_{name}'
        root.mkdir()  # Reserve before writing; an interrupted allocation is not reused.
        for directory in ('tasks', 'runs', 'reports'):
            (root / directory).mkdir()
        from native_traces import capture_current
        with locked(root / '.records.lock'):
            capture_diagnostics = capture_current(root)
        report_capture(capture_diagnostics)
    return root


def resolve_task(root, task):
    root = Path(root)
    target = root / 'tasks' / identifier(task)
    if not target.is_dir() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('task absent from identified implementation')
    from native_traces import capture_current
    with locked(root / '.records.lock'):
        report_capture(capture_current(root))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    allocate_parser = commands.add_parser('allocate',
        formatter_class=argparse.RawDescriptionHelpFormatter, description="""Start new work; every call creates a new implementation, even for the same
name.

name starts with an ASCII letter/digit and contains only ASCII letters, digits,
_, . or -; --records-root defaults to .agentic-workflow/records in the cwd.

Creates --records-root/<NNN>_<name>/ with tasks/, runs/, reports/ and
.records.lock; NNN is the next numeric prefix (at least three digits). Attempts
to save the current native turn and session metadata under
<NNN>_<name>/native/<session-id>/<turn-id>.jsonl (Codex) or .json (OpenCode);
OpenCode 2.2.6 supplies OPENCODE_SESSION_ID in agent shells. Starts no service.

Prints the implementation path. Exit 0 means allocation succeeded, not complete
telemetry; best-effort capture diagnostics go to stderr. Exit 2 means invalid
input or an operation error (stderr).

Retain and reuse the printed path for tasks, reports and repairs; use resolve
to resume an existing task instead of allocating again.

Example: python3 agentic-workflow/helpers/records.py allocate example
""")
    allocate_parser.add_argument('name', help='implementation name (safe identifier)')
    allocate_parser.add_argument('--records-root', type=Path, default=Path('.agentic-workflow/records'),
                                 help='records directory (default: .agentic-workflow/records)')
    resolve_parser = commands.add_parser('resolve',
        formatter_class=argparse.RawDescriptionHelpFormatter, description="""Resume a known task in an existing implementation.

implementation is the allocated implementation path; task is an existing
directory name under implementation/tasks/. task starts with an ASCII
letter/digit and contains only ASCII letters, digits, _, . or -.

Requires implementation/tasks/<task>/ to exist within implementation; creates
no task. Creates/uses implementation/.records.lock and attempts to save the
current native turn and session metadata to implementation/native/<session-
id>/<turn-id>.jsonl (Codex) or .json (OpenCode); OpenCode 2.2.6 supplies
OPENCODE_SESSION_ID in agent shells. Starts no service.

Prints the task path. Exit 0 means resolution succeeded, not complete
telemetry; best-effort capture diagnostics go to stderr. Exit 2 means invalid
input, absent task or an operation error (stderr).

Use the returned task path and retain implementation for reports/repairs.

Example: python3 agentic-workflow/helpers/records.py resolve .agentic-workflow/records/001_example 01_task
""")
    resolve_parser.add_argument('implementation', type=Path, help='existing implementation directory')
    resolve_parser.add_argument('task', help='existing task directory name (safe identifier)')
    args = parser.parse_args()
    try:
        if args.command == 'allocate':
            print(allocate(args.records_root, args.name))
        else:
            print(resolve_task(args.implementation, args.task))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'records: {exc}\n')


if __name__ == '__main__':
    main()
