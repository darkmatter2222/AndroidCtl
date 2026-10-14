import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, access, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { install, packageTarget } from '../../install.mjs';

test('managed migration remembers main, preserves config and removes local discovery duplicate', async () => {
  const root = await mkdtemp(join(tmpdir(), 'androidctl-migrate-'));
  try {
    const prior = join(root, 'plugins/androidctl');
    await mkdir(prior, { recursive: true });
    await writeFile(join(prior, 'package.json'), JSON.stringify({ name: 'opencode-androidctl', version: '0.1.0' }));
    await writeFile(join(root, 'androidctl.json'), '{"host":"keep-me"}');
    const calls = [];
    const result = await install({ configDir: root }, { runOpenCode: async args => calls.push(args) });
    assert.deepEqual(calls[0], ['plugin', 'add', packageTarget]);
    assert.match(packageTarget, /#main::path:/);
    assert.deepEqual(calls[1].slice(0, 2), ['plugin', 'remove']);
    await assert.rejects(access(prior));
    await access(join(result.backup, 'package.json'));
    assert.equal(await readFile(join(root, 'androidctl.json'), 'utf8'), '{"host":"keep-me"}');
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('failed managed install leaves old plugin available', async () => {
  const root = await mkdtemp(join(tmpdir(), 'androidctl-migrate-'));
  try {
    const prior = join(root, 'plugins/androidctl');
    await mkdir(prior, { recursive: true });
    await writeFile(join(prior, 'package.json'), JSON.stringify({ name: 'opencode-androidctl' }));
    await assert.rejects(install({ configDir: root }, { runOpenCode: async () => { throw new Error('offline'); } }), /offline/);
    await access(prior);
  } finally { await rm(root, { recursive: true, force: true }); }
});
