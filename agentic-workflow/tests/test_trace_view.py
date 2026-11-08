"""Public Make/HTTP lifecycle checks using real processes and disposable native sources.

BROWSER points to a recording executable: browser-window behavior is checked by
separate real-UI smoke evidence, while these tests verify the actual launch URL.
Port 9001 must be free; no unrelated process is terminated to run these checks.
"""
from concurrent.futures import ThreadPoolExecutor
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
from html import unescape
import json
import os
import re
from pathlib import Path
import shlex
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, ProxyHandler, build_opener

PACKAGE = Path(__file__).resolve().parents[1]
HELPERS = PACKAGE / 'helpers'
sys.path.insert(0, str(HELPERS))
import records
from unittest.mock import patch


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workflow viewer ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.http = build_opener(ProxyHandler({}))
        try:
            self.http.open('http://127.0.0.1:9001/__agentic_workflow_trace_viewer__', timeout=.2).close()
        except HTTPError as exc:
            exc.close()
            self.fail('Port 9001 is occupied; stop the local viewer before running tests.')
        except URLError:
            pass
        else:
            self.fail('Port 9001 is occupied; stop the local viewer before running tests.')
        self.environment = patch.dict(os.environ, CODEX_HOME=str(self.base), CODEX_THREAD_ID='')
        self.environment.start()
        self.addCleanup(self.environment.stop)
        c = sqlite3.connect(str(self.base / 'state_5.sqlite'))
        c.execute('CREATE TABLE threads (id TEXT, rollout_path TEXT, source TEXT)')
        c.commit()
        c.close()
        self.root = self.implementation('demo')
        self.browser_log = self.base / 'browser.jsonl'
        browser = self.base / 'browser.py'
        browser.write_text('import os,sys,json\nwith open(os.environ["TRACE_BROWSER_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n')
        self.env = dict(os.environ, BROWSER=shlex.join([sys.executable, str(browser), '%s']),
                        TRACE_BROWSER_LOG=str(self.browser_log))
        self.processes = []
        self.addCleanup(self.stop_all)

    def implementation(self, name):
        root = records.allocate(self.base / '.agentic-workflow/records', name)
        path = root / 'native' / 'capture.jsonl'
        path.parent.mkdir()
        rows = [json.loads(line) for line in (PACKAGE / 'tests/fixtures/codex-0.167.0.jsonl').read_text().splitlines()]
        rows[0]['payload']['agent_nickname'] = 'Builder <one>'
        selected = []
        active = None
        for row in rows:
            active = row['payload'].get('turn_id') or active
            if active == 'unselected':
                continue
            selected.append(row)
            if row['type'] == 'turn_context':
                tag = dict(implementation=root.name, task='work', role='implementer', purpose='Implement <script>alert(1)</script>')
                selected.append(dict(timestamp=row['timestamp'], type='response_item', payload=dict(
                    type='message', role='user', content=[dict(type='input_text', text='AGENTIC_WORKFLOW ' + json.dumps(tag))])))
        path.write_text(''.join(json.dumps(r) + '\n' for r in selected))
        return root

    @unittest.skipUnless(os.environ.get('PLAYWRIGHT_MODULE'), 'optional real browser unavailable')
    def test_browser_content_search_selection_refresh_and_inert_payloads(self):
        native = self.root / 'native/capture.jsonl'
        marker = 'Unicode 雪\nprint("snow")\n</script><script>globalThis.injected=true</script>\n' + 'long content\n' * 200
        with native.open('a') as stream:
            for i in range(60):
                stream.write(json.dumps(dict(timestamp=1793959261, type='response_item', payload=dict(
                    type='message', id=f'browser-{i}', turn_id='turn-2', role='assistant', content=marker))) + '\n')
        self.launch(interval=.2)
        _, urls = self.ready()
        result = subprocess.run(['node', str(Path(__file__).with_name('trace_dashboard_browser.cjs')), urls[0], str(native)],
                                env=self.env, capture_output=True, text=True, timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def command(self, root=None, interval=None):
        # Run the portable CLI from another cwd with paths containing spaces.
        return [sys.executable, str(HELPERS / 'trace_view.py'), str(root or self.root),
                *([] if interval is None else [f'--interval={interval}'])]

    def launch(self, interval=None):
        output = tempfile.TemporaryFile(mode='w+')
        process = subprocess.Popen(self.command(interval=interval), cwd=self.base, env=self.env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((process, output))
        return process

    def stop_all(self):
        for process, output in self.processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            output.close()
        self.processes.clear()

    def status(self):
        with self.http.open('http://127.0.0.1:9001/__agentic_workflow_trace_viewer__', timeout=.5) as response:
            return json.load(response)

    def ready(self, browser_calls=1):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                status = self.status()
                lines = self.browser_log.read_text().splitlines()
                if len(lines) >= browser_calls:
                    return status, [json.loads(line)[0] for line in lines]
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        self.fail('Viewer/browser did not become ready')

    def wait_for(self, read, predicate):
        deadline = time.monotonic() + 8
        value = None
        while time.monotonic() < deadline:
            value = read()
            if predicate(value):
                return value
            time.sleep(.05)
        self.fail(f'Viewer did not update: {str(value)[:1000]}')

    def dashboard(self, url):
        with self.http.open(url, timeout=1) as response:
            return response.read().decode()

    def test_completed_snapshot_survives_blocked_refresh_disk_replacement_and_failure(self):
        self.launch(interval=.1)
        _, urls = self.ready()
        url, native = urls[0], self.root / 'native/capture.jsonl'
        names = ('usage.json', 'events.json', 'timeline.json')
        before = {name: self.dashboard(url + name) for name in names}
        reports, parked = self.root / 'reports', self.root / 'parked-reports'
        private = self.base / 'private'
        private.mkdir()
        for name in names:
            (private / name).write_text('{"private_prompt":"SYNTHETIC_PRIVATE_NATIVE"}')
        with (self.root / '.records.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            native.write_text(native.read_text().replace('model-a', 'snapshot-B'))
            with native.open('a') as stream:
                stream.write(json.dumps(dict(timestamp=1793959262, type='response_item', payload=dict(
                    type='message', id='snapshot-B', turn_id='turn-2', role='assistant', content='Snapshot B arrived'))) + '\n')
            time.sleep(.15)  # Let the next collection reach the held lock.
            page = self.dashboard(url)
            reports.rename(parked)
            reports.symlink_to(private, target_is_directory=True)
            try:
                self.assertEqual(self.dashboard(url), page)
                self.assertEqual({name: self.dashboard(url + name) for name in names}, before)
            finally:
                reports.unlink()
                parked.rename(reports)
            for name in names:
                (reports / name).write_text('SENTINEL_DISK_EXPORT')
            self.assertEqual(self.dashboard(url), page)
            self.assertEqual({name: self.dashboard(url + name) for name in names}, before)
        page = self.wait_for(lambda: self.dashboard(url), lambda text: 'Snapshot B arrived' in text)
        summary, embedded = page.split('<script id="event-data" type="application/json">', 1)
        self.assertIn('snapshot-B', summary)
        content = json.loads(embedded.split('</script>', 1)[0])
        self.assertTrue(any(e.get('native_record', {}).get('id') == 'snapshot-B' for e in content['events']))
        successful = {name: self.dashboard(url + name) for name in names}
        self.assertTrue(any(e.get('native_record', {}).get('id') == 'snapshot-B'
                            for e in json.loads(successful['events.json'])['events']))
        self.assertTrue(any(row['key']['model'] == 'snapshot-B'
                            for row in json.loads(successful['usage.json'])['groups']['model']))
        annotations = self.root / 'assignment-annotations.json'
        annotations.write_text('{')
        failed = self.wait_for(lambda: self.dashboard(url), lambda text: 'data-error="Refresh failed;' in text)
        last_success = re.search(r'<time>(.*?)</time>', failed)[1]
        native.write_text(native.read_text().replace('snapshot-B', 'recovered-model'))
        time.sleep(.15)
        self.assertIn(f'<time>{last_success}</time>', self.dashboard(url))
        self.assertEqual({name: self.dashboard(url + name) for name in names}, successful)
        annotations.unlink()
        self.wait_for(lambda: self.dashboard(url), lambda text: 'recovered-model' in text and 'data-error=""' in text)

    def test_command_errors_and_headless_browser_fallback(self):
        for interval in ('0', '-1', 'nan', 'inf', '-inf', 'abc'):
            with self.subTest(interval=interval):
                result = subprocess.run(self.command(interval=interval), cwd=self.base, env=self.env,
                                        capture_output=True, text=True, timeout=8)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('interval must be positive and finite', result.stderr)
        (self.root / 'assignment-annotations.json').write_text('{')
        result = subprocess.run(self.command(), cwd=self.base, env=self.env,
                                capture_output=True, text=True, timeout=8)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('trace-view:', result.stderr)
        self.assertFalse(self.browser_log.exists())
        with self.assertRaises(URLError):
            self.status()

        (self.root / 'assignment-annotations.json').unlink()
        env = dict(os.environ, PATH=str(self.base), BROWSER='/missing-browser %s')
        env.pop('DISPLAY', None)
        env.pop('WAYLAND_DISPLAY', None)
        path = self.base / 'headless.log'
        output = path.open('w')
        process = subprocess.Popen([sys.executable, str(HELPERS/'trace_view.py'), str(self.root)],
                                   cwd=self.base, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        self.processes.append((process,output))
        content = self.wait_for(path.read_text, lambda text: 'Browser launch unavailable' in text)
        self.assertIn('Browser launch unavailable', content)
        self.assertIn('Agent insights: http://127.0.0.1:9001/', content)
        self.assertEqual(self.status()['implementation'], str(self.root))

    def test_http_boundary_for_populated_and_empty_recordings(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                if empty:
                    self.root = records.allocate(self.base / '.agentic-workflow/records', 'empty')
                self.launch()
                status, urls = self.ready()
                self.assertEqual(status['interval'], 5)
                self.assertEqual(urlsplit(urls[0]).netloc, '127.0.0.1:9001')
                with self.http.open(urls[0]) as response:
                    self.assertIn('text/html', response.headers['Content-Type'])
                    dashboard = response.read().decode()
                if empty:
                    self.assertIn('No imported execution observations', dashboard)
                    self.assertIn('No timeline events to display', dashboard)
                    self.assertNotIn('id="perfetto" href=', dashboard)
                else:
                    self.assertIn('Builder &lt;one&gt;', dashboard)
                    self.assertIn('Implement &lt;script&gt;', dashboard)
                    self.assertNotIn('<script>alert(1)</script>', dashboard)
                    perfetto = unescape(re.search(r'id="perfetto" href="([^"]+)"', dashboard)[1])
                    self.assertEqual(urlsplit(perfetto).netloc, 'ui.perfetto.dev')
                    trace_url = parse_qs(urlsplit(perfetto).fragment.split('?', 1)[1])['url'][0]
                    with self.http.open(Request(trace_url, headers={'Origin':'https://ui.perfetto.dev'})) as response:
                        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'https://ui.perfetto.dev')
                        self.assertTrue(any(e['ph'] != 'M' for e in json.load(response)['traceEvents']))
                    with self.assertRaises(HTTPError) as failure:
                        self.http.open(Request(trace_url, headers={'Origin':'https://unrelated.invalid'}))
                    self.assertEqual(failure.exception.code, 403)
                    failure.exception.close()
                for name, key in [('usage.json', 'summary'), ('events.json', 'events'), ('timeline.json', 'traceEvents')]:
                    self.assertIn(key, json.loads(self.dashboard(urls[0] + name)))
                for path in ('/', '/status', '/implementation.json', '/native.jsonl', '/../native.jsonl',
                             f'/{status["token"]}/../native/capture.jsonl', f'/{status["token"]}/native/capture.jsonl'):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as failure:
                        self.http.open('http://127.0.0.1:9001' + path)
                    self.assertEqual(failure.exception.code, 404)
                    failure.exception.close()
                self.stop_all()
                self.browser_log.unlink()

    def test_concurrent_cli_invocations_and_shutdown_restart(self):
        # Hold the real collection lock: reuse must work even before the owner
        # finishes its first pass, without launching a second collector.
        with (self.root / '.records.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with ThreadPoolExecutor(max_workers=2) as pool:
                processes = list(pool.map(lambda _:self.launch(), range(2)))
            self.ready(1)
            deadline = time.monotonic()+5
            while all(p.poll() is None for p in processes) and time.monotonic()<deadline:
                time.sleep(.05)
            self.assertEqual(sum(p.poll() is None for p in processes), 1)
            self.assertEqual([p.returncode for p in processes if p.poll() is not None], [0])
        status, urls = self.ready(2)
        self.assertEqual(urls[0], urls[1])
        repeat = subprocess.run(self.command(interval=.02), cwd=self.base, env=self.env, capture_output=True, text=True, timeout=8)
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertIn('Restart the owning viewer', repeat.stdout)
        self.assertEqual(self.status(), status)
        other = self.implementation('other')
        rejected = subprocess.run(self.command(other), cwd=self.base, env=self.env, capture_output=True, text=True, timeout=8)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('occupied', rejected.stderr)
        self.assertEqual(self.status()['pid'], status['pid'])
        self.stop_all()
        with self.assertRaises(URLError):
            self.status()
        self.launch()
        restarted, _ = self.ready(4)
        self.assertNotEqual(restarted['pid'], status['pid'])

        self.stop_all()
        before = self.browser_log.read_bytes()
        class Unrelated(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"service":"unrelated"}')
            def log_message(self,*args):
                pass
        with HTTPServer(('127.0.0.1',9001),Unrelated) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                result=subprocess.run(self.command(),cwd=self.base,env=self.env,capture_output=True,text=True,timeout=8)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('occupied',result.stderr)
                self.assertEqual(self.browser_log.read_bytes(), before)
                self.assertEqual(self.status()['service'],'unrelated')
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    unittest.main()
