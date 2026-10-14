import { execute, help, loadConfig } from './core.mjs';
try {
  const text = process.argv.slice(2).join(' ');
  const result = !text || text === 'help' ? help : await execute(text, await loadConfig());
  console.log(result);
  if (result.includes('ERROR:')) process.exitCode = 1;
} catch (error) { console.error(error.message); process.exitCode = 1; }
