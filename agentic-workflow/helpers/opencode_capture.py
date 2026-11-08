"""Capture selected OpenCode turns through its export CLI, never by recency."""
import json
from pathlib import Path
import shutil
import subprocess

from records import identifier, write_atomic


def export_session(session):
    identifier(session)
    executable = shutil.which('opencode') or str(Path.home() / '.opencode/bin/opencode')
    result = subprocess.run([executable, 'session', 'export', session], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=20, check=True)
    data = json.loads(result.stdout)
    if data['info']['id'] != session or not isinstance(data['messages'], list):
        raise ValueError('OpenCode export identity mismatch')
    return data


def turns(data):
    """V2 idle markers delimit turns; steered prompts stay in the active turn."""
    result, active = {}, None
    for message in data['messages']:
        if active is None and message['type'] == 'user':
            active = message['id']
            result[active] = []
        if active is not None:
            result[active].append(message)
        if message['type'] == 'idle':
            active = None
    return result


def users(data):
    return [messages[0] for messages in turns(data).values()]


def selected_turn(data, turn):
    selected = turns(data).get(turn)
    if selected is None:
        raise ValueError('selected OpenCode turn unavailable')
    return dict(info=data['info'], messages=selected)


def save(root, data, turn):
    from native_traces import safe_destination
    selected = selected_turn(data, turn)
    path = safe_destination(root, Path(root) / 'native' / identifier(data['info']['id']) /
                            (identifier(turn) + '.json'))
    if path.exists():
        previous = json.loads(path.read_text())
        # A partial export or removed host history must not erase saved evidence.
        old = {m['id']: {p['id'] for p in m.get('content', []) if p['type'] == 'tool'} for m in previous['messages']}
        new = {m['id']: {p['id'] for p in m.get('content', []) if p['type'] == 'tool'} for m in selected['messages']}
        if any(mid not in new or not parts <= new[mid] for mid, parts in old.items()):
            raise ValueError('OpenCode export lost saved observations')
    content = json.dumps(selected, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text() != content:
        write_atomic(path, content)
    return selected


EXPORT_ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)


def capture_current(root, session):
    from native_traces import gap
    try:
        data = export_session(session)
        prompts = users(data)
        if not prompts:
            return [gap('active_turn_unavailable', session)]
        # OpenCode exports messages in native chronological order.
        save(root, data, prompts[-1]['id'])
        return []
    except EXPORT_ERRORS:
        return [gap('opencode_export_unavailable', session)]


def refresh(root, sources):
    """Refresh canonical captures and follow task calls from selected turns only."""
    from native_traces import gap
    diagnostics, cache, seen = [], {}, set()

    def load(session):
        if session not in cache:
            cache[session] = None
            try:
                cache[session] = export_session(session)
            except EXPORT_ERRORS:
                diagnostics.append(gap('opencode_export_unavailable', session))
        return cache[session]

    pending = [(s['session_id'], t) for s in sources for t in s['turn_ids']
               if s['path'] == f"native/{s['session_id']}/{t}.json"]
    while pending:
        session, turn = pending.pop()
        if (session, turn) in seen:
            continue
        seen.add((session, turn))
        data = load(session)
        if data is None:
            continue
        try:
            selected = save(root, data, turn)
        except EXPORT_ERRORS:
            diagnostics.append(gap('opencode_turn_unavailable', session, turn))
            continue
        for message in selected['messages']:
            for part in message.get('content', []):
                if part.get('type') != 'tool' or part.get('name') != 'subagent':
                    continue
                state = part.get('state') or {}
                child = (state.get('metadata') or {}).get('sessionID')
                if not child:
                    diagnostics.append(gap('opencode_dispatch_unresolved', session, turn))
                    continue
                target = load(child)
                if target is None:
                    continue
                if target['info'].get('parentID') != session:
                    diagnostics.append(gap('opencode_parent_mismatch', child))
                    continue
                time = part.get('time') or {}
                start, end = time.get('ran', time.get('created')), time.get('completed')
                candidates = [m['id'] for m in users(target)
                              if isinstance(start, (int, float))
                              and start <= m.get('time', {}).get('created', -1)
                              and (end is None or m['time']['created'] <= end)]
                if len(candidates) != 1:
                    diagnostics.append(gap('ambiguous_dispatch_turn', child))
                else:
                    pending.append((child, candidates[0]))
    return diagnostics
