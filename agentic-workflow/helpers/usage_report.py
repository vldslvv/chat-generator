#!/usr/bin/env python3
"""Rebuild usage and trace reports once for an existing implementation.

implementation is the allocated implementation directory.

Creates/uses implementation/.records.lock; refreshes saved native turns and
proven dispatch descendants under implementation/native/<session-id>/<turn-
id>.jsonl (Codex) or .json (OpenCode). Creates/overwrites implementation/reports/usage.json, usage.md,
events.json and timeline.json; starts no viewer or continuous capture.

Prints JSON with implementation_id (directory name), reports (report directory
path) and coverage (diagnostic-code counts). Exit 0 means reports were written,
not complete telemetry. Inspect coverage and usage.json diagnostics; null means
unavailable, known_subtotal excludes missing measurements. Exit 2 means invalid
input or an operation error (stderr).

Rerun after more evidence is saved, or use trace_view.py for live capture.

Example: python3 agentic-workflow/helpers/usage_report.py .agentic-workflow/records/001_example
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from records import locked, write_atomic
from native_traces import collect, safe_destination
from trace_adapters import METRICS, read_source


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()[:24]


def import_evidence(root):
    """I/O boundary: native records supply both measurements and assignments."""
    root = Path(root)
    sources, assignments, requested, diagnostics = collect(root)
    events = {}
    for source in sources:
        native, gaps = read_source(source, root / source['path'])
        for item in [*native, *gaps]:
            assignment = assignments.get((source['session_id'], item.get('turn_id')), {})
            item.update(implementation_id=root.name, adapter=source['adapter'],
                        agent_id=f'{source["adapter"]}:{source["session_id"]}',
                        task_id=assignment.get('task'), role=assignment.get('role'),
                        agent_run_id=f'{source["adapter"]}:{source["session_id"]}',
                        assignment_id=identity(source['session_id'], assignment))
        for e in native:
            assignment = assignments.get((source['session_id'], e['turn_id']), {})
            e['requested'] = requested.get((source['session_id'], e['turn_id']), {})
            e['native_agent_path'] = e.get('native_agent_path') or source.get('native_agent_path')
            e['agent_name'] = e.get('native_agent_name') or ('root' if e['native_agent_path'] == '/root' else e['agent_id'])
            e['purpose'] = assignment.get('purpose')
            e['assignment_source'] = assignment.get('source', 'native') if assignment else None
            e['assignment_evidence'] = assignment.get('evidence', [])
            e['event_id'] = identity(e['implementation_id'], e['agent_id'], e['kind'], e['native_event_id'])
            old = events.get(e['event_id'])
            if old:
                ignored = {'provenance'}
                if {k: v for k, v in old.items() if k not in ignored} != {k: v for k, v in e.items() if k not in ignored}:
                    raise ValueError('conflicting duplicate native event')
                old['provenance'] += e['provenance']
            else:
                events[e['event_id']] = e
        for turn in source['turn_ids']:
            if not assignments.get((source['session_id'], turn)):
                gaps.append(dict(code='missing_assignment', session_id=source['session_id'],
                                 turn_id=turn, source_id=source['id']))
        diagnostics.extend(gaps)
    # Repeated copies can contain identical source-wide diagnostics.
    unique = {json.dumps(d, sort_keys=True): d for d in diagnostics}
    observed = list(events.values())
    calls = {(e['agent_id'], e['turn_id'], e['call_id']): e for e in observed if e['kind'] == 'tool'}
    turns = {(e['agent_id'], e['turn_id']): e for e in observed if e['kind'] == 'agent'}
    for e in observed:
        e['provenance'] = list({json.dumps(p, sort_keys=True): p for p in e['provenance']}.values())
        if e['kind'] == 'tool':
            parent = calls.get((e['agent_id'], e['turn_id'], e.get('parent_call_id')))
            e['parent_event_id'] = parent['event_id'] if parent else None
            e['outputs'] = []
        if e['kind'] == 'agent':
            e['instructions'] = []
    for e in observed:
        if e['kind'] == 'tool_result':
            call = calls.get((e['agent_id'], e['turn_id'], e['call_id']))
            e['call_event_id'] = call['event_id'] if call else None
            if call:
                e['tool_name'] = call.get('name')
                call['outputs'].append(e)
        if e['kind'] == 'instruction':
            agent = turns.get((e['agent_id'], e['turn_id']))
            e['turn_event_id'] = agent['event_id'] if agent else None
            if agent:
                agent['instructions'].append(e)
    for e in observed:
        for field in ('outputs', 'instructions'):
            if field in e:
                e[field].sort(key=event_order)
    return sorted(observed, key=event_order), [unique[k] for k in sorted(unique)]


def event_order(e):
    observed = next((e.get(k) for k in ('timestamp', 'start', 'end') if e.get(k) is not None), None)
    location = e['provenance'][0]['location']
    # Keep native ordering for records sharing a timestamp, including parts.
    order = tuple(int(part) for part in str(location).split('/') if part.isdigit())
    return (observed is None, observed or 0, e['agent_id'], order, e['event_id'])


GAP_CODES = {'missing_usage', 'unidentified_usage', 'invalid_json_line'}
INCOMPLETE_CODES = GAP_CODES | {'source_unavailable', 'unfinished_turn', 'unverified_native_version',
                                'missing_native_identity', 'message_only_usage', 'unmeasured_message',
                                'native_storage_unavailable', 'native_source_unavailable',
                                'native_identity_unresolved', 'native_identity_mismatch',
                                'ambiguous_native_identity', 'ambiguous_dispatch_turn', 'selected_turn_absent',
                                'native_turn_unavailable', 'no_native_evidence',
                                'opencode_export_unavailable', 'opencode_turn_unavailable',
                                'opencode_dispatch_unresolved', 'opencode_parent_mismatch'}


def summarize(events, diagnostics):
    events = [e for e in events if e['kind'] in ('agent', 'model', 'tool')]
    models = [e for e in events if e['kind'] == 'model']
    calls = [e for e in events if e['kind'] == 'tool']
    unknown = sum(d['code'] in GAP_CODES for d in diagnostics)
    incomplete = any(d['code'] in INCOMPLETE_CODES for d in diagnostics)
    metrics = {}
    for metric in METRICS:
        values = [(e.get('usage') or {}).get(metric) for e in models]
        measured = [v for v in values if v is not None]
        missing = len(values) - len(measured) + unknown
        metrics[metric] = dict(total=sum(measured) if measured and not missing and not incomplete else None,
                               known_subtotal=sum(measured) if measured else None,
                               measured_records=len(measured), missing_records=missing)
    durations = [e['end'] - e['start'] for e in events
                 if e.get('start') is not None and e.get('end') is not None and e['end'] >= e['start']]
    return dict(tokens=metrics, observed_model_measurements=len(models),
                observed_tool_calls=len(calls),
                wrapper_calls=sum(e.get('name') in ('functions.exec', 'exec') for e in calls),
                observed_nested_operations=sum(bool(e.get('parent_call_id')) for e in calls),
                missing_parent_call_relationships=sum(not e.get('parent_call_id') for e in calls),
                outcomes=dict(sorted(Counter(e['outcome'] or 'unknown' for e in calls).items())),
                observed_operation_seconds=sum(durations) if durations else None,
                timed_operations=len(durations), untimed_operations=len(events) - len(durations),
                coverage=dict(sorted(Counter(d['code'] for d in diagnostics).items())))


def spawn_tree(events):
    nodes = {}
    relations = set()
    for e in events:
        node = nodes.setdefault(e['agent_id'], dict(agent_id=e['agent_id'], session_id=e['session_id'],
                                                   agent_run_ids=set(), turns=set()))
        if e.get('agent_run_id'):
            node['agent_run_ids'].add(e['agent_run_id'])
        node['turns'].add(e['turn_id'])
        for field, kind in [('parent_session_id', 'spawn'), ('forked_from_id', 'fork'), ('continued_from_id', 'continuation')]:
            if e.get(field):
                relations.add((f'{e["adapter"]}:{e[field]}', e['agent_id'], kind))
    return dict(nodes=[dict(n, agent_run_ids=sorted(n['agent_run_ids']), turns=sorted(n['turns']))
                       for _, n in sorted(nodes.items())],
                edges=[dict(parent=p, child=c, relationship=k, parent_in_selection=p in nodes)
                       for p, c, k in sorted(relations)])


def build_report(events, diagnostics):
    """Pure accounting. No harness-specific parsing or grouping in adapters."""
    events = [e for e in events if e['kind'] in ('agent', 'model', 'tool')]
    groups, omissions = {}, {}
    for name, fields in [('task', ('task_id',)), ('agent_run', ('agent_run_id',)),
                         ('role', ('role',)), ('model', ('model',)), ('effort', ('reasoning_effort',)),
                         ('model_effort', ('model', 'reasoning_effort')),
                         ('task_model_effort', ('task_id', 'model', 'reasoning_effort')),
                         ('tool', ('name',)), ('task_tool', ('task_id', 'name'))]:
        grouped, gaps = defaultdict(list), defaultdict(list)
        omitted = []
        for e in events:
            if name in ('model', 'effort', 'model_effort', 'task_model_effort') and e['kind'] != 'model':
                continue
            if name in ('tool', 'task_tool') and e['kind'] != 'tool':
                continue
            key = tuple(e.get(k) for k in fields)
            if name != 'task' and any(v is None for v in key):
                omitted.append(e['event_id'])
            else:
                grouped[key].append(e)
        unassigned_gaps = 0
        for d in diagnostics:
            key = tuple(d.get(k) for k in fields)
            if all(v is not None for v in key):
                gaps[key].append(d)
                continue
            unassigned_gaps += 1
            # Preserve diagnostic scope across grouping. A source-wide gap can
            # affect several assignments; a turn gap can affect multiple models.
            affected = {tuple(e.get(k) for k in fields) for e in events
                        if any(p.get('source_id') == d.get('source_id') for p in e['provenance'])
                        and (d.get('turn_id') is None or e['turn_id'] == d['turn_id'])}
            affected = {key for key in affected if name == 'task' or all(v is not None for v in key)}
            if not affected and d['code'] in INCOMPLETE_CODES:
                affected = set(grouped)  # Unknown attribution cannot prove completeness.
            for key in affected:
                gaps[key].append(d)
        groups[name] = [dict(key=dict(zip(fields, key)), summary=summarize(grouped[key], gaps[key]))
                        for key in sorted(grouped.keys() | gaps.keys(), key=lambda key: tuple(v or '' for v in key))]
        omissions[name] = dict(event_ids=omitted, diagnostics_without_attribution=unassigned_gaps)
    return dict(version=2, summary=summarize(events, diagnostics), groups=groups,
                attribution_omissions=omissions, spawn_tree=spawn_tree(events), diagnostics=diagnostics,
                assignments=assignments(events), native_sources=native_sources(events),
                limitations=['Only saved native turns and their proven dispatch descendants are included.',
                             'Known subtotals exclude missing measurements; totals are scoped to observed evidence.',
                             'Operation durations can overlap and are not wall-clock, CPU or billed time.',
                             'Absent parent-call relationships do not establish absence of nested operations.',
                             'Observed settings come from native context, not necessarily provider confirmation.'])


def native_sources(events):
    sources = {}
    for e in events:
        for p in e['provenance']:
            key = (p.get('adapter'), e['session_id'], p.get('path'), p.get('source_version'))
            sources.setdefault(key, set()).add(e['turn_id'])
    return [dict(adapter=adapter, session_id=session, path=path, source_version=version, turn_ids=sorted(turns))
            for (adapter, session, path, version), turns in sorted(sources.items())]


def assignments(events):
    """Unique observed assignments, preserving session reuse and explicit context."""
    fields = ('agent_id', 'agent_run_id', 'agent_name', 'native_agent_name', 'native_agent_path',
              'task_id', 'role', 'purpose', 'assignment_id', 'assignment_source', 'assignment_evidence')
    rows = {}
    for e in events:
        key = (e['agent_id'], e.get('assignment_id'))
        row = rows.setdefault(key, dict({k: e.get(k) for k in fields}, turns=set(), outcomes=set(), observed_settings=set(), requested_settings=set()))
        row['turns'].add(e.get('turn_id'))
        settings = (e.get('model'), e.get('reasoning_effort'), e.get('variant'))
        if any(value is not None for value in settings):
            row['observed_settings'].add(settings)
        request = e.get('requested') or {}
        pair = (request.get('model'), request.get('reasoning_effort'))
        if any(v is not None for v in pair):
            row['requested_settings'].add(pair)
        if e['kind'] == 'agent':
            row['outcomes'].add(e.get('outcome') or 'unfinished')
    return [dict(row, turns=sorted(t for t in row['turns'] if t), outcomes=sorted(row['outcomes']),
                 requested_settings=[dict(model=model, reasoning_effort=effort) for model, effort in
                                     sorted(row['requested_settings'], key=lambda pair: tuple(v or '' for v in pair))],
                 observed_settings=[dict(model=model, reasoning_effort=effort, **({'variant': variant} if variant is not None else {}))
                                    for model, effort, variant in
                                    sorted(row['observed_settings'], key=lambda pair: tuple(v or '' for v in pair))])
            for _, row in sorted(rows.items(), key=lambda item: str(item[0]))]


def format_settings(settings):
    """Keep observed model/effort pairs together, without filling gaps from requests."""
    return '; '.join(f'{s.get("model") or "unavailable"} / {s.get("reasoning_effort") or "unavailable"}'
                     + (f' · variant: {s["variant"]}' if s.get('variant') is not None else '')
                     for s in settings) or 'unavailable'


def timeline_lanes(events, lanes):
    """Pack intervals into tracks where slices can nest without crossing."""
    stacks = {agent: [(tid, [])] for agent, tid in lanes.items()}
    assigned, extra = {}, []
    next_lane = len(lanes) + 1
    spans = [e for e in events if e.get('start') is not None and
             ((e.get('end') is not None and e['end'] >= e['start']) or
              (e['kind'] == 'agent' and e.get('end') is None))]
    for e in sorted(spans, key=lambda e: (round(e['start'] * 1_000_000),
                                          -round(e['end'] * 1_000_000) if e.get('end') is not None else -float('inf'),
                                          e['event_id'])):
        start = round(e['start'] * 1_000_000)
        end = round(e['end'] * 1_000_000) if e.get('end') is not None else float('inf')
        tracks = stacks[e['agent_id']]
        for tid, ends in tracks:
            while ends and ends[-1] <= start:
                ends.pop()
            if not ends or end <= ends[-1]:
                break
        else:
            tid, ends = next_lane, []
            next_lane += 1
            tracks.append((tid, ends))
            extra.append((e['agent_id'], tid, len(tracks)))
        ends.append(end)
        assigned[e['event_id']] = tid
    return assigned, extra


def timeline(events):
    first_seen = {}
    for e in events:
        observed = next((e[key] for key in ('start', 'timestamp', 'end') if e.get(key) is not None), float('inf'))
        first_seen[e['agent_id']] = min(first_seen.get(e['agent_id'], float('inf')), observed)
    lanes = {agent: i + 1 for i, agent in enumerate(sorted(first_seen, key=lambda agent: (first_seen[agent], agent)))}
    labels = defaultdict(set)
    for assignment in assignments(events):
        context = ' / '.join(v for v in (assignment.get('role'), assignment.get('task_id')) if v)
        label = assignment.get('agent_name') or assignment['agent_id']
        label = f'{label} · {context}' if context else label
        labels[assignment['agent_id']].add(f'{label} · {format_settings(assignment["observed_settings"])}')
    event_lanes, extra = timeline_lanes(events, lanes)
    tracks = sorted([(agent, tid, 1) for agent, tid in lanes.items()] + extra,
                    key=lambda track: (lanes[track[0]], track[2]))
    output = []
    for rank, (agent, tid, number) in enumerate(tracks):
        label = '; '.join(sorted(labels[agent])) + (f' · parallel {number}' if number > 1 else '')
        output.append(dict(ph='M', name='thread_name', pid=1, tid=tid, args={'name': label}))
        # Perfetto otherwise applies its own thread ordering. Keep parallel
        # tracks adjacent to their session, in session start order.
        output.append(dict(ph='M', name='thread_sort_index', pid=1, tid=tid, args={'sort_index': rank}))
    omitted, flows = [], set()
    ordered = sorted(events, key=lambda e: (
        round((e.get('start') if e.get('start') is not None else e.get('timestamp') or e.get('end') or 0) * 1_000_000),
        -round(e['end'] * 1_000_000) if e.get('end') is not None else -float('inf'),
        e['event_id']))
    for e in ordered:
        start, end = e.get('start'), e.get('end')
        point = e.get('timestamp')
        label = e.get('name') or (e.get('agent_name') if e['kind'] == 'agent' else None) or e['kind']
        if e['kind'] == 'agent':
            label += ' · ' + (e.get('purpose') or ' / '.join(v for v in (e.get('role'), e.get('task_id')) if v) or 'assignment unavailable')
            label += ' · ' + format_settings([e])
        base = dict(name=label, cat=e['kind'], pid=1, tid=event_lanes.get(e['event_id'], lanes[e['agent_id']]),
                    args={k: e.get(k) for k in ('event_id', 'task_id', 'role', 'agent_run_id', 'agent_id',
                                               'agent_name', 'native_agent_name', 'native_agent_path', 'purpose',
                                               'assignment_source', 'assignment_evidence',
                                               'outcome', 'model', 'reasoning_effort', 'variant', 'call_id', 'parent_call_id')})
        base['args'].update({f'tokens.{k}': v for k, v in (e.get('usage') or {}).items() if v is not None})
        for key in ('native_event_id', 'session_id', 'turn_id', 'message_role', 'call_event_id',
                    'parent_event_id', 'turn_event_id', 'message_id', 'parent_message_id'):
            if e.get(key) is not None:
                base['args'][key] = e[key]
        # JSON strings keep complete arrays/structured values inspectable in
        # Perfetto, whose argument importer otherwise flattens nested objects.
        for key in ('content', 'outputs', 'instructions', 'native_record', 'provenance'):
            if key in e:
                base['args'][key] = json.dumps(e[key], ensure_ascii=False, indent=2)
        if start is not None and end is not None and end >= start:
            output.append(dict(base, ph='X', ts=round(start * 1_000_000), dur=round(end * 1_000_000) - round(start * 1_000_000)))
        elif e['kind'] == 'agent' and start is not None and end is None:
            output.append(dict(base, name=label + ' · unfinished', ph='B', ts=round(start * 1_000_000)))
            omitted.append(dict(event_id=e['event_id'], reason='duration_unavailable'))
        elif start is not None or end is not None or point is not None:
            observed = start if start is not None else end if end is not None else point
            output.append(dict(base, ph='i', s='t', ts=round(observed * 1_000_000)))
            if e['kind'] in ('agent', 'model', 'tool'):
                omitted.append(dict(event_id=e['event_id'], reason='duration_unavailable'))
        else:
            omitted.append(dict(event_id=e['event_id'], reason='timing_unavailable'))
        parent = f'{e["adapter"]}:{e.get("parent_session_id")}'
        spawn = e.get('spawn_timestamp')
        if parent in lanes and spawn is not None and e['agent_id'] not in flows:
            flows.add(e['agent_id'])
            fid = lanes[e['agent_id']]  # Chrome/Perfetto IDs are numeric (not arbitrary hash strings).
            for phase, agent in [('s', parent), ('f', e['agent_id'])]:
                # Bind each endpoint to an explicit observed creation instant.
                # Without anchors Perfetto can attach to unrelated enclosing
                # slices and reverse a flow when one lane has only instants.
                output.append(dict(name='native spawn', cat='agent', ph='i', s='t',
                                   pid=1, tid=lanes[agent], ts=round(spawn * 1_000_000)))
                output.append(dict(name='spawn', cat='agent', ph=phase, id=fid, pid=1,
                                   tid=lanes[agent], ts=round(spawn * 1_000_000), **({'bp': 'e'} if phase == 'f' else {})))
    return dict(traceEvents=output, displayTimeUnit='ms', metadata=dict(timing_omissions=omitted))


def markdown(report):
    lines = ['# Selected implementation usage', '',
             'Null means unavailable. Known subtotals exclude missing measurements. Scope and omissions are in usage.json.', '',
             '| Metric | Total | Known subtotal | Measured records | Missing records |',
             '|---|---:|---:|---:|---:|']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ') if value is not None else 'unavailable'
    for metric, values in report['summary']['tokens'].items():
        lines.append('| ' + ' | '.join(map(cell, [metric, *values.values()])) + ' |')
    for name, rows in report['groups'].items():
        tools = name in ('tool', 'task_tool')
        models = name in ('model', 'effort', 'model_effort', 'task_model_effort')
        headers = (['Group', 'Observed calls', 'Outcomes', 'Observed seconds', 'Untimed'] if tools else
                   ['Group', 'Total tokens', 'Known subtotal', 'Missing records'] + ([] if models else ['Tools']))
        lines += ['', f'## By {name}', '', '| ' + ' | '.join(headers) + ' |',
                  '| ' + ' | '.join('---' for _ in headers) + ' |']
        for row in rows:
            s = row['summary']
            tokens = s['tokens']['total_tokens']
            values = ([s['observed_tool_calls'], s['outcomes'], s['observed_operation_seconds'], s['untimed_operations']]
                      if tools else [tokens['total'], tokens['known_subtotal'], tokens['missing_records']]
                      + ([] if models else [s['observed_tool_calls']]))
            label = ', '.join(v if v is not None else 'unavailable' for v in row['key'].values())
            lines.append('| ' + ' | '.join(map(cell, [label, *values])) + ' |')
        omission = report['attribution_omissions'][name]
        lines += ['', f'Attribution omissions: {len(omission["event_ids"])} events; {omission["diagnostics_without_attribution"]} diagnostics.']
    lines += ['', '## Native lineage', '']
    for edge in report['spawn_tree']['edges']:
        lines.append(f'- {edge["parent"]} → {edge["child"]} ({edge["relationship"]})')
    lines += ['', '## Coverage diagnostics', '']
    for code, n in report['summary']['coverage'].items():
        lines.append(f'- {code}: {n}')
    return '\n'.join(lines) + '\n'


@dataclass(frozen=True)
class ReportBundle:
    usage: dict
    content: dict
    files: dict
    timeline_available: bool


def refresh(root):
    root = Path(root).resolve()
    with locked(root / '.records.lock'):
        events, diagnostics = import_evidence(root)
        report = build_report(events, diagnostics)
        report['implementation_id'] = root.name
        trace = timeline(events)
        content_report = dict(version=1, implementation_id=root.name, events=events,
                              timing_omissions=trace['metadata']['timing_omissions'])
        outputs = {name: (json.dumps(value, indent=2) + '\n').encode()
                   for name, value in [('usage.json', report), ('timeline.json', trace), ('events.json', content_report)]}
        outputs['usage.md'] = markdown(report).encode()
        # Validate the whole output set before writing, including symlink/hardlink
        # aliases. Native inputs live outside this output boundary.
        for name in outputs:
            safe_destination(root, root / 'reports' / name)
        for name, data in outputs.items():
            write_atomic(root / 'reports' / name, data)
    return ReportBundle(report, content_report, outputs, any(e['ph'] != 'M' for e in trace['traceEvents']))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('implementation', type=Path, help='existing implementation directory')
    args = parser.parse_args()
    try:
        report = refresh(args.implementation).usage
        print(json.dumps({'implementation_id': report['implementation_id'], 'reports': str(args.implementation / 'reports'),
                          'coverage': report['summary']['coverage']}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'usage-report: {exc}\n')


if __name__ == '__main__':
    main()
