import test from 'node:test';
import assert from 'node:assert/strict';
import { setupTui } from '../ui.mjs';

function harness(overrides = {}) {
  let layer; const toasts = [], dialogs = [];
  const forbidden = new Proxy({}, { get() { throw new Error('Direct command touched the model/session API'); } });
  const ctx = {
    keymap: { layer: factory => { layer = factory(); } },
    client: forbidden, data: forbidden,
    ui: { toast: { show: x => toasts.push(x) }, dialog: { alert: async x => dialogs.push(x) }, router: { current: () => ({ type: 'home' }) } },
    ...overrides,
  };
  return { ctx, toasts, dialogs, command: () => layer.commands[0] };
}

test('screen launch is a TUI command with zero session/model API access', async () => {
  const h = harness(); const calls = [];
  setupTui(h.ctx, { loadConfig: async () => ({}), execute: async text => { calls.push(text); return 'Viewer launched'; } });
  assert.deepEqual(h.command().slash, { name: 'androidctl', arguments: true });
  await h.command().run('A,B,C,D');
  assert.deepEqual(calls, ['A,B,C,D']);
  assert.equal(h.toasts.length, 1);
  assert.equal(h.dialogs.length, 0);
});

test('help, status, logs, errors and partial failures stay outside chat', async () => {
  for (const input of ['', 'help', 'status', 'logs A', 'A']) {
    const h = harness();
    setupTui(h.ctx, { loadConfig: async () => ({}), execute: async () => 'A: ERROR: offline' });
    await h.command().run(input);
    assert.equal(h.dialogs.length, 1);
  }
  const h = harness();
  setupTui(h.ctx, { loadConfig: async () => { throw new Error('broken config'); } });
  await h.command().run('A');
  assert.match(h.dialogs[0].message, /broken config/);
});

test('repeated key submission does not launch twice while a command is running', async () => {
  const h = harness(); let resolve, count = 0;
  setupTui(h.ctx, { loadConfig: async () => ({}), execute: () => { count++; return new Promise(r => { resolve = r; }); } });
  const first = h.command().run('A');
  await Promise.resolve();
  await h.command().run('A');
  assert.equal(count, 1);
  resolve('Viewer launched'); await first;
  assert.equal(h.toasts.length, 2);
});

test('only explicitly requested agent workflows submit a prompt', async () => {
  const prompts = [];
  const h = harness({ client: { session: { prompt: async p => prompts.push(p) } }, location: { directory: '/test' } });
  h.ctx.ui.router.current = () => ({ type: 'session', sessionID: 'session-1' });
  setupTui(h.ctx);
  await h.command().run('debug device B offline');
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0].sessionID, 'session-1');
  assert.match(prompts[0].text, /device B offline/);
});
