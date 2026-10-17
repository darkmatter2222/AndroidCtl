# Stable endpoints and emulator ports

The following fixed-port rules apply to legacy instances and CLI creation without
--runtime-ports. New web catalog reservations use the runtime mode described below.

`console = console_base_port + 2 × (ID − 1)`; `local_adb = console + 1`; `remote_adb = remote_adb_base_port + ID`. Defaults: 5554 and 15550. Values are stored in each instance config and do not change when global bases are edited.

The documented numeric console range is 5554–5682 inclusive, with even console ports. This is 65 numeric pairs (the Google page also describes 64 simultaneous devices; the manager does not treat that prose count as a capacity promise). The last following ADB port is 5683. Default IDs above 65 exhaust the numeric range. Higher logical IDs can use explicit unused supported console/proxy ports; all reserved ports remain unique even among stopped instances. Actual concurrency is constrained by RAM/CPU and policy, not the theoretical port count.

```bash
sudo androidctl create 99 --console-port 5562 --remote-adb-port 16099 --install-image
```

Creation/start checks wildcard IPv4 binds to catch listeners on local interfaces and checks all registered ports across roles. IPv6 wildcard listeners that also claim IPv4 are caught by the IPv4 bind; IPv6-only listeners do not conflict with these IPv4 services. A port conflict names the port and an `ss` command to identify its owner. No listener is killed and no substitute port is chosen.

The emulator console/local ADB are intended to stay loopback-only; validate actual listeners with `sudo ss -ltnp` after the first real boot. The exposed proxy endpoint binds only the chosen loopback/private IPv4 interface. The managed ADB server uses its own loopback port 5038 and cannot overlap device ports.

## Catalog reservations with runtime ports

New web catalog entries use --runtime-ports. These retain a unique saved public
ADB proxy port but allocate an internal console/ADB pair only at service preflight.
Allocation is protected by the manager lock and saved in the runtime reservation
under /run/androidctl. Launch, proxy, health, and shutdown resolve that assignment.
The runtime reservation disappears on stop; identity, config, AVD data, and public
endpoint persist. This allows 200 or more saved reservations with a small active
subset without enlarging the supported console range.

Legacy fixed-port instances are unchanged and their pairs remain excluded from the
runtime pool. Runtime allocation excludes configured public endpoints, legacy pairs,
other admitted instances and live listeners. Admission limits and memory reserve
continue to apply. New CLI example: sudo androidctl create 200 --runtime-ports.
The default public endpoint for ID 200 is 15750; custom remote bases and overrides
must still fit the validated TCP range.
