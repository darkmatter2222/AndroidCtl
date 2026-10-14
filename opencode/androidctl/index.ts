import { Plugin } from '@opencode/plugin';

// Keep the server identity for existing installations. All direct commands live
// in ./tui: never register a chat command or write to a session on the server.
export default Plugin.define({ id: 'androidctl', setup() {} });
