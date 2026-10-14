import { Plugin } from '@opencode/plugin/tui';
import { setupTui } from './ui.mjs';

export default Plugin.define({ id: 'androidctl.tui', setup: setupTui });
