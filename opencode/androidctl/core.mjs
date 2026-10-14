import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile, mkdir, open } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';

const exec = promisify(execFile);
export const configPath = () => process.env.ANDROIDCTL_CONFIG || join(process.env.XDG_CONFIG_HOME || join(homedir(), '.config'), 'opencode', 'androidctl.json');
export const help = `AndroidCtl (OpenCode 2.x)
/androidctl A | A,B,C,D | all | host:port
/androidctl view A,B (same as the shorthand)
/androidctl list | status [A,B|all] | health [A,B|all]
/androidctl start A | stop B,C | restart D | enable all | disable all
/androidctl logs A | doctor | ports | endpoints [all] | config
/androidctl deploy [requirements] | debug [symptoms] | mcp [requirements]
View reconnects only selected ADB endpoints. Lifecycle actions require configured SSH.
Config: ${configPath()}`;

export function endpoint(value) {
  if (typeof value !== 'string' || !/^(?:[a-zA-Z0-9][a-zA-Z0-9.-]*|\[[0-9a-fA-F:]+\]):\d{1,5}$/.test(value)) throw new Error(`Invalid ADB endpoint: ${value}; expected host:port`);
  const port = Number(value.slice(value.lastIndexOf(':') + 1));
  if (port < 1 || port > 65535) throw new Error('ADB port must be 1–65535');
  return value;
}

export function validate(raw) {
  const c = { adb: 'adb', scrcpy: 'scrcpy', ssh: 'ssh', maxFps: 30, ...raw };
  if (!c.devices || typeof c.devices !== 'object' || Array.isArray(c.devices) || !Object.keys(c.devices).length) throw new Error('Configure at least one device alias');
  for (const [alias, d] of Object.entries(c.devices)) {
    if (!/^[A-Z][A-Z0-9_-]*$/.test(alias)) throw new Error('Device aliases must be uppercase letters/digits/_/-');
    if (!d || typeof d !== 'object' || !/^\d{2}$/.test(d.id) || Number(d.id) < 1) throw new Error(`Invalid instance id for ${alias}`);
    if (d.endpoint) endpoint(d.endpoint);
    else if (!c.host || !Number.isInteger(d.port)) throw new Error(`Set endpoint or host + port for ${alias}`);
    else endpoint(`${c.host}:${d.port}`);
  }
  if (!Number.isInteger(c.maxFps) || c.maxFps < 1 || c.maxFps > 240) throw new Error('maxFps must be 1–240');
  for (const key of ['adb', 'scrcpy', 'ssh']) if (typeof c[key] !== 'string' || !c[key] || c[key].startsWith('-')) throw new Error(`Invalid ${key} executable`);
  if (c.management) {
    const m = c.management;
    if (!/^(?:[a-zA-Z0-9_][a-zA-Z0-9_.-]*@)?[a-zA-Z0-9][a-zA-Z0-9.-]*$/.test(m.target || '')) throw new Error('management.target must be an SSH host or user@host');
    if (m.port !== undefined && (!Number.isInteger(m.port) || m.port < 1 || m.port > 65535)) throw new Error('Invalid SSH port');
    if (m.identityFile !== undefined && typeof m.identityFile !== 'string') throw new Error('identityFile must be a path');
  }
  return c;
}

export async function loadConfig(path = configPath()) {
  try { return validate(JSON.parse(await readFile(path, 'utf8'))); }
  catch (error) { throw new Error(`Cannot load ${path}: ${error.message}. Copy androidctl.example.json and configure your host.`); }
}

export function select(c, text = 'all', allowEndpoint = false) {
  const tokens = text.trim().toLowerCase() === 'all' ? Object.keys(c.devices) : text.split(',').map(x => x.trim()).filter(Boolean);
  if (!tokens.length) throw new Error('Select one or more aliases, e.g. A,B');
  const devices = tokens.map(token => {
    const alias = token.toUpperCase(), d = c.devices[alias];
    if (d) return { alias, id: d.id, endpoint: d.endpoint || `${c.host}:${d.port}` };
    if (allowEndpoint) return { alias: endpoint(token), endpoint: token };
    throw new Error(`Unknown alias: ${token}`);
  });
  return [...new Map(devices.map(d => [d.endpoint, d])).values()];
}

export async function run(file, args) {
  try {
    const r = await exec(file, args, { timeout: 45000, maxBuffer: 2 * 1024 * 1024, windowsHide: true, env: { ...process.env, SYSTEMD_PAGER: 'cat' } });
    return (r.stdout + r.stderr).trim();
  } catch (e) { throw new Error(`${file}: ${e.stderr || e.stdout || e.message}`); }
}

// SSH joins its remote arguments into a shell command. Quote each token separately.
export const quote = value => "'" + String(value).replaceAll("'", "'\\''") + "'";
export function remoteArgs(c, args, elevated = false) {
  if (!c.management) throw new Error('Set management.target in androidctl.json for host operations');
  const m = c.management;
  const flags = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10'];
  if (m.port) flags.push('-p', String(m.port));
  if (m.identityFile) flags.push('-i', m.identityFile);
  const command = [...(elevated ? ['sudo', '-n'] : []), 'androidctl', ...args];
  return [...flags, m.target, command.map(quote).join(' ')];
}

export async function launch(c, d) {
  const directory = join(process.env.XDG_STATE_HOME || join(homedir(), '.local', 'state'), 'androidctl', 'viewer');
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${Date.now()}-${d.alias.replace(/[^a-zA-Z0-9_-]/g, '_')}.log`);
  const log = await open(path, 'a', 0o600);
  try {
    const child = spawn(c.scrcpy, ['-s', d.endpoint, '--no-audio', '--video-codec=h264', `--max-fps=${c.maxFps}`, '--print-fps', `--window-title=AndroidCtl ${d.alias} (${d.endpoint})`], { detached: true, stdio: ['ignore', log.fd, log.fd], windowsHide: true });
    // Catch missing executables and immediate encoder/display/connection failures.
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { child.removeListener('exit', exited); resolve(); }, 800);
      const exited = (code) => { clearTimeout(timer); reject(new Error(`scrcpy exited (${code}); inspect ${path}`)); };
      child.once('exit', exited);
      child.once('error', error => { clearTimeout(timer); reject(error); });
    });
    child.unref();
    return `Viewer launched: ${d.alias}, PID ${child.pid}. Log: ${path}. Close its window to stop viewing.`;
  } finally { await log.close(); }
}

export async function execute(text, c, io = {}) {
  const invoke = io.run || run, viewer = io.launch || launch;
  const words = text.trim().split(/\s+/), first = words.shift() || 'help';
  if (['help', '--help'].includes(first)) return help;
  if (first === 'config') return `Configuration: ${configPath()}\n${JSON.stringify(c, null, 2)}`;
  const actions = new Set(['view', 'list', 'status', 'health', 'start', 'stop', 'restart', 'enable', 'disable', 'logs', 'doctor', 'ports', 'endpoints']);
  const action = actions.has(first.toLowerCase()) ? first.toLowerCase() : 'view';
  const target = action === 'view' && first.toLowerCase() !== 'view' ? [first, ...words].join('') : words.join('');
  if (['list', 'doctor', 'ports'].includes(action)) {
    if (target) throw new Error(`${action} takes no aliases`);
    return invoke(c.ssh, remoteArgs(c, [action, '--json'], action === 'doctor'));
  }
  if (['start', 'stop', 'restart', 'enable', 'disable', 'logs', 'view'].includes(action) && !target) throw new Error(`${action} requires explicit aliases or all`);
  const selected = select(c, target || 'all', action === 'view'); // Validate entire selection before any side effect.
  const results = [];
  for (const d of selected) {
    try {
      if (action === 'view') {
        await invoke(c.adb, ['disconnect', d.endpoint]);
        await invoke(c.adb, ['connect', d.endpoint]);
        const state = await invoke(c.adb, ['-s', d.endpoint, 'get-state']);
        if (state.trim() !== 'device') throw new Error(`ADB is not ready: ${state}`);
        results.push(await viewer(c, d));
      } else {
        const mutate = ['start', 'stop', 'restart', 'enable', 'disable'].includes(action);
        const args = action === 'endpoints' ? ['adb-endpoint', d.id] : action === 'logs' ? ['logs', d.id, '--since', '10m'] : [action, d.id, ...(['status', 'health'].includes(action) ? ['--json'] : [])];
        results.push(`${d.alias}: ${await invoke(c.ssh, remoteArgs(c, args, mutate))}`);
      }
    } catch (e) { results.push(`${d.alias}: ERROR: ${e.message}`); }
  }
  if (['start', 'stop', 'restart'].includes(action)) results.push('Lifecycle request returned; run /androidctl status to verify completion.');
  return results.join('\n');
}

export function guidance(action, request, pluginDir) {
  const common = `Read ${resolve(pluginDir, 'OPERATIONS.md')} before acting. You are helping operate AndroidCtl. Preserve userdata and unrelated services. Use the user's existing authorization; ask only for missing decisions or destructive actions. Do not bypass OpenCode permissions. User request: ${request}`;
  return `${common}\nWorkflow: ${action}. For deploy, inspect the target and install/configure/verify using the repository's actual scripts. For debug, collect evidence before proposing repairs. For mcp, follow the separate android_automation repository's current instructions; do not invent MCP launch commands. Report completed work and any remaining blockers accurately.`;
}
