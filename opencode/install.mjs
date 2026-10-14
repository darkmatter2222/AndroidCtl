import { cp, mkdir, readFile, writeFile, access, rename } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

export const packageTarget = 'github:darkmatter2222/AndroidCtl#main::path:opencode/androidctl';
const oldTarget = 'github:darkmatter2222/AndroidCtl#feat/opencode-androidctl::path:opencode/androidctl';
const source = join(dirname(fileURLToPath(import.meta.url)), 'androidctl');
const defaultRoot = () => join(process.env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'opencode');

function runOpenCode(args) {
  // Only fixed package targets reach this function. On Windows npm's opencode.cmd
  // requires cmd.exe; no user-supplied text is interpolated into that shell.
  const result = spawnSync('opencode', args, { stdio: 'inherit', shell: process.platform === 'win32' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`opencode ${args.slice(0, 2).join(' ')} failed (${result.status}). Existing local plugin/configuration retained.`);
}

export async function install(options = {}, io = {}) {
  const root = resolve(options.configDir || defaultRoot());
  if (!options.local && options.configDir && !io.runOpenCode) throw new Error('--config-dir requires --local. Managed installs use OpenCode’s global configuration.');
  const destination = join(root, 'plugins', 'androidctl');
  const config = join(root, 'androidctl.json');
  const example = JSON.parse(await readFile(join(source, 'androidctl.example.json'), 'utf8'));
  if (options.host) example.host = options.host;
  if (options.ssh) example.management = { target: options.ssh };
  if (options.host || options.ssh) {
    const { validate } = await import('./androidctl/core.mjs');
    validate({ ...example, host: options.host || 'localhost' });
  }
  let exists = false;
  try { await access(destination); exists = true; } catch (e) { if (e.code !== 'ENOENT') throw e; }
  if (exists && options.local) throw new Error(`Already installed at ${destination}. Use the default managed installer to migrate, or back up/remove the local plugin before reinstalling.`);
  if (exists) {
    const prior = JSON.parse(await readFile(join(destination, 'package.json'), 'utf8'));
    if (prior.name !== 'opencode-androidctl') throw new Error(`Refusing to move an unrecognized plugin at ${destination}`);
  }
  await mkdir(root, { recursive: true });
  let backup;
  if (options.local) {
    await cp(source, destination, { recursive: true, filter: path => !path.includes('node_modules') && !path.startsWith(join(source, 'test')) });
  } else {
    const command = io.runOpenCode || runOpenCode;
    await command(['plugin', 'add', packageTarget]);
    // Remove the old development-branch subscription if present. Native command
    // preserves other JSONC settings and is a no-op when the target is absent.
    await command(['plugin', 'remove', oldTarget]);
    if (exists) {
      const backups = join(root, 'androidctl-backups');
      await mkdir(backups, { recursive: true });
      backup = join(backups, `plugin-${Date.now()}`);
      await rename(destination, backup);
    }
  }
  try { await writeFile(config, JSON.stringify(example, null, 2) + '\n', { flag: 'wx', mode: 0o600 }); }
  catch (e) { if (e.code !== 'EEXIST') throw e; }
  return { config, backup, destination: options.local ? destination : packageTarget, managed: !options.local };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2), options = {};
    for (let i = 0; i < args.length; i++) {
      if (args[i] === '--local') { options.local = true; continue; }
      const key = { '--host': 'host', '--ssh': 'ssh', '--config-dir': 'configDir' }[args[i]];
      if (!key || !args[i + 1] || args[i + 1].startsWith('--')) throw new Error('Usage: node opencode/install.mjs [--host HOST] [--ssh USER@HOST] [--local [--config-dir PATH]]');
      options[key] = args[++i];
    }
    const result = await install(options);
    console.log(`Installed: ${result.destination}\nConfiguration (existing file preserved): ${result.config}${result.backup ? `\nOld local plugin backed up: ${result.backup}` : ''}\nRestart OpenCode 2.x, then /androidctl help.\n${result.managed ? 'Future updates: /plugins → check for updates → update (or opencode plugin update).' : 'Local development copy: native update checks skip this install.'}`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
