# Remote ADB

The default proxy endpoint is local-only. For trusted LAN access, stop managed devices, set `bind_address` to a specific RFC1918 interface address or `auto`, then start them. `auto` asks the kernel which local source address it would use for a route; it sends no probe traffic. The selected address is printed and retained for that service run. It must exist on the host and be private. Wildcard/public values are rejected.

The proxy maps `<BIND_ADDRESS>:15551` to `127.0.0.1:5555` for instance 01. ADB over this TCP proxy is powerful, not an authenticated web API. Image-specific ADB authentication behavior must not be treated as the manager's access-control layer. Restrict clients using your existing firewall/VPN, or keep loopback binding and use SSH.

With loopback defaults, from a client that has SSH access:

```bash
ssh -N -L 15551:127.0.0.1:15551 <ADMIN>@<ANDROID_HOST>
```

In another client terminal:

```cmd
adb connect 127.0.0.1:15551
scrcpy -s 127.0.0.1:15551
```

For a LAN-enabled host:

```cmd
adb connect <ANDROID_HOST>:15551
scrcpy -s <ANDROID_HOST>:15551 --no-audio
```

Do not forward ADB, the emulator console, or the managed ADB-server port through an internet router. AndroidCtl does not change firewall/NAT/routing configuration. Console ports must remain loopback-only. Local users can reach the dedicated ADB server and therefore must be trusted administrators of these guests.
