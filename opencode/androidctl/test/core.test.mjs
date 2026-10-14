import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { endpoint, validate, select, execute, remoteArgs, loadConfig } from '../core.mjs';
const config = () => validate({ host: 'host.example', devices: { A: { id: '01', port: 15551 }, B: { id: '02', endpoint: 'other:16662' } }, management: { target: 'user@host' } });
test('aliases, multiple hosts, deduplication and explicit endpoints', () => {
  const c = config();
  assert.deepEqual(select(c, 'a,B,A').map(x => x.endpoint), ['host.example:15551', 'other:16662']);
  assert.equal(select(c, '[::1]:5555', true)[0].endpoint, '[::1]:5555');
  assert.equal(select(c, 'all').length, 2);
});
test('reject invalid selections and injection before side effects', async () => {
  for (const value of ['x:0', 'x:65536', '-o:22', 'x;touch:22', 'x:22\nfoo']) assert.throws(() => endpoint(value));
  let calls = 0;
  await assert.rejects(execute('A,bogus', config(), { run: async () => { calls++; } }));
  assert.equal(calls, 0);
  assert.throws(() => validate({ ...config(), management: { target: '-oProxyCommand=bad' } }));
});
test('view disconnects/connects/checks each exact serial and continues after failure', async () => {
  const calls = [], views = [];
  const result = await execute('A,B', config(), {
    run: async (file, args) => { calls.push(args); if (args.includes('host.example:15551') && args.includes('get-state')) return 'offline'; return args.includes('get-state') ? 'device' : 'ok'; },
    launch: async (c, d) => { views.push(d.alias); return 'launched'; },
  });
  assert.match(result, /A: ERROR/);
  assert.deepEqual(views, ['B']);
  assert.deepEqual(calls[0], ['disconnect', 'host.example:15551']);
  assert.deepEqual(calls[1], ['connect', 'host.example:15551']);
  assert.equal(calls.length, 6);
});
test('ADB connect exit zero but failed connection never opens a viewer', async () => {
  const result = await execute('A', config(), { run: async (_, args) => args.includes('get-state') ? 'offline' : 'failed to connect', launch: () => { throw new Error('must not launch'); } });
  assert.match(result, /ADB is not ready/);
});
test('management requires explicit targets for mutations and quotes SSH command', async () => {
  await assert.rejects(execute('stop', config()), /requires explicit/);
  const calls = [];
  await execute('stop B', config(), { run: async (...args) => { calls.push(args); return 'ok'; } });
  assert.equal(calls[0][1].at(-1), "'sudo' '-n' 'androidctl' 'stop' '02'");
  assert.ok(calls[0][1].includes('BatchMode=yes'));
  assert.throws(() => remoteArgs({ ...config(), management: undefined }, ['list']), /management.target/);
});
test('logs are bounded by time, health and endpoints use saved IDs', async () => {
  const commands = [];
  const io = { run: async (_, args) => { commands.push(args.at(-1)); return 'ok'; } };
  await execute('logs B', config(), io);
  await execute('health A', config(), io);
  await execute('endpoints B', config(), io);
  assert.deepEqual(commands, ["'androidctl' 'logs' '02' '--since' '10m'", "'androidctl' 'health' '01' '--json'", "'androidctl' 'adb-endpoint' '02'"]);
});
test('installer uses isolated destination, preserves configuration and refuses overwrite', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'androidctl-test-'));
  try {
    const installer = resolve(import.meta.dirname, '../../install.mjs');
    const saved = join(dir, 'androidctl.json');
    await writeFile(saved, JSON.stringify(config()));
    execFileSync(process.execPath, [installer, '--config-dir', dir, '--host', 'newhost']);
    assert.equal((await loadConfig(saved)).host, 'host.example');
    assert.match(await readFile(join(dir, 'plugins/androidctl/index.ts'), 'utf8'), /Plugin.define/);
    assert.throws(() => execFileSync(process.execPath, [installer, '--config-dir', dir], { stdio: 'pipe' }));
  } finally { await rm(dir, { recursive: true, force: true }); }
});
