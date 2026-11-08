"""Collection contracts through real native files/indexes and public commands.

The disposable SQLite index mirrors installed Codex identity/parent fields.
Fixture counters are deliberately independent of collector selection logic.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPERS = Path(__file__).resolve().parents[1] / 'helpers'
sys.path.insert(0, str(HELPERS))
from usage_report import refresh


def row(kind, payload, time=100):
    return dict(type=kind, timestamp=time, payload=payload)


def turn(sid, tid, time, message='', complete=True):
    rows = [row('event_msg', dict(type='task_started', turn_id=tid), time),
            row('turn_context', dict(turn_id=tid, model='observed', effort='high'), time),
            row('response_item', dict(type='message', role='user', content=[dict(type='input_text', text=message)]), time),
            row('token_usage_record', dict(thread_id=sid, turn_id=tid, response_id=tid + '-response', usage=dict(
                input_tokens=10, cached_input_tokens=2, cache_write_input_tokens=0,
                output_tokens=3, reasoning_output_tokens=1)), time + 1)]
    if complete:
        rows.append(row('event_msg', dict(type='task_complete', turn_id=tid), time + 2))
    return rows


def dispatch(name, call, args, result, time=110):
    return [row('response_item', dict(type='function_call', name=name, call_id=call, arguments=json.dumps(args)), time),
            row('response_item', dict(type='function_call_output', call_id=call, output=json.dumps(result)), time + 1)]


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.host = self.base / 'host'
        self.host.mkdir()
        self.index = self.host / 'state_5.sqlite'
        c = sqlite3.connect(self.index)
        c.execute('CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT, source TEXT, agent_path TEXT)')
        c.commit()
        c.close()
        self.environment = patch.dict(os.environ, CODEX_HOME=str(self.host), CODEX_THREAD_ID='root')
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.root = self.base / '.agentic-workflow/records/001_demo'

    def tag(self, task='work', role='implementer', **extra):
        return 'AGENTIC_WORKFLOW ' + json.dumps(dict(implementation='001_demo', task=task, role=role, **extra))

    def native(self, sid, rows, parent=None, path=None, fork=None, created=100):
        source = dict(subagent=dict(thread_spawn=dict(parent_thread_id=parent, agent_path=path))) if parent else 'cli'
        meta = row('session_meta', dict(id=sid, cli_version='0.167.0', timestamp=created,
                                       source=source, forked_from_id=fork), created)
        native = self.host / (sid + '.jsonl')
        native.write_bytes(b''.join((json.dumps(r) + '\n').encode() for r in [meta, *rows]))
        c = sqlite3.connect(self.index)
        c.execute('INSERT OR REPLACE INTO threads VALUES (?,?,?,?)', (sid, str(native), json.dumps(source), path))
        c.commit()
        c.close()
        return native

    def cli(self, script, *args):
        return subprocess.run([sys.executable, str(HELPERS / script), *map(str, args)], capture_output=True, text=True)

    def allocate(self):
        result = self.cli('records.py', 'allocate', 'demo', '--records-root', self.base / '.agentic-workflow/records')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), self.root)
        self.assertFalse((self.root / 'implementation.json').exists())

    def test_allocation_resume_refresh_bytes_and_removed_registration_cli(self):
        native = self.native('root', turn('root', 'old', 100) + turn('root', 'active', 200, self.tag('orchestration', 'supervisor'), complete=False))
        before = native.read_bytes()
        self.allocate()
        captured = self.root / 'native/root/active.jsonl'
        expected = b''.join(line for line in before.splitlines(keepends=True)
                            if b'"old"' not in line and b'old-response' not in line)
        # user messages without explicit turn IDs belong to the selected block.
        old_user = (json.dumps(turn('root', 'old', 100)[2]) + '\n').encode()
        expected = expected.replace(old_user, b'', 1)
        self.assertEqual(captured.read_bytes(), expected)
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['known_subtotal'], 13)
        self.assertIn('unfinished_turn', report['summary']['coverage'])
        with native.open('ab') as f:
            f.write((json.dumps(row('event_msg', dict(type='task_complete', turn_id='active'), 205)) + '\n').encode())
        complete = refresh(self.root).usage
        self.assertEqual(complete['summary']['tokens']['total_tokens']['total'], 13)
        self.assertEqual(captured.read_bytes(), expected + (json.dumps(row('event_msg', dict(type='task_complete', turn_id='active'), 205)) + '\n').encode())
        (self.root / 'tasks/work').mkdir(parents=True)
        with native.open('ab') as f:
            f.write(b''.join((json.dumps(r) + '\n').encode() for r in turn('root', 'resumed', 300, self.tag('repair', 'reviewer'))))
        result = self.cli('records.py', 'resolve', self.root, 'work')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['total'], 26)
        self.assertEqual({r['key']['task_id'] for r in report['groups']['task']}, {'orchestration', 'repair'})
        self.assertEqual(len(report['spawn_tree']['nodes']), 1)
        self.assertFalse(list(self.root.glob('runs/*/*/trace.jsonl')))
        for command in ('source', 'bind'):
            self.assertEqual(self.cli('records.py', command, self.root, 'ignored.json').returncode, 2)
        # Host files have only the records appended explicitly by this test.
        self.assertTrue(native.read_bytes().startswith(before))

    def test_nested_dispatch_followups_retags_replacements_unrelated_and_fork_history(self):
        handoff = self.tag(purpose='Build feature')
        repair = self.tag('repair', 'reviewer')
        root_rows = turn('root', 'r1', 100, self.tag('orchestration', 'supervisor'))
        root_rows += dispatch('spawn_agent', 'spawn', dict(task_name='builder', message=handoff, model='requested', reasoning_effort='low'), dict(task_name='/root/builder'))
        root_rows += dispatch('followup_task', 'again', dict(target='builder', message='Continue'), {}, 210)
        root_rows += dispatch('followup_task', 'retag', dict(target='/root/builder', message=repair), dict(turn_id='b3'), 310)
        root_rows += dispatch('spawn_agent', 'replacement', dict(task_name='replacement', message=handoff), dict(agent_id='replacement'), 410)
        self.native('root', root_rows)
        child_rows = turn('child', 'b1', 200, handoff)
        child_rows += dispatch('spawn_agent', 'nested', dict(task_name='review', message=self.tag(role='reviewer')), dict(task_name='/root/builder/review'), 205)
        child_rows += turn('child', 'b2', 300, 'Continue') + turn('child', 'b3', 400, repair) + turn('child', 'unrelated', 600)
        self.native('child', child_rows, 'root', '/root/builder', created=195)
        self.native('nested', turn('root', 'inherited', 100) + turn('nested', 'n1', 250, self.tag(role='reviewer')),
                    'child', '/root/builder/review', fork='root', created=240)
        self.native('unrelated', turn('unrelated', 'u1', 100))
        # Identical agent paths in another native tree cannot affect attribution.
        self.native('other-root', turn('other-root', 'or1', 100))
        self.native('other-child', turn('other-child', 'oc1', 200), 'other-root', '/root/builder', created=195)
        self.allocate()
        pending = refresh(self.root).usage
        self.assertEqual(pending['summary']['tokens']['total_tokens']['known_subtotal'], 65)
        self.assertNotIn('codex:replacement', {n['agent_id'] for n in pending['spawn_tree']['nodes']})
        # Retry an already saved dispatch after its native child becomes visible.
        self.native('replacement', turn('replacement', 'new', 500, handoff), 'root', '/root/replacement', created=490)
        originals = {p: p.read_bytes() for p in self.host.glob('*.jsonl')}
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['total'], 78)
        self.assertEqual({p.parent.name for p in self.root.glob('native/*/*.jsonl')}, {'root', 'child', 'nested', 'replacement'})
        self.assertFalse(list(self.root.glob('native/*/inherited.jsonl')))
        self.assertFalse(list(self.root.glob('native/*/unrelated.jsonl')))
        assignments = {(a['session_id'] if 'session_id' in a else a['agent_id'].split(':')[1], a['task_id']): a for a in report['assignments']}
        self.assertEqual(assignments[('child', 'work')]['turns'], ['b1', 'b2'])
        self.assertEqual(assignments[('child', 'work')]['requested_settings'], [dict(model='requested', reasoning_effort='low')])
        self.assertEqual(assignments[('child', 'repair')]['turns'], ['b3'])
        self.assertEqual({a['agent_run_id'] for a in report['assignments'] if a['agent_id'] == 'codex:child'}, {'codex:child'})
        self.assertIn(dict(parent='codex:child', child='codex:nested', relationship='spawn', parent_in_selection=True), report['spawn_tree']['edges'])
        timeline = json.loads((self.root / 'reports/timeline.json').read_text())
        self.assertEqual(sum(e['ph'] == 's' for e in timeline['traceEvents']), 3)
        # Requested settings remain available without replacing observed settings.
        from usage_report import import_evidence
        events, _ = import_evidence(self.root)
        child = next(e for e in events if e['agent_id'] == 'codex:child' and e['turn_id'] == 'b2' and e['kind'] == 'model')
        self.assertEqual(child['requested'], dict(model='requested', reasoning_effort='low'))
        self.assertEqual(child['model'], 'observed')
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        # Offline refresh reconstructs attribution from saved dispatches and metadata.
        with patch.dict(os.environ, CODEX_HOME=str(self.base / 'missing')):
            offline = refresh(self.root).usage
        self.assertEqual(offline['summary']['tokens']['total_tokens']['known_subtotal'], 78)
        self.assertIn('native_storage_unavailable', offline['summary']['coverage'])
        self.assertEqual(offline['assignments'], report['assignments'])

    def test_missing_tags_ambiguous_identity_turns_and_missing_storage_keep_known_usage(self):
        rows = turn('root', 'r1', 100)
        rows += dispatch('spawn_agent', 'ambiguous', dict(task_name='same', message='Build'), dict(task_name='/root/same'))
        rows += dispatch('spawn_agent', 'known', dict(task_name='known', message='Build'), dict(agent_id='known'))
        rows += dispatch('followup_task', 'uncertain', dict(target='known', message='encrypted'), {}, 250)
        self.native('root', rows)
        for sid in ('same-a', 'same-b'):
            self.native(sid, turn(sid, sid + '-turn', 200), 'root', '/root/same', created=190)
        known = self.native('known', turn('known', 'k1', 200) + turn('known', 'k2', 300) + turn('known', 'k3', 400), 'root', '/root/known', created=190)
        self.allocate()
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['known_subtotal'], 26)
        self.assertIn('ambiguous_native_identity', report['summary']['coverage'])
        self.assertIn('ambiguous_dispatch_turn', report['summary']['coverage'])
        self.assertIn('missing_assignment', report['summary']['coverage'])
        self.assertEqual([row['key'] for row in report['groups']['task']], [{'task_id': None}])
        self.assertEqual(report['groups']['task'][0]['summary']['tokens']['total_tokens']['known_subtotal'], 26)
        self.assertEqual(report['groups']['role'], [])
        self.assertEqual(report['summary']['observed_model_measurements'], 2)
        known.unlink()
        # A missing host path must never rewrite or merge existing snapshots.
        (self.host / 'root.jsonl').unlink()
        canonical = self.root / 'native/root/r1.jsonl'
        (self.root / 'native/explicit.jsonl').write_bytes(canonical.read_bytes())
        copies = {p: p.read_bytes() for p in self.root.glob('native/**/*.jsonl')}
        unavailable = refresh(self.root).usage
        self.assertEqual({p: p.read_bytes() for p in copies}, copies)
        self.assertIn('native_source_unavailable', unavailable['summary']['coverage'])
        self.assertEqual(unavailable['summary']['tokens']['total_tokens']['known_subtotal'], 26)

    def test_messages_to_parent_keep_active_turn_and_exclude_later_unrelated_work(self):
        root_rows = turn('root', 'selected', 100, self.tag('orchestration', 'supervisor'), complete=False)
        root_rows += dispatch('spawn_agent', 'spawn', dict(task_name='worker', message=self.tag()), dict(agent_id='worker'), 110)
        root_rows.append(row('event_msg', dict(type='task_complete', turn_id='selected'), 400))
        native = self.native('root', root_rows)
        child_rows = turn('worker', 'work', 200, self.tag(), complete=False)
        child_rows += dispatch('send_message', 'during', dict(target='/root', message='Status'), {}, 250)
        child_rows += dispatch('send_message', 'after', dict(target='/root', message='Finished'), {}, 450)
        child_rows.append(row('event_msg', dict(type='task_complete', turn_id='work'), 460))
        self.native('worker', child_rows, 'root', '/root/worker', created=190)
        self.allocate()
        with native.open('ab') as stream:
            stream.write(b''.join((json.dumps(r) + '\n').encode() for r in turn('root', 'unrelated', 500)))
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['known_subtotal'], 26)
        self.assertEqual({t for n in report['spawn_tree']['nodes'] for t in n['turns']}, {'selected', 'work'})
        self.assertEqual(report['summary']['coverage']['ambiguous_dispatch_turn'], 1)

    def test_partial_utf8_tail_refresh_preserves_bytes_and_recovers_completed_record(self):
        rows = turn('root', 'active', 100, self.tag(), complete=False)
        native = self.native('root', rows)
        with native.open('ab') as f:
            f.write(b'{"type":"event_msg","note":"' + bytes([0xe2, 0x82]))
        self.allocate()
        report = refresh(self.root).usage
        self.assertIn('invalid_json_line', report['summary']['coverage'])
        self.assertEqual(report['summary']['tokens']['total_tokens']['known_subtotal'], 13)
        original = native.read_bytes()
        self.assertEqual((self.root / 'native/root/active.jsonl').read_bytes(), original)
        native.write_bytes(original + bytes([0xac]) + b'","timestamp":105,"payload":{"type":"task_complete","turn_id":"active"}}\n')
        report = refresh(self.root).usage
        self.assertEqual(report['summary']['tokens']['total_tokens']['total'], 13)
        self.assertNotIn('invalid_json_line', report['summary']['coverage'])
        self.assertEqual((self.root / 'native/root/active.jsonl').read_bytes(), native.read_bytes())

    def test_opaque_handoff_annotations_restore_assignments_without_changing_native_evidence(self):
        rows = turn('root', 'r1', 100, self.tag('orchestration', 'supervisor'))
        rows += dispatch('spawn_agent', 'spawn', dict(task_name='worker', message='opaque-handoff'), dict(agent_id='worker'))
        self.native('root', rows)
        child = turn('worker', 'w1', 200)
        child.append(row('event_msg', dict(type='item_completed', item=dict(
            type='SubAgentActivity', agent_thread_id='root', agent_path='/root', kind='interacted')), 201))
        self.native('worker', child, 'root', '/root/worker', created=190)
        self.allocate()
        baseline = refresh(self.root).usage
        copies = {p: p.read_bytes() for p in self.root.glob('native/**/*.jsonl')}
        (self.root / 'tasks/work').mkdir(parents=True)
        (self.root / 'tasks/work/acceptance.md').write_text('Selected task: work; worker role: implementer.\n')
        annotation = dict(adapter='codex', session_id='worker', turn_id='w1', task='work',
                          role='implementer', purpose='Build feature', evidence=['tasks/work/acceptance.md'])
        annotations = self.root / 'assignment-annotations.json'
        annotations.write_text(json.dumps(dict(version=1, assignments=[annotation])))
        report = refresh(self.root).usage
        by_agent = {a['agent_id']: a for a in report['assignments']}
        worker = by_agent['codex:worker']
        self.assertEqual((worker['task_id'], worker['role'], worker['purpose']), ('work', 'implementer', 'Build feature'))
        self.assertEqual(worker['assignment_source'], 'annotation')
        self.assertEqual(worker['assignment_evidence'], ['tasks/work/acceptance.md'])
        self.assertEqual(by_agent['codex:root']['native_agent_path'], '/root')
        self.assertNotIn('missing_assignment', report['summary']['coverage'])
        self.assertEqual(report['summary']['tokens'], baseline['summary']['tokens'])
        self.assertEqual({p: p.read_bytes() for p in copies}, copies)
        with patch.dict(os.environ, CODEX_HOME=str(self.base / 'missing')):
            offline = refresh(self.root).usage
        self.assertEqual(offline['assignments'], report['assignments'])
        # Annotations cannot select turns, override native tags, or escape the root.
        invalid = [dict(annotation, turn_id='unselected'),
                   dict(annotation, session_id='root', turn_id='r1'),
                   dict(annotation, evidence=['../outside.md'])]
        for entry in invalid:
            with self.subTest(entry=entry):
                annotations.write_text(json.dumps(dict(version=1, assignments=[entry])))
                with self.assertRaises(ValueError):
                    refresh(self.root)

    def test_delivered_agent_message_tags_are_attributed_to_recipient_only(self):
        self.native('root', turn('root', 'r1', 100, self.tag('orchestration', 'supervisor')) +
                    dispatch('spawn_agent', 'spawn', dict(task_name='worker', message='opaque-handoff'), dict(agent_id='worker')))
        child = turn('worker', 'w1', 200)
        for recipient, tag in [('/root/other', self.tag('other', 'reviewer')),
                               ('/root/worker', self.tag(purpose='Build feature'))]:
            child.append(row('response_item', dict(type='agent_message', author='/root', recipient=recipient,
                                                   content=[dict(type='input_text', text=tag)]), 201))
        self.native('worker', child, 'root', '/root/worker', created=190)
        self.allocate()
        report = refresh(self.root).usage
        worker = next(a for a in report['assignments'] if a['agent_id'] == 'codex:worker')
        self.assertEqual((worker['task_id'], worker['role'], worker['purpose']), ('work', 'implementer', 'Build feature'))
        self.assertEqual(worker['assignment_source'], 'native')


if __name__ == '__main__':
    unittest.main()
