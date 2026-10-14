import { cp, mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
const source = join(dirname(fileURLToPath(import.meta.url)), 'androidctl');
const args = process.argv.slice(2);
const options = {};
for (let i = 0; i < args.length; i += 2) {
  if (!['--host', '--ssh', '--config-dir'].includes(args[i]) || !args[i + 1] || args[i + 1].startsWith('--')) throw new Error('Usage: node opencode/install.mjs [--host HOST] [--ssh USER@HOST] [--config-dir PATH]');
  options[args[i]] = args[i + 1];
}
const root = resolve(options['--config-dir'] || join(process.env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'opencode'));
const destination = join(root, 'plugins', 'androidctl');
const config = join(root, 'androidctl.json');
const example = JSON.parse(await readFile(join(source, 'androidctl.example.json'), 'utf8'));
if (options['--host']) example.host = options['--host'];
if (options['--ssh']) example.management = { target: options['--ssh'] };
// Reject invalid supplied endpoints before writing anything; template placeholder is intentionally incomplete.
if (options['--host'] || options['--ssh']) {
  const { validate } = await import('./androidctl/core.mjs');
  validate({ ...example, host: options['--host'] || 'localhost' });
}
await mkdir(root, { recursive: true });
try { await access(destination); throw new Error(`Already installed at ${destination}. Back up/remove only that plugin directory before reinstalling. Your androidctl.json is preserved.`); }
catch (e) { if (e.code !== 'ENOENT') throw e; }
await cp(source, destination, { recursive: true, filter: path => !path.includes('node_modules') && !path.includes(`${join(source, 'test')}`) });
try { await writeFile(config, JSON.stringify(example, null, 2) + '\n', { flag: 'wx', mode: 0o600 }); }
catch (e) { if (e.code !== 'EEXIST') throw e; }
console.log(`Installed: ${destination}\nConfiguration (existing file preserved): ${config}\nRestart OpenCode 2.x, then /androidctl help. Configure the host before viewing.\nInstall adb and scrcpy on this desktop. Management additionally requires SSH access.`);
