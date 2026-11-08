"""Capture through public commands with a local export CLI fixture.

The fixture replaces only OpenCode's export process; selection, persistence,
refresh and reporting are real. A live CLI smoke check is separate.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HELPERS = Path(__file__).resolve().parents[1] / 'helpers'
FIXTURE = Path(__file__).parent / 'fixtures/opencode-2.2.6.json'
sys.path.insert(0, str(HELPERS))
from usage_report import refresh


class OpenCodeCaptureTests(unittest.TestCase):
    def test_capture_refresh_resume_and_export_failure_preserve_selected_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            host = base / 'host.json'
            data = json.loads(FIXTURE.read_text())
            tag = 'AGENTIC_WORKFLOW {"implementation":"001_demo","task":"orchestration","role":"supervisor"}'
            data['messages'][2]['text'] = 'Implement demo'
            data['messages'][3]['content'][0]['text'] = tag
            # Assignment examples inside tool output are not self-identification.
            data['messages'][3]['content'][1]['state']['content'][0]['text'] = (
                'AGENTIC_WORKFLOW {"implementation":"001_demo","task":"wrong","role":"reviewer"}')
            steering = dict(id='msg_steer', type='user', text='Also check errors', time=dict(created=3200))
            data['messages'].insert(3, steering)
            active = dict(data, messages=data['messages'][:4])
            host.write_text(json.dumps(active))
            binary = base / 'opencode'
            binary.write_text('#!' + sys.executable + '\nimport pathlib, sys\n'
                              'assert sys.argv[1:] == ["session", "export", "ses_fixture"]\n'
                              'print(pathlib.Path(' + repr(str(host)) + ').read_text())\n')
            binary.chmod(0o755)
            with patch.dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH'],
                            OPENCODE_SESSION_ID='ses_fixture', CODEX_THREAD_ID='wrong-codex'):
                result = subprocess.run([sys.executable, str(HELPERS / 'records.py'), 'allocate', 'demo',
                                         '--records-root', str(base / 'records')], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                root = Path(result.stdout.strip())
                snapshot = root / 'native/ses_fixture/msg_current.json'
                self.assertTrue(snapshot.is_file(), result.stderr)
                pending = refresh(root).usage
                self.assertIsNone(pending['summary']['tokens']['total_tokens']['total'])
                self.assertIn('unfinished_turn', pending['summary']['coverage'])
                host.write_text(json.dumps(data))
                report = refresh(root).usage
                self.assertEqual(report['summary']['tokens']['total_tokens']['total'], 75)
                self.assertEqual(report['summary']['tokens']['reasoning_output_tokens']['total'], 5)
                self.assertEqual(report['assignments'][0]['role'], 'supervisor')
                self.assertEqual(report['assignments'][0]['task_id'], 'orchestration')
                self.assertEqual(report['summary']['observed_tool_calls'], 1)
                self.assertEqual(report['summary']['outcomes'], {'completed': 1})
                self.assertEqual({s['session_id'] for s in report['native_sources']}, {'ses_fixture'})
                # Refresh includes new observations in the selected turn, but no new user turn.
                new_turn = [dict(id='msg_next', type='user', text='Unrelated', time=dict(created=7000))]
                data['messages'] += new_turn
                host.write_text(json.dumps(data))
                self.assertEqual(refresh(root).usage['summary']['tokens']['total_tokens']['total'], 75)
                saved = json.loads(snapshot.read_text())
                self.assertEqual([m['id'] for m in saved['messages']], ['msg_current', 'msg_steer', 'msg_step', 'msg_idle'])
                before = snapshot.read_bytes()
                host.write_text('invalid JSON')
                failed = refresh(root).usage
                self.assertEqual(snapshot.read_bytes(), before)
                self.assertIn('opencode_export_unavailable', failed['summary']['coverage'])
                self.assertIsNone(failed['summary']['tokens']['total_tokens']['total'])
                self.assertEqual(failed['summary']['tokens']['total_tokens']['known_subtotal'], 75)
                host.write_text(json.dumps(data))
                (root / 'tasks/work').mkdir()
                result = subprocess.run([sys.executable, str(HELPERS / 'records.py'), 'resolve', str(root), 'work'],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((root / 'native/ses_fixture/msg_next.json').is_file())
                resumed = refresh(root).usage
                self.assertNotIn('missing_assignment', resumed['summary']['coverage'])
                self.assertEqual(len(resumed['assignments']), 1)
                self.assertEqual(set(resumed['assignments'][0]['turns']), {'msg_current', 'msg_next'})

    def test_dispatch_selects_only_child_turn_with_matching_parent_and_call_time(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / '001_demo'
            data = json.loads(FIXTURE.read_text())
            task = data['messages'][3]['content'][1]
            task.update(name='subagent')
            task['state']['metadata'] = dict(sessionID='ses_child')
            child = json.loads(FIXTURE.read_text())
            child['info'].update(id='ses_child', parentID='ses_fixture')
            child['messages'][2]['time']['created'] = 4200
            child['messages'][3]['time']['created'] = 4300
            (base / 'ses_fixture.json').write_text(json.dumps(data))
            (base / 'ses_child.json').write_text(json.dumps(child))
            snapshot = root / 'native/ses_fixture/msg_current.json'
            snapshot.parent.mkdir(parents=True)
            data['messages'] = data['messages'][2:]
            snapshot.write_text(json.dumps(data))
            binary = base / 'opencode'
            binary.write_text('#!' + sys.executable + '\nimport pathlib, sys\n'
                              'assert sys.argv[1:3] == ["session", "export"]\n'
                              'print((pathlib.Path(' + repr(str(base)) + ') / (sys.argv[3] + ".json")).read_text())\n')
            binary.chmod(0o755)
            with patch.dict(os.environ, PATH=str(base) + os.pathsep + os.environ['PATH']):
                report = refresh(root).usage
                self.assertEqual(report['summary']['tokens']['total_tokens']['total'], 150)
                self.assertTrue((root / 'native/ses_child/msg_current.json').exists())
                self.assertFalse((root / 'native/ses_child/msg_old.json').exists())
                child['info'].update(id='ses_stranger', parentID='ses_elsewhere')
                (base / 'ses_stranger.json').write_text(json.dumps(child))
                task['state']['metadata']['sessionID'] = 'ses_stranger'
                (base / 'ses_fixture.json').write_text(json.dumps(data))
                report = refresh(root).usage
                self.assertIn('opencode_parent_mismatch', report['summary']['coverage'])
                self.assertFalse((root / 'native/ses_stranger').exists())


if __name__ == '__main__':
    unittest.main()
