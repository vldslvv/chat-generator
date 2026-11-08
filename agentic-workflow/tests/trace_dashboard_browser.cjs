// Real Chromium boundary check, invoked by test_trace_view.py when configured.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.argv[2]);
    assert.equal(await page.locator('#pause-notice').isVisible(), false);
    await page.locator('#group').selectOption('tool');
    await page.locator('#search').fill('exec_command');
    await page.locator('#native-lineage').evaluate(node => { node.open = true; });
    assert.equal(await page.locator('#group-tool tbody tr:visible').count(), 1);
    await page.locator('#event-kind').selectOption('message');
    await page.locator('#event-agent').selectOption('codex:supervisor');
    await page.locator('#event-task').selectOption('work');
    await page.locator('#event-search').fill('print("snow")');
    await page.waitForFunction(() => document.querySelectorAll('#event-list button').length === 60);
    await page.locator('#event-search').fill('Unicode 雪');
    await page.waitForFunction(() => document.querySelectorAll('#event-list button').length === 60);
    await page.locator('#event-list button').first().click();
    assert.match(await page.locator('#event-detail').textContent(), /Unicode 雪\nprint\("snow"\)\n<\/script><script>globalThis.injected=true<\/script>/);
    assert.equal(await page.evaluate(() => globalThis.injected), undefined);
    const selected = await page.locator('#event-list button[aria-pressed="true"]').getAttribute('data-event-id');
    await page.locator('#event-search').focus();
    await page.evaluate(() => {
      document.querySelector('#event-list').scrollTop = 130;
      document.querySelector('#event-detail').scrollTop = 150;
    });
    fs.appendFileSync(process.argv[3], JSON.stringify({timestamp: 1793959262, type: 'response_item',
      payload: {type: 'message', id: 'browser-refresh', turn_id: 'turn-2', role: 'assistant', content: 'Refresh arrived'}}) + '\n');
    await page.waitForFunction(() => JSON.parse(document.querySelector('#event-data').textContent).events.some(
      event => event.native_record?.id === 'browser-refresh'));
    assert.equal(await page.locator('#group').inputValue(), 'tool');
    assert.equal(await page.locator('#search').inputValue(), 'exec_command');
    assert.equal(await page.locator('#native-lineage').evaluate(node => node.open), true);
    assert.equal(await page.locator('#event-search').inputValue(), 'Unicode 雪');
    assert.equal(await page.locator('#event-kind').inputValue(), 'message');
    assert.equal(await page.locator('#event-agent').inputValue(), 'codex:supervisor');
    assert.equal(await page.locator('#event-task').inputValue(), 'work');
    assert.equal(await page.locator('#event-list button[aria-pressed="true"]').getAttribute('data-event-id'), selected);
    assert.deepEqual(await page.evaluate(() => [document.querySelector('#event-list').scrollTop,
      document.querySelector('#event-detail').scrollTop]), [130, 150]);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'event-search');
    await page.locator('#event-search').fill('Refresh arrived');
    assert.equal(await page.locator('#event-list button').count(), 1);
    await page.locator('#event-list button').click();
    assert.match(await page.locator('#event-detail').textContent(), /Refresh arrived/);
    await page.locator('#event-search').fill('');
    await page.locator('#event-kind').selectOption('tool');
    await page.locator('#event-tool').selectOption('exec_command');
    assert.equal(await page.locator('#event-list button').count(), 1);
    await page.locator('#event-list button').click();
    assert.match(await page.locator('#event-detail').textContent(), /PRIVATE_ARGUMENTS/);
    assert.match(await page.locator('#event-detail').textContent(), /PRIVATE_OUTPUT/);

    // A real poll must preserve highlighted text until the reader clears it.
    const highlight = await page.locator('#event-detail pre').first().evaluate(node => {
      const range = document.createRange();
      range.setStart(node.firstChild, 0);
      range.setEnd(node.firstChild, 20);
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
      return window.getSelection().toString();
    });
    assert.ok(highlight.length);
    fs.appendFileSync(process.argv[3], JSON.stringify({timestamp: 1793959263, type: 'response_item',
      payload: {type: 'message', id: 'browser-interaction', turn_id: 'turn-2', role: 'assistant', content: 'Interaction update'}}) + '\n');
    async function waitForUpdatedPoll(marker = 'Interaction update') {
      const response = await page.waitForResponse(async response =>
        response.url() === process.argv[2] && (await response.text()).includes(marker));
      await response.finished();
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    }
    await waitForUpdatedPoll();
    assert.equal(await page.evaluate(() => window.getSelection().toString()), highlight);
    assert.equal(await page.locator('#pause-notice').isVisible(), true);
    await page.getByRole('button', {name: 'Resume updates'}).focus();
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => JSON.parse(document.querySelector('#event-data').textContent).events.some(
      event => event.native_record?.id === 'browser-interaction'));
    assert.equal(await page.evaluate(() => window.getSelection().toString()), '');
    assert.equal(await page.locator('#pause-notice').isVisible(), false);

    // Keep a native dropdown open across a poll, then commit its pending choice.
    for (const id of ['group', 'event-kind']) {
      const select = page.locator('#' + id);
      const expected = await select.evaluate(node => node.options[node.options.length - 1].value);
      await select.selectOption({index: 0});
      await select.click();
      await page.keyboard.press('End');
      assert.equal(await select.evaluate(node => node.matches(':open')), true);
      const marker = 'Dropdown update ' + id;
      fs.appendFileSync(process.argv[3], JSON.stringify({timestamp: 1793959264, type: 'response_item',
        payload: {type: 'message', id: marker, turn_id: 'turn-2', role: 'assistant', content: marker}}) + '\n');
      await waitForUpdatedPoll(marker);
      assert.equal(await select.evaluate(node => node.matches(':open')), true, id + ' dropdown closed during polling');
      assert.equal(await page.locator('#pause-notice').isVisible(), true);
      await page.keyboard.press('Enter');
      assert.equal(await select.inputValue(), expected, id + ' dropdown lost its pending choice');
      await page.locator('#event-search').focus();
      await page.waitForFunction(marker => JSON.parse(document.querySelector('#event-data').textContent).events.some(
        event => event.native_record?.id === marker), marker);
      assert.equal(await page.locator('#pause-notice').isVisible(), false);
    }
    assert.deepEqual(errors, []);
    console.log('PASS: content search, filters, selection, refresh, scrolling, focus, highlighting, dropdowns and inert text');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
