#!/usr/bin/env bash
set -euo pipefail
exec androidctl doctor "$@"
