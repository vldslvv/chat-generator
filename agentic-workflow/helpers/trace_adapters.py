"""Native parsing only. Adapter contract: (source, Path) -> (events, diagnostics).

Events use agent/model/tool kinds, native session/turn/event IDs, seconds since
Unix epoch, optional observed start/end, outcome, observed settings, canonical
usage and provenance. Content observations are separate from measurements.
Add an adapter to ADAPTERS; accounting remains unchanged.
Supported profiles are pinned, not a promise about arbitrary harness versions.
"""
from datetime import datetime
from collections import Counter
import hashlib
import json
import math
import re

METRICS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
           'uncached_input_tokens', 'output_tokens', 'reasoning_output_tokens', 'total_tokens')


def stamp(value, milliseconds=False):
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return value / (1000 if milliseconds else 1) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.timestamp() if parsed.tzinfo else None
        except ValueError:
            pass
    return None


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def add(*values):
    return sum(values) if all(v is not None for v in values) else None


def tokens(raw, harness):
    if not isinstance(raw, dict):
        raw = {}
    if harness == 'codex':
        result = {k: count(raw.get(k)) for k in METRICS}
        i, c, o, r = (result[k] for k in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens'))
        if i is not None and c is not None:
            if c > i:
                raise ValueError('cached tokens exceed input')
            result['uncached_input_tokens'] = i - c
    else:
        cache = raw.get('cache') or {}
        base, c, w, o, r = (count(v) for v in (raw.get('input'), cache.get('read'), cache.get('write'), raw.get('output'), raw.get('reasoning')))
        i = add(base, c, w)
        result = dict(input_tokens=i, cached_input_tokens=c, cache_write_input_tokens=w,
                      uncached_input_tokens=add(base, w), output_tokens=o, reasoning_output_tokens=r)
    if r is not None and o is not None and r > o:
        raise ValueError('reasoning tokens exceed output')
    # Both pinned formats store reasoning within output. OC input excludes cache
    # read/write; canonical input includes both. Cache writes are non-read input.
    result['total_tokens'] = add(i, o)
    return result


def event(source, kind, native_id, turn, location, **values):
    result = dict(kind=kind, native_event_id=native_id, session_id=source['session_id'],
                  turn_id=turn, start=None, end=None, timestamp=None, outcome=None,
                  model=None, reasoning_effort=None, variant=None, provider=None,
                  parent_session_id=None, forked_from_id=None, continued_from_id=None,
                  parent_call_id=None, call_id=None, usage=None,
                  provenance=[dict(source_id=source['id'], path=source['path'], location=location,
                                   adapter=source['adapter'], source_version=source['source_version'])])
    result.update(values)
    return result


def diagnostic(source, code, turn=None, **values):
    return dict(source_id=source['id'], session_id=source['session_id'], turn_id=turn,
                code=code, **values)


def content(payload, *fields):
    """Keep the recorded value, including empty values and opaque evidence."""
    values = {key: payload[key] for key in fields if key in payload}
    encrypted = {key: value for key, value in payload.items() if 'encrypted' in key and value is not None}
    metadata = payload.get('metadata')
    truncated = bool(payload.get('truncated') or isinstance(metadata, dict) and metadata.get('truncated'))
    # Codex's command wrapper can record truncation in its returned text rather
    # than a schema field. Only recognize its explicit diagnostic line.
    truncated = truncated or any(isinstance(value, str) and re.search(
        r'(?m)^Warning: truncated output \(original token count: \d+\)', value) for value in values.values())
    truncated = bool(truncated)
    state = 'recorded' if values else 'missing'
    if values and all(value in ('', [], {}, None) for value in values.values()):
        state = 'empty' if all(value is not None for value in values.values()) else 'missing'
    if encrypted:
        state = 'partially_encrypted' if state == 'recorded' else 'encrypted'
    if truncated:
        state = 'upstream_truncated'
    return dict(availability=state, values=values, encrypted=encrypted, upstream_truncated=truncated)


def codex_result_outcome(payload):
    if payload.get('type') == 'mcp_tool_call_end':
        result = payload.get('result') or {}
        return ('failed' if 'Err' in result or (result.get('Ok') or {}).get('isError') else
                'completed' if 'Ok' in result else None)
    if payload.get('type') == 'exec_command_end':
        status = payload.get('status')
        if status is None and isinstance(payload.get('exit_code'), int):
            status = 'failed' if payload['exit_code'] != 0 else 'completed'
        return status
    return 'returned'


def observation_id(row, turn, occurrences):
    """Native IDs win; ID-less records retain repeated occurrences within a turn.

    Fingerprints ignore file offsets so selected copies deduplicate on import.
    An identical ID-less row repeated in one file cannot safely be called a copy.
    """
    payload = row.get('payload') or {}
    if payload.get('id') or payload.get('message_id'):
        return f'{turn}:{row["type"]}:{payload.get("type")}:{payload.get("id") or payload["message_id"]}'
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = (turn, digest)
    occurrences[key] += 1
    return f'{turn}:{digest}:{occurrences[key]}'


def codex(source, path):
    events, diagnostics, calls, agents, models = [], [], {}, {}, {}
    selected = set(source['turn_ids'])
    active, settings, meta = None, {}, {}
    contexts = {}
    observations, occurrences, session_context = [], Counter(), {}
    declared, native_version = False, None
    with path.open('rb') as stream:
        for line, raw in enumerate(stream, 1):
            try:
                row = json.loads(raw)
            except ValueError:
                diagnostics.append(diagnostic(source, 'invalid_json_line', location=line))
                continue
            p = row.get('payload') or {}
            kind = row.get('type')
            if kind == 'session_meta':
                if p.get('id') != source['session_id']:
                    raise ValueError('session identity mismatch')
                declared = True
                native_version = p.get('cli_version')
                origin = p.get('source')
                spawn = ((origin.get('subagent') or {}).get('thread_spawn') or {}) if isinstance(origin, dict) else {}
                meta = dict(parent_session_id=p.get('parent_thread_id') or spawn.get('parent_thread_id'),
                            native_agent_name=p.get('agent_nickname') or spawn.get('agent_nickname'),
                            native_agent_path=p.get('agent_path') or spawn.get('agent_path'),
                            forked_from_id=p.get('forked_from_id'), continued_from_id=None,
                            spawn_timestamp=stamp(p.get('timestamp')))
                session_context = {key: value for key, value in p.items()
                                   if 'instruction' in key}
                session_location = line
                continue
            if kind == 'turn_context':
                active = p.get('turn_id')
                settings = dict(model=p.get('model'), reasoning_effort=p.get('effort'))
                contexts[active] = settings
            if kind == 'event_msg' and p.get('type') == 'task_started':
                active = p.get('turn_id', active)
            turn = p.get('turn_id') or (p.get('internal_chat_message_metadata_passthrough') or {}).get('turn_id') or active
            if turn not in selected or p.get('thread_id', source['session_id']) != source['session_id']:
                continue
            settings = contexts.get(turn, {})
            t = stamp(row.get('timestamp'))
            if turn not in agents:
                agents[turn] = event(source, 'agent', turn, turn, line, **meta)
                if session_context:
                    observations.append(event(source, 'instruction', f'{turn}:session-context', turn,
                                              session_location, content=content(session_context, *session_context),
                                              name='session instructions', context_scope='session'))
            agent = agents[turn]
            subtype = p.get('type')
            observation_kind = None
            fields = ()
            if kind == 'turn_context':
                observation_kind, fields = 'instruction', tuple(p)
            elif kind == 'response_item' and subtype in ('message', 'reasoning'):
                observation_kind = 'instruction' if p.get('role') in ('developer', 'system') else 'message'
                fields = ('content', 'summary')
            elif kind in ('event_msg', 'response_item') and subtype in ('user_message', 'agent_message', 'agent_reasoning', 'agent_reasoning_raw_content'):
                observation_kind, fields = 'message', ('message', 'text', 'content')
            elif (kind == 'response_item' and subtype in ('function_call_output', 'custom_tool_call_output') or
                  kind == 'event_msg' and subtype in ('exec_command_end', 'mcp_tool_call_end')):
                observation_kind, fields = 'tool_result', ('output', 'stdout', 'stderr', 'aggregated_output', 'result')
            if observation_kind:
                observations.append(event(source, observation_kind, observation_id(row, turn, occurrences), turn, line,
                                          timestamp=t, call_id=p.get('call_id'), name=subtype or kind,
                                          message_role=p.get('role') or ('user' if subtype == 'user_message' else None),
                                          outcome=codex_result_outcome(p) if observation_kind == 'tool_result' else None,
                                          content=content(p, *fields), native_record=p, **settings))
            if kind == 'turn_context':
                agent.update(settings)
            if kind == 'event_msg':
                subtype = p.get('type')
                if subtype == 'task_started':
                    start = stamp(p.get('started_at'))
                    agent['start'] = start if start is not None else t
                elif subtype in ('task_complete', 'task_completed', 'turn_aborted'):
                    agent.update(end=t, outcome='aborted' if subtype == 'turn_aborted' else 'completed')
                elif subtype == 'token_count':
                    diagnostics.append(diagnostic(source, 'aggregate_snapshot_excluded', turn))
                elif subtype in ('exec_command_end', 'mcp_tool_call_end'):
                    call = calls.get(p.get('call_id'))
                    if call:
                        call.update(end=t, outcome=codex_result_outcome(p))
                continue
            if kind == 'token_usage_record':
                rid = p.get('response_id')
                if not rid:
                    diagnostics.append(diagnostic(source, 'unidentified_usage', turn, location=line))
                    continue
                model = event(source, 'model', rid, turn, line, timestamp=t, end=t,
                              outcome='completed', usage=tokens(p.get('usage'), 'codex'), **settings)
                old = models.get(rid)
                if old:
                    if any(old[k] != model[k] for k in ('turn_id', 'usage', 'model', 'reasoning_effort')):
                        raise ValueError('conflicting duplicate usage')
                    old['provenance'] += model['provenance']
                else:
                    models[rid] = model
            if kind == 'response_item':
                subtype, cid = p.get('type'), p.get('call_id')
                if subtype in ('function_call', 'custom_tool_call'):
                    if not cid:
                        diagnostics.append(diagnostic(source, 'unidentified_tool', turn, location=line))
                        continue
                    call = event(source, 'tool', cid, turn, line, start=t, timestamp=t,
                                 call_id=cid, name=p.get('name'), parent_call_id=p.get('parent_call_id'),
                                 content=content(p, 'arguments', 'input'), native_record=p, **settings)
                    if cid in calls:
                        old = calls[cid]
                        if any(old[k] != call[k] for k in ('turn_id', 'name', 'parent_call_id', 'content', 'native_record')):
                            raise ValueError('conflicting duplicate tool call')
                        old['provenance'] += call['provenance']
                    else:
                        calls[cid] = call
                elif subtype in ('function_call_output', 'custom_tool_call_output'):
                    if cid in calls:
                        # Completion is observed; success is unknown without structured status.
                        calls[cid]['end'] = t
                        calls[cid]['outcome'] = calls[cid]['outcome'] or 'returned'
                    else:
                        diagnostics.append(diagnostic(source, 'orphan_tool_result', turn, location=line))
    if not declared:
        diagnostics.append(diagnostic(source, 'missing_native_identity'))
    if native_version != '0.167.0':
        diagnostics.append(diagnostic(source, 'unverified_native_version', native_version=native_version))
    events.extend(agents.values())
    events.extend(models.values())
    events.extend(calls.values())
    events.extend(observations)
    for item in events:
        for field in ('native_agent_name', 'native_agent_path', 'parent_session_id',
                      'forked_from_id', 'continued_from_id', 'spawn_timestamp'):
            item[field] = meta.get(field)
    return events, diagnostics


def opencode(source, path):
    data = json.loads(path.read_text())
    info = data['info']
    if 'version' not in info:
        from opencode_v2 import parse
        return parse(source, data)
    if info.get('id') != source['session_id']:
        raise ValueError('session identity mismatch')
    diagnostics, events = [], []
    if info.get('version') != '1.2.27':
        diagnostics.append(diagnostic(source, 'unverified_native_version', native_version=info.get('version')))
    selected = set(source['turn_ids'])  # Native user-message IDs are OpenCode turns.
    parents = {m['info']['id']: m['info'].get('parentID') for m in data['messages']}

    def turn_for(mid):
        seen = set()
        while mid not in selected and mid in parents and mid not in seen:
            seen.add(mid)
            mid = parents[mid]
        return mid if mid in selected else None

    agents = {}
    for index, message in enumerate(data['messages']):
        m = message['info']
        if m.get('sessionID') != source['session_id']:
            continue
        turn = turn_for(m['id'])
        if not turn:
            continue
        location = f'messages/{index}'
        if turn not in agents:
            agents[turn] = event(source, 'agent', turn, turn, location,
                                 parent_session_id=info.get('parentID'),
                                 spawn_timestamp=stamp((info.get('time') or {}).get('created'), True))
        agent = agents[turn]
        time = m.get('time') or {}
        if not message['parts']:
            events.append(event(source, 'message', f'{m["id"]}:empty-message', turn, location,
                                timestamp=stamp(time.get('created'), True), message_role=m['role'],
                                name='message', message_id=m['id'], parent_message_id=m.get('parentID'),
                                content=content({}, 'text')))
        for part_index, part in enumerate(message['parts']):
            if part['type'] in ('text', 'reasoning', 'subtask', 'compaction', 'file', 'agent'):
                pt = part.get('time') or {}
                events.append(event(source, 'message', f'{m["id"]}:{part.get("id", part_index)}', turn,
                                    f'{location}/parts/{part_index}',
                                    timestamp=stamp(pt.get('start', time.get('created')), True),
                                    message_role=m['role'], name=part['type'],
                                    message_id=m['id'], parent_message_id=m.get('parentID'),
                                    content=content(part, 'text', 'prompt'), native_record=part))
        if 'system' in m:
            events.append(event(source, 'instruction', f'{m["id"]}:system', turn, location,
                                timestamp=stamp(time.get('created'), True), name='system instructions',
                                content=content(m, 'system')))
        if m.get('error'):
            events.append(event(source, 'message', f'{m["id"]}:error', turn, location,
                                timestamp=stamp(time.get('completed'), True), name='message error',
                                message_role=m['role'], outcome='failed', content=content(m, 'error')))
        if m['role'] == 'user':
            agent['start'] = stamp(time.get('created'), True)
            continue
        if m['role'] != 'assistant':
            continue
        settings = dict(model=m.get('modelID'), provider=m.get('providerID'), variant=m.get('variant'))
        end = stamp(time.get('completed'), True)
        outcome = 'failed' if m.get('error') else ('completed' if end is not None else None)
        steps = [p for p in message['parts'] if p['type'] == 'step-finish']
        if steps:
            # Parts are model steps; message.tokens repeats only the latest step.
            for p in steps:
                events.append(event(source, 'model', p['id'], turn, f'{location}/parts/{p["id"]}',
                                    usage=tokens(p.get('tokens'), 'opencode'), outcome='completed', finish_reason=p.get('reason'), **settings))
            diagnostics.append(diagnostic(source, 'message_snapshot_excluded', turn, native_event_id=m['id']))
        else:
            # Completion also occurs after errors; initialized zeros are not usage.
            measured = end is not None and m.get('finish') and not m.get('error')
            usage = tokens(m.get('tokens') if measured else None, 'opencode')
            diagnostics.append(diagnostic(source, 'message_only_usage' if measured else 'unmeasured_message', turn,
                                          native_event_id=m['id']))
            events.append(event(source, 'model', m['id'], turn, location, start=stamp(time.get('created'), True),
                                end=end, outcome=outcome, usage=usage, **settings))
        if m.get('finish') and m['finish'] not in ('tool-calls', 'unknown') or m.get('error'):
            agent.update(end=end, outcome=outcome)
        for p in message['parts']:
            if p['type'] != 'tool':
                continue
            state = p.get('state') or {}
            time = state.get('time') or {}
            cid = p.get('callID')
            if not cid:
                diagnostics.append(diagnostic(source, 'unidentified_tool', turn, location=location))
                continue
            events.append(event(source, 'tool', cid, turn, f'{location}/parts/{p["id"]}',
                                call_id=cid, name=p.get('tool'), start=stamp(time.get('start'), True),
                                end=stamp(time.get('end'), True), outcome={'error': 'failed'}.get(state.get('status'), state.get('status')),
                                content=content(state, 'input'), native_record=p, **settings))
            if 'output' in state or 'error' in state:
                events.append(event(source, 'tool_result', f'{cid}:{p["id"]}:result', turn,
                                    f'{location}/parts/{p["id"]}', call_id=cid, name=p.get('tool'),
                                    timestamp=stamp(time.get('end'), True),
                                    outcome='failed' if state.get('status') == 'error' else state.get('status'),
                                    content=content(state, 'output', 'error'), native_record=state, **settings))
    return list(agents.values()) + events, diagnostics


ADAPTERS = {'codex': codex, 'opencode': opencode}


def read_source(source, path):
    adapter = source['adapter']
    if adapter not in ADAPTERS:
        raise ValueError(f'unsupported adapter: {adapter}')
    if not path.is_file():
        events, diagnostics = [], [diagnostic(source, 'source_unavailable')]
    else:
        events, diagnostics = ADAPTERS[adapter](source, path)
    for turn in source['turn_ids']:
        selected = [e for e in events if e['turn_id'] == turn]
        if not selected:
            diagnostics.append(diagnostic(source, 'selected_turn_absent', turn))
        if not any(e['kind'] == 'model' for e in selected) and not any(d['code'] == 'unidentified_usage' and d.get('turn_id') == turn for d in diagnostics):
            diagnostics.append(diagnostic(source, 'missing_usage', turn))
        if not any(e['kind'] == 'agent' and e['outcome'] for e in selected):
            diagnostics.append(diagnostic(source, 'unfinished_turn', turn))
    return events, diagnostics
