import { Plugin } from '@opencode/plugin';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execute, guidance, help, loadConfig } from './core.mjs';

export default Plugin.define({
  id: 'androidctl',
  async setup(ctx) {
    await ctx.command.transform(editor => {
      editor.add({
        name: 'androidctl',
        description: 'View Android screens; manage, diagnose and deploy AndroidCtl hosts',
        async execute({ sessionID, prompt, delivery }) {
          const text = (prompt.text || '').trim();
          const [action] = text.split(/\s+/);
          if (['deploy', 'debug', 'mcp'].includes(action)) {
            await ctx.session.prompt({ ...prompt, sessionID, delivery, text: guidance(action, text.slice(action.length).trim(), dirname(fileURLToPath(import.meta.url))) });
            return;
          }
          let result;
          try { result = !text || text === 'help' ? help : await execute(text, await loadConfig()); }
          catch (error) { result = `AndroidCtl: ${error instanceof Error ? error.message : String(error)}`; }
          // Direct commands report results without initiating a model turn.
          await ctx.session.synthetic({ sessionID, text: result });
        },
      });
    });
  },
});
