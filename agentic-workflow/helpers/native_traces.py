"""Native file discovery, selection and collection; no usage accounting.

Codex's read-only SQLite index resolves identities. Saved JSONL records remain
byte-for-byte native records, partitioned by session/turn. Exports live in native/.
Native evidence selects scope; optional annotations recover opaque assignments.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from records import identifier, write_atomic
from trace_adapters import stamp


def gap(code, session=None, turn=None):
    return dict(code=code, session_id=session, turn_id=turn)


def object_value(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def lineage(meta):
    origin = object_value(meta.get('source'))
    spawn = (origin.get('subagent') or {}).get('thread_spawn') or {}
    return (meta.get('parent_thread_id') or spawn.get('parent_thread_id'),
            meta.get('agent_path') or spawn.get('agent_path'))


def native_index():
    """Read only identity/path/parent metadata, never search by cwd or recency."""
    home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    databases = sorted(home.glob('state_*.sqlite'), key=lambda p: int(p.stem.split('_')[-1]), reverse=True)
    if not databases:
        raise OSError('native index unavailable')
    with closing(sqlite3.connect(databases[0].resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA query_only=ON')
        columns = {r[1] for r in connection.execute('PRAGMA table_info(threads)')}
        fields = ['id', 'rollout_path', 'source'] + [f for f in ('agent_path',) if f in columns]
        rows = [dict(zip(fields, r)) for r in connection.execute('SELECT ' + ','.join(fields) + ' FROM threads')]
    return {r['id']: r for r in rows}


def codex_document(path):
    """Keep raw lines separately from parsed selection metadata, including tails."""
    path = Path(path)
    raw_rows = path.read_bytes().splitlines(keepends=True)
    meta, records, active = None, [], None
    for raw in raw_rows:
        try:
            row = json.loads(raw)
            if not isinstance(row, dict) or not isinstance(row.get('payload'), dict):
                raise ValueError('invalid native record')
        except (ValueError, UnicodeError):
            records.append((active, None, raw))
            continue
        p = row['payload']
        if row['type'] == 'session_meta':
            if meta and meta.get('id') != p.get('id'):
                raise ValueError('ambiguous native session metadata')
            meta = p
            records.append((None, row, raw))
            continue
        if row['type'] == 'turn_context' or (row['type'] == 'event_msg' and p.get('type') == 'task_started'):
            active = p.get('turn_id', active)
        turn = p.get('turn_id') or (p.get('internal_chat_message_metadata_passthrough') or {}).get('turn_id') or active
        records.append((turn, row, raw))
    if not meta or not meta.get('id'):
        raise ValueError('native file needs session metadata')
    sid = identifier(meta['id'])
    foreign = {turn for turn, row, _ in records if row and row['type'] == 'token_usage_record'
               and row['payload'].get('thread_id', sid) != sid}
    creation = stamp(meta.get('timestamp'))
    turns = []
    for turn, row, _ in records:
        if not turn or turn in foreign:
            continue
        if meta.get('forked_from_id'):
            # Forks can copy parent history. Native creation bounds that history;
            # it never establishes a relationship to another session.
            t = stamp(row.get('timestamp')) if row else None
            if creation is None or t is None or t < creation:
                continue
        if turn not in turns:
            turns.append(identifier(turn))
    return dict(path=path, meta=meta, session_id=sid, records=records, turns=turns)


def saved_documents(root):
    documents, exports = [], []
    for path in sorted((Path(root) / 'native').rglob('*')):
        if not path.is_file():
            continue
        local_path(root, path)
        if path.suffix == '.jsonl':
            documents.append(codex_document(path))
        elif path.suffix == '.json':
            data = json.loads(path.read_text())
            info = data['info']
            legacy = 'version' in info
            if legacy:
                turns = [m['info']['id'] for m in data['messages'] if m['info']['role'] == 'user'
                         and m['info'].get('sessionID') == info['id']]
            else:
                from opencode_capture import turns as opencode_turns
                turns = list(opencode_turns(data))
            exports.append(dict(id=str(path.relative_to(root)), path=str(path.relative_to(root)),
                                adapter='opencode', session_id=info['id'], turn_ids=turns,
                                source_version='opencode-export-' + str(info.get('version', 'v2'))))
    return documents, exports


def local_path(root, path):
    """Resolve the chosen root, rejecting aliases at every component inside it."""
    boundary = Path(root).absolute()
    try:
        relative = Path(path).absolute().relative_to(boundary)
    except ValueError:
        raise ValueError('path escapes implementation root') from None
    current = boundary.resolve()
    for part in relative.parts:
        if part == '..':
            raise ValueError('path escapes implementation root')
        current /= part
        if current.is_symlink():
            raise ValueError('path contains a filesystem alias')
    return current


def safe_destination(root, path):
    path = local_path(root, path)
    # Hard links can alias host logs even when paths are contained.
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError('output aliases another file')
    return path


def save_turn(root, document, turn):
    if turn not in document['turns']:
        return False
    sid = document['session_id']
    path = safe_destination(root, Path(root) / 'native' / identifier(sid) / (identifier(turn) + '.jsonl'))
    content = b''.join(raw for tid, row, raw in document['records']
                       if (row and row['type'] == 'session_meta') or tid == turn)
    if path.exists():
        old = path.read_bytes()
        # An active writer may expose an incomplete final record, or an index
        # can briefly point at a shorter rollout. Keep already captured evidence.
        if old.startswith(content) and len(old) > len(content):
            return False
        if old == content:
            return False
    write_atomic(path, content)
    return True


def capture_current(root):
    opencode_session = os.environ.get('OPENCODE_SESSION_ID')
    if opencode_session:
        from opencode_capture import capture_current as capture_opencode
        return capture_opencode(root, opencode_session)
    sid = os.environ.get('CODEX_THREAD_ID')
    if not sid:
        return [gap('current_session_unavailable')]
    try:
        entry = native_index().get(sid)
        if not entry:
            return [gap('native_identity_unresolved', sid)]
        doc = codex_document(entry['rollout_path'])
        if doc['session_id'] != sid:
            return [gap('native_identity_mismatch', sid)]
        if not doc['turns']:
            return [gap('active_turn_unavailable', sid)]
        save_turn(root, doc, doc['turns'][-1])
        return []
    except (OSError, sqlite3.Error):
        return [gap('native_storage_unavailable', sid)]
    except ValueError:
        return [gap('invalid_native_source', sid)]


def message_text(payload):
    content = payload.get('content') or []
    return '\n'.join(part.get('text', '') for part in content if isinstance(part, dict)) if isinstance(content, list) else ''


def assignment_message(payload, agent_path):
    return (payload.get('role') in ('user', 'assistant') or
            (payload.get('type') == 'agent_message' and agent_path is not None
             and payload.get('recipient') == agent_path))


def annotate_assignments(root, sources, assignments):
    """Fill only missing selected assignments; never select evidence or override tags."""
    path = local_path(root, root / 'assignment-annotations.json')
    if not path.exists():
        return
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('assignments'), list):
        raise ValueError('invalid assignment annotations: expected version 1 and assignments list')
    selected = {(s['adapter'], s['session_id'], t) for s in sources for t in s['turn_ids']}
    seen = set()
    for entry in data['assignments']:
        if not isinstance(entry, dict):
            raise ValueError('invalid assignment annotation')
        key = tuple(entry.get(k) for k in ('adapter', 'session_id', 'turn_id'))
        for value in key:
            identifier(value)
        if key not in selected or key in seen:
            raise ValueError('assignment annotation needs a unique selected native turn')
        seen.add(key)
        tag = {k: identifier(entry.get(k)) for k in ('task', 'role')}
        tag['implementation'] = root.name
        if 'purpose' in entry:
            if not isinstance(entry['purpose'], str) or len(entry['purpose']) > 500:
                raise ValueError('invalid annotation purpose')
            tag['purpose'] = entry['purpose']
        evidence = entry.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('assignment annotation needs evidence paths')
        for reference in evidence:
            if (not isinstance(reference, str) or not reference or Path(reference).is_absolute()
                    or not local_path(root, root / reference).is_file()):
                raise ValueError('assignment annotation needs implementation-local evidence files')
        native_key = key[1:]
        if assignments.get(native_key):
            raise ValueError('assignment annotation conflicts with a native assignment')
        assignments[native_key] = dict(tag, source='annotation', evidence=evidence)


def observed_agent_paths(documents, diagnostics):
    """Resolve paths by explicit native identity, including activity about the root."""
    paths = {}
    for doc in documents:
        sid, path = doc['session_id'], lineage(doc['meta'])[1]
        if path:
            paths.setdefault(sid, set()).add(path)
        for turn, row, _ in doc['records']:
            if turn not in doc['turns'] or not row or row['type'] != 'event_msg':
                continue
            item = row['payload'].get('item') or {}
            if item.get('type') == 'SubAgentActivity' and item.get('agent_thread_id') and item.get('agent_path'):
                paths.setdefault(item['agent_thread_id'], set()).add(item['agent_path'])
    resolved = {}
    for sid, values in paths.items():
        if len(values) == 1:
            resolved[sid] = next(iter(values))
        else:
            diagnostics.append(gap('ambiguous_native_agent_path', sid))
    return resolved


def assignment_tag(text, implementation):
    tags = []
    invalid = False
    for line in text.splitlines():
        if not line.startswith('AGENTIC_WORKFLOW '):
            continue
        value = object_value(line.partition(' ')[2])
        try:
            for field in ('implementation', 'task', 'role'):
                identifier(value.get(field))
            if 'purpose' in value and (not isinstance(value['purpose'], str) or len(value['purpose']) > 500):
                raise ValueError('invalid purpose')
        except ValueError:
            invalid = True
            continue
        if value['implementation'] == implementation:
            tags.append(value)
    unique = {json.dumps(t, sort_keys=True): t for t in tags}
    return (next(iter(unique.values())) if len(unique) == 1 else None,
            invalid or len(unique) > 1)


def dispatches(document, selected):
    results, calls = {}, []
    for turn, row, _ in document['records']:
        if turn not in selected or not row or row['type'] != 'response_item':
            continue
        p = row['payload']
        if p.get('type') in ('function_call_output', 'custom_tool_call_output'):
            results[p.get('call_id')] = object_value(p.get('output'))
        name = p.get('name', '').rsplit('.', 1)[-1]
        if p.get('type') in ('function_call', 'custom_tool_call') and name in ('spawn_agent', 'followup_task', 'send_message'):
            calls.append(dict(kind=name, arguments=object_value(p.get('arguments') or p.get('input')),
                              call_id=p.get('call_id'), timestamp=stamp(row.get('timestamp')), turn=turn))
    for call in calls:
        call['result'] = results.get(call['call_id'], {})
    return calls


def dispatch_turn(document, call, before=None):
    """Use returned native turn IDs or matching delivered messages before timing.

    A single new native turn following a dispatch is resolvable once identity is
    proven. Multiple possible turns remain ambiguous; never select all of them.
    """
    explicit = call['result'].get('turn_id')
    if explicit:
        return explicit if explicit in document['turns'] else None
    message = call['arguments'].get('message')
    mid = call['result'].get('message_id')
    matches = [tid for tid, row, _ in document['records']
               if tid in document['turns'] and row and row['type'] == 'response_item'
               and row['payload'].get('role') == 'user'
               and ((mid and row['payload'].get('id') == mid) or
                    (message and message_text(row['payload']) == message))
               and (before is None or (stamp(row.get('timestamp')) is not None
                                        and stamp(row['timestamp']) < before))
               and (call['timestamp'] is None or stamp(row.get('timestamp')) is None
                    or stamp(row['timestamp']) >= call['timestamp'])]
    matches = list(dict.fromkeys(matches))
    if len(matches) == 1:
        return matches[0]
    if call['kind'] == 'spawn_agent':
        return document['turns'][0] if document['turns'] else None
    candidates = []
    for turn in document['turns']:
        starts = [stamp(row.get('timestamp')) for tid, row, _ in document['records']
                  if tid == turn and row and row['type'] == 'event_msg' and row['payload'].get('type') == 'task_started']
        if starts and starts[0] is not None and call['timestamp'] is not None and starts[0] >= call['timestamp'] and (before is None or starts[0] < before):
            candidates.append(turn)
    if len(candidates) == 1 and call['kind'] == 'followup_task':
        return candidates[0]
    if call['kind'] in ('send_message', 'followup_task') and call['timestamp'] is not None:
        active = []
        for turn in document['turns']:
            starts, ends = [], []
            for tid, row, _ in document['records']:
                if tid != turn or not row or row['type'] != 'event_msg':
                    continue
                p, t = row['payload'], stamp(row.get('timestamp'))
                if t is None:
                    continue
                if p.get('type') == 'task_started':
                    starts.append(t)
                elif p.get('type') in ('task_complete', 'task_completed', 'turn_aborted'):
                    ends.append(t)
            if starts and min(starts) <= call['timestamp'] and (not ends or call['timestamp'] <= max(ends)):
                active.append(turn)
        if len(active) == 1:
            return active[0]
    return None


def collect(root):
    """Refresh saved selections and their proven dispatch descendants.

    Caller holds the implementation lock across collection and report writes.
    Returns source descriptors derived from native contents, assignment context
    and coverage diagnostics. These descriptors are never persisted.
    """
    root = Path(root)
    saved, exports = saved_documents(root)
    diagnostics, index = [], {}
    if exports:
        from opencode_capture import refresh as refresh_opencode
        diagnostics.extend(refresh_opencode(root, exports))
    if saved or not exports:
        try:
            index = native_index()
        except (OSError, sqlite3.Error):
            diagnostics.append(gap('native_storage_unavailable'))
    documents, selected = {}, {}
    for doc in saved:
        sid = doc['session_id']
        selected.setdefault(sid, set()).update(doc['turns'])
        if sid in documents:
            documents[sid]['records'].extend(doc['records'])
            documents[sid]['turns'] = list(dict.fromkeys(documents[sid]['turns'] + doc['turns']))
        else:
            documents[sid] = doc
    loaded, refreshed = set(), set()

    def load(sid):
        if sid in loaded:
            return documents.get(sid)
        loaded.add(sid)
        if sid not in index:
            if index:
                diagnostics.append(gap('native_identity_unresolved', sid))
            return documents.get(sid)
        try:
            doc = codex_document(index[sid]['rollout_path'])
            if doc['session_id'] != sid:
                diagnostics.append(gap('native_identity_mismatch', sid))
            else:
                documents[sid] = doc
                refreshed.add(sid)
        except (OSError, ValueError):
            diagnostics.append(gap('native_source_unavailable', sid))
        return documents.get(sid)

    for doc in documents.values():
        order = {}
        for turn, row, _ in doc['records']:
            if row and turn in doc['turns']:
                order.setdefault(turn, stamp(row.get('timestamp')) or 0)
        doc['turns'].sort(key=lambda turn: (order.get(turn, 0), turn))
    # Metadata from saved files also resolves descendants during offline analysis.
    candidates = dict(index)
    for sid, doc in documents.items():
        candidates.setdefault(sid, dict(doc['meta'], id=sid))

    def tree_root(sid):
        seen = set()
        while sid in candidates and sid not in seen:
            seen.add(sid)
            parent = lineage(candidates[sid])[0]
            if not parent:
                return sid
            sid = parent
        return sid

    assignments, requested, seen = {}, {}, set()
    changed = True
    while changed:
        changed = False
        for sid, turns in list(selected.items()):
            doc = load(sid)
            if not doc:
                continue
            calls = dispatches(doc, turns)
            for call in calls:
                key = (sid, call['call_id'])
                if key in seen:
                    continue
                seen.add(key)
                args, result = call['arguments'], call['result']
                if result.get('error') or result.get('status') in ('failed', 'error'):
                    continue
                target = result.get('agent_id') or result.get('thread_id')
                path = result.get('task_name') or result.get('agent_path') or args.get('target')
                if not target and path in candidates:
                    target = path
                if not target:
                    if not path and call['kind'] == 'spawn_agent' and args.get('task_name'):
                        path = (lineage(doc['meta'])[1] or '/root') + '/' + args['task_name']
                    if path and not path.startswith('/'):
                        path = (lineage(doc['meta'])[1] or '/root') + '/' + path
                    scope = tree_root(sid)
                    matches = [cid for cid, entry in candidates.items()
                               if (lineage(entry)[1] or ('/root' if cid == scope else None)) == path
                               and (lineage(entry)[0] == sid if call['kind'] == 'spawn_agent'
                                    else tree_root(cid) == scope)]
                    if len(matches) == 1:
                        target = matches[0]
                    else:
                        diagnostics.append(gap('ambiguous_native_identity' if matches else 'native_identity_unresolved', sid, call['turn']))
                        continue
                child = load(target)
                if not child:
                    diagnostics.append(gap('native_source_unavailable', target))
                    continue
                aliases = {target, lineage(child['meta'])[1]}
                next_dispatch = [c['timestamp'] for c in calls
                                 if c['timestamp'] is not None and call['timestamp'] is not None
                                 and c['timestamp'] > call['timestamp']
                                 and (c['arguments'].get('target') in aliases
                                      or c['arguments'].get('target') == (lineage(child['meta'])[1] or '').rsplit('/', 1)[-1])]
                turn = dispatch_turn(child, call, min(next_dispatch) if next_dispatch else None)
                if not turn:
                    diagnostics.append(gap('ambiguous_dispatch_turn', target))
                    continue
                if turn not in selected.setdefault(target, set()):
                    selected[target].add(turn)
                    changed = True
                tag, ambiguous = assignment_tag(args.get('message') or '', root.name)
                if ambiguous:
                    diagnostics.append(gap('ambiguous_assignment', target, turn))
                if tag:
                    previous = assignments.get((target, turn))
                    if previous and previous != tag:
                        diagnostics.append(gap('ambiguous_assignment', target, turn))
                        assignments[(target, turn)] = {}
                    else:
                        assignments[(target, turn)] = tag
                request = requested.setdefault((target, turn), {})
                request.update({k: args[k] for k in ('model', 'reasoning_effort') if args.get(k) is not None})
    # Capture only selected turns, including active partial logs. Host files are
    # read-only. Never overwrite explicitly supplied saved exports at other paths.
    for sid, turns in selected.items():
        if sid in refreshed:
            for turn in sorted(turns):
                if turn not in documents[sid]['turns']:
                    diagnostics.append(gap('native_turn_unavailable', sid, turn))
                else:
                    save_turn(root, documents[sid], turn)
    # Re-read the copies: parsing and reports must describe the saved evidence.
    saved, exports = saved_documents(root)
    sources = list(exports)
    if not saved and not exports:
        diagnostics.append(gap('no_native_evidence'))
    paths = observed_agent_paths(saved, diagnostics)
    for doc in saved:
        path = str(doc['path'].relative_to(root))
        sources.append(dict(id=path, path=path, adapter='codex', session_id=doc['session_id'],
                            source_version='codex-rollout-' + str(doc['meta'].get('cli_version')), turn_ids=doc['turns'],
                            native_agent_path=paths.get(doc['session_id'])))
    export_prompts = {}
    for source in exports:
        data = json.loads((root / source['path']).read_text())
        if 'version' not in data['info']:
            from opencode_capture import turns as opencode_turns
            prompts = [(turn, messages[0]['time']['created'],
                        '\n'.join([m.get('text', '') for m in messages if m['type'] == 'user'] +
                                  [p.get('text', '') for m in messages if m['type'] == 'assistant'
                                   for p in m.get('content', []) if p['type'] == 'text']))
                       for turn, messages in opencode_turns(data).items()]
        else:
            prompts = [(m['info']['id'], m['info'].get('time', {}).get('created', 0),
                        '\n'.join(p.get('text', '') for p in m['parts'] if p.get('type') == 'text'))
                       for m in data['messages'] if m['info']['id'] in source['turn_ids']]
        for turn, time, text in prompts:
            export_prompts.setdefault(source['session_id'], {})[turn] = (time, text)
    for session, prompts in export_prompts.items():
        previous = None
        for turn, (_, text) in sorted(prompts.items(), key=lambda item: item[1][0]):
            tag, ambiguous = assignment_tag(text, root.name)
            if ambiguous:
                diagnostics.append(gap('ambiguous_assignment', session, turn))
                previous = None
            elif tag:
                previous = tag
            assignments[(session, turn)] = previous or {}
    # Assignment inheritance is native-session scoped, in native turn order.
    for sid in sorted({s['session_id'] for s in sources if s['adapter'] == 'codex'}):
        session_docs = [d for d in saved if d['session_id'] == sid]
        order = {}
        for d in session_docs:
            for turn, row, _ in d['records']:
                if turn in d['turns'] and row:
                    order.setdefault(turn, stamp(row.get('timestamp')) or 0)
        previous, prior_request = None, {}
        for turn in sorted(order, key=lambda t: (order[t], t)):
            text = '\n'.join(message_text(row['payload']) for d in session_docs for tid, row, _ in d['records']
                             if tid == turn and row and row['type'] == 'response_item'
                             and assignment_message(row['payload'], paths.get(sid)))
            tag, ambiguous = assignment_tag(text, root.name)
            if ambiguous:
                diagnostics.append(gap('ambiguous_assignment', sid, turn))
                previous = None
            elif tag:
                previous = tag
            elif (sid, turn) in assignments:
                previous = assignments[(sid, turn)] or None
            assignments[(sid, turn)] = previous or {}
            request = requested.get((sid, turn), {})
            prior_request = {k: request.get(k) or prior_request.get(k) for k in ('model', 'reasoning_effort')}
            requested[(sid, turn)] = dict(prior_request)
    annotate_assignments(root, sources, assignments)
    return sources, assignments, requested, diagnostics
