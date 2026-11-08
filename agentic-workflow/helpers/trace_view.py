#!/usr/bin/env python3
"""Continuously capture selected native evidence and view agent insights.

implementation is an existing allocated implementation directory. --interval
SECONDS is positive and finite (default: 5); the owner waits this long after
each collection attempt; it also sets the browser poll interval.

Starts a foreground HTTP viewer on 127.0.0.1:9001 and attempts to open a
browser. Creates/uses implementation/.records.lock; refreshes saved native
turns and proven dispatch descendants under
implementation/native/<session-id>/<turn-id>.jsonl (Codex) or .json (OpenCode);
creates/overwrites implementation/reports/usage.json,
usage.md, events.json and timeline.json. Reuses a compatible viewer for the
same implementation and exits; the owner's interval remains in effect. Other
port occupants cause an error; stop the conflicting viewer or process before
retrying.

Prints the dashboard URL and refresh/coverage messages to stdout; open the URL
manually if browser launch is unavailable. Coverage gaps mean telemetry is
incomplete even when refresh succeeds; null means unavailable. Initial failure
exits 2 with stderr; later refresh failures print to stdout, keep the last
report visible and retry on the next cycle. Exit 0 means reuse or a stopped
viewer, not complete telemetry.

Retain the owner's shell session while capturing; it runs until Ctrl+C or
SIGTERM. Stop it after capture. Restart the owner to change --interval.

Example: python3 agentic-workflow/helpers/trace_view.py .agentic-workflow/records/001_example --interval 5
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import threading
import time
from urllib.parse import quote
from urllib.request import ProxyHandler, build_opener
import webbrowser

from trace_dashboard import render
from usage_report import ReportBundle, refresh

HOST, PORT = '127.0.0.1', 9001
ORIGIN = 'https://ui.perfetto.dev'
SERVICE = 'agentic-workflow-insights-v1'
# /status belongs to Perfetto's native RPC probe; it must remain a 404 here.
STATUS_PATH = '/__agentic_workflow_trace_viewer__'


def viewer_url(token):
    return f'http://{HOST}:{PORT}/{token}/'


def perfetto_url(token):
    source = f'http://{HOST}:{PORT}/{token}/timeline.json'
    return f'{ORIGIN}/#!/?url={quote(source, safe="")}&referrer=agentic-workflow'


@dataclass(frozen=True)
class Snapshot:
    bundle: ReportBundle
    html: bytes
    refreshed: str


class Viewer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, interval):
        self.root = root
        self.interval = interval
        self.snapshot = None
        self.initial_collection = threading.Event()
        self.token = secrets.token_hex(16)
        super().__init__((HOST, PORT), Handler)

    def collect(self):
        bundle = refresh(self.root)
        self.publish(bundle, datetime.now(timezone.utc).isoformat(timespec='seconds'))
        return bundle.usage

    def publish(self, bundle, refreshed, error=None):
        page = render(bundle.usage, perfetto_url(self.token) if bundle.timeline_available else None,
                      interval=self.interval, refreshed=refreshed, error=error, content=bundle.content)
        # Published bundles are never mutated. Each request captures one snapshot.
        self.snapshot = Snapshot(bundle, page.encode(), refreshed)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, code, data=b'', content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Access-Control-Allow-Origin', ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return (self.headers.get('Host') == f'{HOST}:{PORT}' and
                self.headers.get('Origin') in (None, ORIGIN))

    def do_OPTIONS(self):
        self.reply(204 if self.allowed() else 403)

    def do_GET(self):
        if not self.allowed():
            self.reply(403)
        elif self.path == STATUS_PATH:
            self.reply(200, json.dumps(dict(service=SERVICE, implementation=str(self.server.root),
                                           token=self.server.token, pid=os.getpid(),
                                           interval=self.server.interval)).encode())
        elif self.path in (f'/{self.server.token}/', f'/{self.server.token}/usage.json',
                           f'/{self.server.token}/timeline.json', f'/{self.server.token}/events.json'):
            # Identity is available while initial collection waits on the
            # implementation lock, but pages must wait for its first result.
            self.server.initial_collection.wait()
            snapshot = self.server.snapshot
            if snapshot is None:
                self.reply(503)
            elif self.path.endswith('/'):
                self.reply(200, snapshot.html, 'text/html; charset=utf-8')
            else:
                self.reply(200, snapshot.bundle.files[self.path.rsplit('/', 1)[1]])
        else:
            self.reply(404)


def existing_viewer(root):
    """Check identity before reusing a listener; never kill a port occupant."""
    opener = build_opener(ProxyHandler({}))
    for _ in range(10):
        try:
            with opener.open(f'http://{HOST}:{PORT}{STATUS_PATH}', timeout=.2) as response:
                status = json.loads(response.read(8192))
            if (status.get('service') == SERVICE and status.get('implementation') == str(root)
                    and re.fullmatch(r'[0-9a-f]{32}', status.get('token', ''))):
                return status
            break
        except (OSError, ValueError, AttributeError, TypeError):
            time.sleep(.1)  # A concurrently starting viewer may not yet be serving.
    raise ValueError(f'Port {PORT} is occupied by another process, implementation or older viewer; stop that viewer before retrying.')


def open_browser(url):
    print(f'Agent insights: {url}', flush=True)
    print('Use “Open timeline in Perfetto” for timing; allow local-device access if prompted.', flush=True)
    try:
        opened = webbrowser.open(url, new=0)
    except (OSError, webbrowser.Error):
        opened = False
    if not opened:
        print('Browser launch unavailable. Open the dashboard URL above on this machine.', flush=True)


def positive_interval(value):
    try:
        interval = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('interval must be positive and finite') from None
    if not math.isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError('interval must be positive and finite')
    return interval


def wait_interval(interval):
    # Bound individual sleeps so even very large finite intervals are supported.
    started = time.monotonic()
    while (remaining := interval - (time.monotonic() - started)) > 0:
        time.sleep(min(remaining, 3600))


def run(root, interval=5):
    root = Path(root).resolve()
    try:
        server = Viewer(root, interval)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        status = existing_viewer(root)
        print(f'Reusing the running viewer (interval {status["interval"]:g}s). '
              'Restart the owning viewer to change its interval.', flush=True)
        open_browser(viewer_url(status['token']))
        return
    with server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            # Initial failures remain command errors; only the owner collects.
            report = server.collect()
            server.initial_collection.set()
            print(f'Refreshed {report["implementation_id"]}: {root / "reports"}', flush=True)
            if not report['summary']['observed_model_measurements'] and not report['summary']['observed_tool_calls']:
                print('No imported execution observations in this report; the viewer cannot reconstruct missing native evidence.', flush=True)
            if report['summary']['coverage']:
                print('Coverage: ' + json.dumps(report['summary']['coverage'], sort_keys=True), flush=True)
            print(f'Serving agent insights locally; refreshing every {interval:g}s after collection. '
                  'Ctrl+C stops collection and serving.', flush=True)
            open_browser(viewer_url(server.token))
            while True:
                wait_interval(interval)
                try:
                    server.collect()
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    previous = server.snapshot
                    server.publish(previous.bundle, previous.refreshed, 'Refresh failed; retrying on the next cycle.')
                    print(f'trace-view: refresh failed: {exc}', flush=True)
        finally:
            server.initial_collection.set()
            server.shutdown()
            worker.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('implementation', type=Path, help='existing implementation directory')
    parser.add_argument('--interval', type=positive_interval, default=5,
                        metavar='SECONDS', help='collection and browser poll interval (default: 5; restart viewer to change)')
    args = parser.parse_args()
    def stop(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        run(args.implementation, args.interval)
    except KeyboardInterrupt:
        print('\nViewer stopped.', flush=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'trace-view: {exc}\n')


if __name__ == '__main__':
    main()
