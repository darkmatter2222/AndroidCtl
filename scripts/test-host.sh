#!/usr/bin/env bash
# Explicit, opt-in persistence smoke test against an EXISTING disposable instance.
set -euo pipefail
if [[ $# != 2 || "$1" != "--instance" ]]; then
  echo 'Usage: sudo scripts/test-host.sh --instance ID (starts/stops and writes a test marker)' >&2
  exit 2
fi
INSTANCE_ID="$2"
androidctl start "$INSTANCE_ID"
androidctl adb "$INSTANCE_ID" shell 'echo androidctl-persistence-test > /data/local/tmp/androidctl-persistence-test'
androidctl restart "$INSTANCE_ID"
MARKER="$(androidctl adb "$INSTANCE_ID" shell cat /data/local/tmp/androidctl-persistence-test | tr -d '\r')"
[[ "$MARKER" == "androidctl-persistence-test" ]] || { echo 'Persistence check FAILED' >&2; exit 1; }
androidctl health "$INSTANCE_ID" --json
androidctl stop "$INSTANCE_ID"
echo 'Verify the printed marker and static ports; see docs/validation.md for full acceptance checks.'
