"""OpenCode 2.2.6 transfer schema: flat messages, idle-delimited turns."""
from opencode_capture import turns
from trace_adapters import add, content, count, diagnostic, event, stamp


def usage(raw):
    raw = raw or {}
    cache = raw.get('cache') or {}
    base, cached, written, output, reasoning = map(count, (
        raw.get('input'), cache.get('read'), cache.get('write'), raw.get('output'), raw.get('reasoning')))
    incoming, outgoing = add(base, cached, written), add(output, reasoning)
    return dict(input_tokens=incoming, cached_input_tokens=cached, cache_write_input_tokens=written,
                uncached_input_tokens=add(base, written), output_tokens=outgoing,
                reasoning_output_tokens=reasoning, total_tokens=add(incoming, outgoing))


def parse(source, data):
    if data['info']['id'] != source['session_id']:
        raise ValueError('session identity mismatch')
    events, gaps = [], []
    for turn, messages in turns(data).items():
        if turn not in source['turn_ids']:
            continue
        agent = event(source, 'agent', turn, turn, 'messages',
                      start=stamp(messages[0]['time']['created'], True),
                      parent_session_id=data['info'].get('parentID'))
        events.append(agent)
        for message in messages:
            mid, kind = message['id'], message['type']
            location = 'messages/' + mid
            time = message.get('time') or {}
            start, end = stamp(time.get('created'), True), stamp(time.get('completed'), True)
            if kind == 'idle':
                agent.update(end=start, outcome={'succeeded': 'completed', 'failed': 'failed',
                                                 'interrupted': 'interrupted'}[message['outcome']])
                continue
            if kind != 'assistant':
                events.append(event(source, 'message', mid, turn, location, timestamp=start,
                                    message_role=kind, name=kind, message_id=mid,
                                    content=content(message, 'text', 'summary', 'output', 'error'), native_record=message))
                if kind == 'compaction' and message.get('tokens'):
                    events.append(event(source, 'model', mid + ':usage', turn, location,
                                        start=start, end=end, usage=usage(message['tokens'])))
                continue
            model = message.get('model') or {}
            settings = dict(model=model.get('id'), provider=model.get('providerID'), variant=model.get('variant'))
            events.append(event(source, 'model', mid, turn, location, start=start, end=end,
                                outcome='failed' if message.get('error') else ('completed' if end else None),
                                usage=usage(message.get('tokens')), finish_reason=message.get('finish'), **settings))
            if message.get('error'):
                events.append(event(source, 'message', mid + ':error', turn, location,
                                    timestamp=end, message_role='assistant', name='message error',
                                    outcome='failed', content=content(message, 'error')))
            for index, part in enumerate(message.get('content', [])):
                loc = location + '/content/' + str(index)
                if part['type'] != 'tool':
                    events.append(event(source, 'message', f'{mid}:{index}', turn, loc, timestamp=start,
                                        message_role='assistant', name=part['type'], message_id=mid,
                                        content=content(part, 'text'), native_record=part))
                    continue
                state, clock = part['state'], part['time']
                cid = part['id']
                outcome = 'failed' if state['status'] == 'error' else state['status']
                events.append(event(source, 'tool', cid, turn, loc, call_id=cid, name=part['name'],
                                    start=stamp(clock.get('ran', clock.get('created')), True),
                                    end=stamp(clock.get('completed'), True), outcome=outcome,
                                    content=content(state, 'input'), native_record=part, **settings))
                if 'content' in state or 'error' in state:
                    events.append(event(source, 'tool_result', cid + ':result', turn, loc, call_id=cid,
                                        name=part['name'], timestamp=stamp(clock.get('completed'), True),
                                        outcome=outcome, content=content(state, 'content', 'error'),
                                        native_record=state, **settings))
        if agent['end'] is None:
            gaps.append(diagnostic(source, 'unfinished_turn', turn))
    return events, gaps
