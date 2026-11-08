"""Presentation of usage and recorded content; no native reads or token arithmetic."""
from html import escape
import json
from usage_report import format_settings

GROUPS = {
    'task': 'Task', 'agent_run': 'Agent run', 'role': 'Role', 'model': 'Model',
    'effort': 'Reasoning effort', 'model_effort': 'Model + effort',
    'task_model_effort': 'Task + model + effort', 'tool': 'Tool', 'task_tool': 'Task + tool',
}
MODEL_GROUPS = {'model', 'effort', 'model_effort', 'task_model_effort'}
TOOL_GROUPS = {'tool', 'task_tool'}


def text(value):
    return escape(str(value) if value is not None else 'Unavailable', quote=True)


def number(value):
    return f'{value:,}' if value is not None else 'Unavailable'


def measurement(metric):
    if metric['total'] is not None:
        return number(metric['total'])
    if metric['known_subtotal'] is not None:
        return number(metric['known_subtotal'])
    return 'Unavailable'


def table(headers, rows, **attrs):
    attributes = ' '.join(f'{key}="{text(value)}"' for key, value in attrs.items())
    head = ''.join(f'<th scope="col">{text(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{text(c)}</td>' for c in row) + '</tr>' for row in rows)
    if not rows:
        body = f'<tr><td colspan="{len(headers)}">No attributed observations in this selection.</td></tr>'
    return f'<div class="scroll"><table {attributes}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def render(report, perfetto_url, *, interval=5, refreshed=None, error=None, content=None):
    summary = report['summary']
    assignments = report['assignments']
    task_roles = {}
    for assignment in assignments:
        task_roles.setdefault(assignment['task_id'], set()).add(assignment['role'] or 'Unknown')
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Agent trace insights</title><style>', CSS, '</style><body>',
             f'<main data-interval="{text(interval)}">',
             f'<p id="refresh-status" role="status" data-error="{text(error or "")}">'
             f'Last successful refresh: <time>{text(refreshed)}</time> · '
             f'Polling every {text(interval)}s. Display updates pause while a dropdown has focus or text is highlighted. '
             f'<span id="refresh-error">{text(error or "")}</span></p>',
             '<div id="pause-notice" hidden><span role="status"><strong>Display updates paused</strong>'
             '<br>Collection continues. Resume clears the highlight and releases the dropdown.</span>'
             '<button id="resume-updates" type="button">Resume updates</button></div>',
             '<div id="report-content">',
             '<header><div><p class="eyebrow">LOCAL EXECUTION EVIDENCE</p><h1>Agent trace insights</h1>',
             f'<p>{text(report["implementation_id"])}</p></div><nav>',
             (f'<a class="button" id="perfetto" href="{text(perfetto_url)}" target="_blank" rel="noreferrer">Open timeline in Perfetto ↗</a>'
              if perfetto_url else '<span id="timeline-empty">No timeline events to display</span>'),
             '<a href="usage.json">Usage JSON</a><a href="events.json">Content JSON</a></nav></header>',
             '<p class="notice">Scope: saved native turns and proven dispatch descendants. Updates are collected automatically. '
             'Unfinished evidence does not establish that an agent is currently running. '
             'Token totals may be partial when work is unfinished, trace records are missing, or coverage cannot be verified. '
             'In those cases, displayed numbers include only known usage; actual usage may be higher. '
             'See Coverage and interpretation below for details. Unavailable is never zero.</p>']
    if not summary['observed_model_measurements'] and not summary['observed_tool_calls']:
        parts += ['<section role="status"><h2>No imported execution observations</h2>'
                  '<p>This report contains no model usage or tool observations. Missing observations do not mean '
                  'the work did not run. The viewer cannot reconstruct missing native evidence.</p>'
                  '<p>Check the implementation’s saved native files and coverage diagnostics. '
                  'Allocation and task resolution capture the active native turn; make trace refreshes it.</p></section>']
    parts.append('<div class="cards">')
    for label, key in [('Total tokens', 'total_tokens'), ('Input tokens', 'input_tokens'),
                       ('Cached input', 'cached_input_tokens'), ('Output tokens', 'output_tokens'),
                       ('Reasoning output', 'reasoning_output_tokens')]:
        metric = summary['tokens'][key]
        parts.append(f'<article><span>{label}</span><strong>{text(measurement(metric))}</strong>'
                     f'<small>{metric["measured_records"]} measured / {metric["missing_records"]} missing records</small></article>')
    parts += [f'<article><span>Observed tool calls</span><strong>{number(summary["observed_tool_calls"])}</strong>'
              f'<small>{summary["wrapper_calls"]} wrappers · {summary["observed_nested_operations"]} parented nested operations</small></article>',
              '</div><p class="hint">Input includes cache reads and writes; output includes reasoning. These are overlapping breakdowns, '
              'not values to add together. Model measurements represent native usage records, not necessarily all API requests.</p>',
              '<section aria-labelledby="group-title"><h2 id="group-title">Explore usage</h2><div class="controls">',
              '<label>Group by <select id="group">']
    parts += [f'<option value="{name}">{label}</option>' for name, label in GROUPS.items()]
    parts += ['</select></label><label>Find in this table <input id="search" type="search" placeholder="Task, model, tool…"></label>',
              '<span id="matches" aria-live="polite"></span></div>']
    for name, title in GROUPS.items():
        rows = report['groups'][name]
        fields = list(rows[0]['key']) if rows else []
        headers = [f.replace('_', ' ').title() for f in fields]
        if name == 'task':
            headers += ['Role']
        values = []
        if name in TOOL_GROUPS:
            headers += ['Observed calls', 'Outcomes', 'Wrapper calls', 'Parented nested', 'Observed duration (s)', 'Timed / untimed']
            for row in rows:
                s = row['summary']
                duration = s['observed_operation_seconds']
                values.append([*row['key'].values(), number(s['observed_tool_calls']),
                               ', '.join(f'{k}: {v}' for k, v in s['outcomes'].items()) or 'Unavailable',
                               s['wrapper_calls'], s['observed_nested_operations'],
                               f'{duration:,.3f}' if duration is not None else 'Unavailable',
                               f'{s["timed_operations"]} / {s["untimed_operations"]}'])
        else:
            metrics = ('total_tokens', 'input_tokens', 'cached_input_tokens', 'uncached_input_tokens',
                       'output_tokens', 'reasoning_output_tokens')
            headers += ['Total tokens', 'Input', 'Cache read', 'Uncached input', 'Output', 'Reasoning', 'Model measurements']
            if name not in MODEL_GROUPS:
                headers += ['Observed tools']
            for row in rows:
                s = row['summary']
                labels = list(row['key'].values())
                if name == 'task':
                    labels = [label if label is not None else 'Unknown' for label in labels]
                    labels.append(', '.join(sorted(task_roles.get(row['key']['task_id'], {'Unknown'}))))
                values.append([*labels, *(measurement(s['tokens'][m]) for m in metrics),
                               s['observed_model_measurements'],
                               *([] if name in MODEL_GROUPS else [s['observed_tool_calls']])])
        omitted = report['attribution_omissions'][name]
        parts += [f'<div class="group" id="group-{name}"{ " hidden" if name != "task" else ""}>',
                  f'<h3>By {title.lower()}</h3>', table(headers, values),
                  f'<p class="hint">Attribution omitted: {len(omitted["event_ids"])} events; '
                  f'{omitted["diagnostics_without_attribution"]} diagnostics lack this grouping. '
                  'Model/effort tables contain model measurements; tool tables contain tool observations.</p></div>']
    parts += ['<p class="hint">Tool durations sum observed endpoints and may overlap; they are not wall-clock time. '
              '“Returned” means a result was received, not confirmed success. Wrapper calls may contain operations not exposed '
              'by the native source; missing parent-call relationships cannot prove that no nested work occurred.</p></section>',
              '<section><h2>Agents and assignments</h2><p class="hint">Names come from native metadata or structured AGENTIC_WORKFLOW assignments. '
              'Assignment source distinguishes native tags from explicit recovery annotations. '
              'When a purpose was not recorded, the role and task are shown explicitly as assignment context. '
              'A reused agent can have multiple assignments. Model / effort lists observed native settings; '
              'multiple pairs indicate settings changes, and unavailable values are not inferred from requests.</p>']
    parts.append(table(['Agent', 'Observed model / effort', 'Purpose / assignment', 'Task', 'Role', 'Run', 'Observed status', 'Native path', 'Assignment source'],
                       [[a['agent_name'], format_settings(a.get('observed_settings', [])),
                         a['purpose'] or f'Assignment: {a["role"] or "unavailable role"} / {a["task_id"] or "unavailable task"}',
                         a['task_id'], a['role'], a['agent_run_id'], ', '.join(a['outcomes']) or 'Unavailable',
                         a['native_agent_path'], a.get('assignment_source')] for a in assignments], id='assignments'))
    names = {a['agent_id']: f'{a["agent_name"] or a["agent_id"]} [{a["agent_run_id"] or "unassigned"}]' for a in assignments}
    parts += ['<details id="native-lineage"><summary>Native lineage and identities</summary>',
              table(['Parent', 'Relationship', 'Child'],
                    [[names.get(e['parent'], e['parent']), e['relationship'], names.get(e['child'], e['child'])]
                     for e in report['spawn_tree']['edges']]),
              table(['Agent / run', 'Native identity'], [[name, aid] for aid, name in sorted(names.items())]),
              '</details></section><section><h2>Coverage and interpretation</h2>',
              table(['Diagnostic', 'Occurrences'], list(summary['coverage'].items())),
              '<p>Snapshot exclusions are deliberate deduplication, not missing counters. Other diagnostics may limit totals. '
              'The JSON report includes scoped diagnostics and attribution omissions.</p><ul>']
    parts += [f'<li>{text(limit)}</li>' for limit in report['limitations']]
    payload = json.dumps(content or {'events': [], 'timing_omissions': []}, ensure_ascii=True)
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    parts += ['</ul></section>', INSPECTOR,
              '<script id="event-data" type="application/json">', payload, '</script>',
              '<footer>Perfetto needs internet and may request local-device access. '
              'Perfetto is a snapshot; open it again for newer timing data. '
              'This summary stays local. Stop collection and serving with Ctrl+C in the owning terminal.</footer>',
              '</div></main><script>', SCRIPT, '</script></body></html>']
    return ''.join(parts)


INSPECTOR = '''
<section id="inspector"><h2>Recorded content</h2>
<p class="hint">Full recorded content from selected turns. This is not a reconstruction of the assembled model request.
Untimed observations appear after timed events. Encrypted, missing and upstream-truncated content is labeled when recorded.</p>
<div class="event-controls controls">
<label>Agent<select id="event-agent"></select></label>
<label>Task<select id="event-task"></select></label>
<label>Event type<select id="event-kind"></select></label>
<label>Tool<select id="event-tool"></select></label>
<label>Search full content<input id="event-search" type="search"></label></div>
<p id="event-count" aria-live="polite"></p><p id="event-omissions" class="hint"></p>
<div class="event-layout"><div id="event-list" class="scroll" tabindex="0"></div>
<div id="event-detail" class="scroll" tabindex="0">Select an event to inspect its full content.</div></div></section>
'''


CSS = '''
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#203044;background:#f3f6f9}
#pause-notice{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:10;display:flex;align-items:center;gap:16px;width:max-content;max-width:calc(100% - 32px);padding:14px 18px;background:#fff3cd;color:#584300;border:1px solid #d4ae43;border-radius:8px;box-shadow:0 4px 16px #20304426;font-size:13px}
#resume-updates{flex-shrink:0;padding:9px 12px;border:1px solid #806300;border-radius:5px;background:white;color:#584300;font:inherit;font-weight:600;cursor:pointer}
.event-layout{display:grid;grid-template-columns:minmax(250px,1fr) minmax(300px,2fr);gap:20px}
#event-list,#event-detail{max-height:650px;overflow:auto}#event-detail pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}
#event-list button{display:block;width:100%;text-align:left;padding:12px;border:0;border-bottom:1px solid #dbe2e9;background:white;color:inherit;cursor:pointer}
#event-list button[aria-pressed="true"]{background:#d9edf2}#event-detail h3{overflow-wrap:anywhere}
.content-value{padding-left:14px;border-left:1px solid #dbe2e9}
@media(max-width:720px){.event-layout{grid-template-columns:1fr}}
*{box-sizing:border-box}body{margin:0}main{max-width:1680px;margin:auto;padding:32px}
header{display:flex;justify-content:space-between;gap:24px;align-items:center}h1{margin:0;font-size:30px;letter-spacing:-.7px}
h2{font-size:21px}h3{font-size:16px}.eyebrow{font-size:11px;letter-spacing:2px;color:#45717d;font-weight:700}
nav{display:flex;align-items:center;gap:20px;flex-wrap:wrap}a{color:#096577}.button{background:#126574;color:white;padding:12px 18px;border-radius:6px;text-decoration:none}
.notice{border-left:3px solid #569aac;padding:12px 16px;background:#e7f1f4;font-size:14px}.hint,small,footer{color:#58697a;font-size:13px;line-height:1.6}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(195px,1fr));gap:12px;margin:24px 0 12px}
article,section{background:white;border:1px solid #dbe2e9;border-radius:8px}article{padding:18px}article span,article strong,article small{display:block}article span{font-size:13px}article strong{font-size:24px;margin:8px 0;font-variant-numeric:tabular-nums}
section{padding:22px;margin:24px 0}.controls{display:flex;gap:20px;align-items:end;flex-wrap:wrap;margin-bottom:20px}label{display:grid;gap:7px;font-size:13px;font-weight:600}input,select{padding:9px 12px;border:1px solid #aebdca;border-radius:5px;background:white;color:inherit;font:inherit;min-width:220px}
.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th{background:#edf2f6;font-weight:600;white-space:nowrap}th,td{padding:12px;border-bottom:1px solid #e1e7ed;vertical-align:top}td{font-variant-numeric:tabular-nums;overflow-wrap:anywhere}tbody tr:hover{background:#f7fafc}summary{cursor:pointer;padding:16px 0;color:#096577}footer{padding-bottom:20px}#matches{font-size:13px;color:#58697a}[hidden]{display:none!important}@media(max-width:720px){main{padding:16px}header{align-items:start;flex-direction:column}section{padding:14px}}
'''

SCRIPT = '''
const group = document.querySelector('#group'), search = document.querySelector('#search');
function update() {
  let shown = 0, total = 0;
  document.querySelectorAll('.group').forEach(panel => {
    panel.hidden = panel.id !== 'group-' + group.value;
    if (!panel.hidden) panel.querySelectorAll('tbody tr').forEach(row => {
      total++;
      row.hidden = !row.textContent.toLowerCase().includes(search.value.toLowerCase());
      if (!row.hidden) shown++;
    });
  });
  document.querySelector('#matches').textContent = shown + ' of ' + total + ' rows';
}
group.addEventListener('change', () => { search.value = ''; update(); });
search.addEventListener('input', update);
update();

const inspector = document.querySelector('#inspector');
const eventList = inspector.querySelector('#event-list'), eventDetail = inspector.querySelector('#event-detail');
const eventSearch = inspector.querySelector('#event-search');
const eventFilters = [['agent', 'agent_id'], ['task', 'task_id'], ['kind', 'kind'], ['tool', 'tool_name']];
let events = [], selectedEvent = null;
let eventSearchText = new Map();
function searchableText(value) {
  if (value && typeof value === 'object') {
    return Object.entries(value).map(([key, part]) => key + '\\n' + searchableText(part)).join('\\n');
  }
  return String(value);
}
function appendText(parent, tag, value) {
  const node = document.createElement(tag);
  node.textContent = value;
  parent.append(node);
  return node;
}
function showValue(parent, label, value) {
  appendText(parent, 'h3', label);
  if (typeof value === 'string') appendText(parent, 'pre', value);
  else if (value && typeof value === 'object' && Object.keys(value).length) {
    const nested = document.createElement('div');
    nested.className = 'content-value';
    parent.append(nested);
    Object.entries(value).forEach(([key, part]) => showValue(nested, key, part));
  }
  else appendText(parent, 'pre', JSON.stringify(value));
}
function showEvent() {
  const position = [eventDetail.scrollLeft, eventDetail.scrollTop];
  const nativeOpen = Boolean(eventDetail.querySelector('details[open]'));
  eventDetail.replaceChildren();
  const event = events.find(e => e.event_id === selectedEvent);
  if (!event) {
    eventDetail.textContent = selectedEvent ? 'Selected event is no longer available.' : 'Select an event to inspect its full content.';
    return;
  }
  appendText(eventDetail, 'h3', event.name || event.kind);
  const {content, outputs, instructions, native_record, ...metadata} = event;
  appendText(eventDetail, 'pre', JSON.stringify(metadata, null, 2));
  if (content) showValue(eventDetail, 'Content', content);
  if (outputs) showValue(eventDetail, 'Outputs', outputs);
  if (instructions) showValue(eventDetail, 'Recorded instruction context', instructions);
  if (native_record) {
    const native = document.createElement('details');
    native.open = nativeOpen;
    appendText(native, 'summary', 'Recorded structured payload');
    appendText(native, 'pre', JSON.stringify(native_record, null, 2));
    eventDetail.append(native);
  }
  eventDetail.scrollTo(...position);
}
function filterEvents() {
  const position = [eventList.scrollLeft, eventList.scrollTop];
  const query = eventSearch.value.toLowerCase();
  const visible = events.filter(e => eventFilters.every(([id, field]) => {
    const value = inspector.querySelector('#event-' + id).value;
    return !value || (e[field] ?? '(unavailable)') === value;
  }) && eventSearchText.get(e.event_id).includes(query));
  eventList.replaceChildren();
  for (const event of visible) {
    const time = event.timestamp ?? event.start ?? event.end;
    const button = appendText(eventList, 'button',
      (time == null ? 'Untimed' : new Date(time * 1000).toISOString()) + ' · ' +
      event.agent_name + ' · ' + event.kind + ' · ' + (event.name || event.message_role || event.outcome || ''));
    button.dataset.eventId = event.event_id;
    button.setAttribute('aria-pressed', String(event.event_id === selectedEvent));
    button.addEventListener('click', () => {
      selectedEvent = event.event_id;
      eventDetail.scrollTo(0, 0);
      filterEvents();
      showEvent();
    });
  }
  inspector.querySelector('#event-count').textContent = visible.length + ' of ' + events.length + ' events';
  eventList.scrollTo(...position);
}
function loadEvents(data) {
  events = data.events.map(e => ({...e, tool_name: e.kind === 'tool' ? e.name : e.tool_name}));
  eventSearchText = new Map(events.map(e => [e.event_id, searchableText(e).toLowerCase()]));
  for (const [id, field] of eventFilters) {
    const select = inspector.querySelector('#event-' + id), previous = select.value;
    const choices = [...new Set(events.map(e => e[field] ?? '(unavailable)'))].sort();
    if (previous && !choices.includes(previous)) choices.push(previous);
    select.replaceChildren(new Option('All', ''), ...choices.map(value => new Option(value, value)));
    select.value = previous;
  }
  inspector.querySelector('#event-omissions').textContent =
    (data.timing_omissions || []).filter(e => e.reason === 'timing_unavailable').length + ' events lack timestamps and are omitted from Perfetto.';
  filterEvents();
  showEvent();
}
eventFilters.forEach(([id]) => inspector.querySelector('#event-' + id).addEventListener('change', filterEvents));
eventSearch.addEventListener('input', filterEvents);
loadEvents(JSON.parse(document.querySelector('#event-data').textContent));

const interval = Number(document.querySelector('main').dataset.interval);
const pauseNotice = document.querySelector('#pause-notice');
let pollTimer, polling = false;
function updatesPaused() {
  return document.activeElement?.tagName === 'SELECT' || !window.getSelection().isCollapsed;
}
function showPauseNotice() {
  // Keep the notice available until a poll resumes, including during button focus.
  if (updatesPaused()) pauseNotice.hidden = false;
}
document.addEventListener('focusin', showPauseNotice);
document.addEventListener('selectionchange', showPauseNotice);
document.querySelector('#resume-updates').addEventListener('click', () => {
  window.getSelection().removeAllRanges();
  if (document.activeElement?.tagName === 'SELECT') document.activeElement.blur();
  poll();
});
async function poll() {
  if (polling) return;
  polling = true;
  clearTimeout(pollTimer);
  if (!updatesPaused()) pauseNotice.hidden = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(location.href, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    const status = page.querySelector('#refresh-status');
    const content = page.querySelector('#report-content');
    if (!status || !content) throw new Error('Invalid dashboard response');
    // Moving controls or rebuilding text cancels native popups and selections.
    // Check after fetching: the reader may have started interacting while waiting.
    if (updatesPaused()) {
      showPauseNotice();
      return;
    }
    pauseNotice.hidden = true;
    document.querySelector('#refresh-status').replaceWith(status);
    if (!status.dataset.error) {
      const current = document.querySelector('#report-content');
      const expanded = new Set([...current.querySelectorAll('details[open]')].map(node => node.id));
      const scrolls = [...current.querySelectorAll('.scroll')].map(node => [node.scrollLeft, node.scrollTop]);
      const position = [window.scrollX, window.scrollY];
      const focused = document.activeElement;
      // Retain the actual controls, including search text and event handlers.
      content.querySelector('.controls').replaceWith(current.querySelector('.controls'));
      const freshEvents = JSON.parse(content.querySelector('#event-data').textContent);
      content.querySelector('#inspector').replaceWith(inspector);
      content.querySelectorAll('details').forEach(node => { node.open = expanded.has(node.id); });
      current.replaceWith(content);
      update();
      loadEvents(freshEvents);
      if (focused === group || focused === search || inspector.contains(focused)) focused.focus({preventScroll: true});
      content.querySelectorAll('.scroll').forEach((node, index) => {
        if (scrolls[index]) node.scrollTo(...scrolls[index]);
      });
      window.scrollTo(...position);
    }
  } catch (error) {
    const refreshError = document.querySelector('#refresh-error');
    const collectionError = document.querySelector('#refresh-status').dataset.error;
    refreshError.textContent = [collectionError, 'Connection failed; retrying on the next cycle.'].filter(Boolean).join(' ');
  } finally {
    clearTimeout(timeout);
    polling = false;
    schedulePoll();
  }
}
function schedulePoll() {
  // Split long intervals to avoid the browser's 32-bit timer overflow.
  const started = performance.now();
  function wait() {
    const remaining = interval - (performance.now() - started) / 1000;
    if (remaining > 0) pollTimer = setTimeout(wait, Math.min(remaining * 1000, 2147483647));
    else poll();
  }
  wait();
}
schedulePoll();
'''
