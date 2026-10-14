// @ts-check
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execute, guidance, help, loadConfig } from './core.mjs';

// Deliberately independent of the session inbox. Results are transient terminal
// UI only; direct commands must work even when every client API is unavailable.
/**
 * @param {import("@opencode/plugin/tui").Plugin.Context} ctx
 * @param {{loadConfig?: typeof loadConfig, execute?: typeof execute}} dependencies
 */
export function setupTui(ctx, dependencies = {}) {
  const load = dependencies.loadConfig || loadConfig;
  const run = dependencies.execute || execute;
  let busy = false;
  ctx.keymap.layer(() => ({
    mode: 'global',
    commands: [{
      id: 'androidctl.command',
      title: 'AndroidCtl: view and manage devices',
      group: 'AndroidCtl',
      palette: true,
      slash: { name: 'androidctl', arguments: true },
      async run(input) {
        if (busy) {
          ctx.ui.toast.show({ title: 'AndroidCtl', message: 'A command is already running.', variant: 'info' });
          return;
        }
        busy = true;
        try {
          const text = (input || '').trim();
          const action = text.split(/\s+/)[0].toLowerCase();
          if (['deploy', 'debug', 'mcp'].includes(action)) {
            const route = ctx.ui.router.current();
            if (route.type !== 'session') throw new Error('Open a chat session before requesting an agent workflow.');
            // Only these explicitly agent-driven operations may invoke a model.
            await ctx.client.session.prompt({
              sessionID: route.sessionID,
              text: guidance(action, text.slice(action.length).trim(), dirname(fileURLToPath(import.meta.url))),
            });
            return;
          }
          const result = !text || action === 'help' ? help : await run(text, await load());
          const viewing = text && !['help', 'config', 'list', 'status', 'health', 'start', 'stop', 'restart', 'enable', 'disable', 'logs', 'doctor', 'ports', 'endpoints'].includes(action);
          if (viewing && !result.includes('ERROR:')) {
            ctx.ui.toast.show({ title: 'AndroidCtl', message: result, variant: 'success', duration: 5000 });
          } else {
            await ctx.ui.dialog.alert({ title: 'AndroidCtl', message: result });
          }
        } catch (error) {
          await ctx.ui.dialog.alert({ title: 'AndroidCtl error', message: error instanceof Error ? error.message : String(error) });
        } finally {
          busy = false;
        }
      },
    }],
  }));
}
