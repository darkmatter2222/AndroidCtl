---
name: androidctl-workbench
description: Start and operate the local AndroidCtl web device utility and its authenticated JSON API.
---
Read `docs/web-workbench.md`. Start `python -m androidctl.web --no-browser` from an installed package, or with `PYTHONPATH=src` in this checkout. Keep the process running; the command prints the local URL with a per-process token. Do not put this token or wireless pairing codes into committed files or logs.
Use the exact serial from `/api/devices`. Supply `X-AndroidCtl-Token` for API requests. Configure `--adb-port 5038` only when intentionally using AndroidCtl's managed host ADB server; desktops use 5037. Read-only inspection is safe alongside workers. Obtain ownership of the device before any input, disconnect, or native scrcpy interaction. Do not change emulator lifecycle as a side effect of opening the workbench. Never claim screenshot polling is video or that launch success proves the desktop viewer is healthy.
