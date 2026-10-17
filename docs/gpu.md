# Graphics selection

Software rendering is the default. It requires CPU time but no physical GPU device permissions. `host` and `auto` require a PCI selection via `--gpu-pci` or a stable `dri_prime` default; they never select an NVIDIA accelerator merely because one exists.

1. Run `androidctl gpu list --json` to view PCI identities, kernel drivers, render nodes and card nodes.
2. Choose a supported Mesa device (i915, xe, amdgpu, radeon or nouveau), or the sole proprietary NVIDIA GPU on a single-NVIDIA host.
3. Create the device with `--gpu host --gpu-pci <PCI_ADDRESS>`.
4. Inspect emulator logs, EGL diagnostics and GPU activity on the host.

The Mesa selector transforms a PCI address's colon/dot separators into underscores and prefixes `pci-`. Use a value derived from your discovery output, not a copied machine-specific address. `androidctl config set dri_prime <SELECTOR>` applies to future instances. An experimental proprietary NVIDIA path is available for single-NVIDIA hosts. It discovers the selected GPU minor from /proc/driver/nvidia, permits that GPU plus required shared NVIDIA control nodes, and selects NVIDIA GLX/EGL where available. Multi-NVIDIA hosts are rejected because reliable per-PCI EGL selection has not been validated. CUDA/NVIDIA services and driver configuration are not changed.

Hardware instances receive systemd allow rules for chosen card/render nodes (and NVIDIA device/control nodes when selected). Mesa receives DRI_PRIME; other GPU nodes remain blocked. Software instances get no GPU nodes. If the host's driver cannot render with this policy on a headless server, the launch fails; choose a supported software renderer rather than expanding access to unrelated GPUs automatically.

Current emulator documentation lists auto, host, software, lavapipe, swiftshader, and swangle. `swiftshader_indirect` is retained for older versions but is deprecated in newer releases. AndroidCtl passes the configured mode unchanged, so the installed emulator's capability is authoritative. Use its `-help-gpu` and journal output for version-specific availability. No automatic renderer fallback is implemented by the manager.

Doctor runs EGL/GLX diagnostics in the service identity when invoked through sudo. A GLX failure without an X server can be normal; the emulator's actual boot is the decisive test. This diagnostic does not prove any particular per-instance GPU selection works.

## Reported workaround for software RenderThread crashes

On 2026-10-08, an API 35 instance using emulator 37.2.12.0 repeatedly
segfaulted with automatic software rendering and explicit swiftshader,
including with guest Vulkan disabled. Explicit `gpu_mode = swangle` plus
`Vulkan = off` in the service account's advancedFeatures.ini produced a
verified ANGLE adapter and the user reported that it appeared to work.
Long-duration stability remains unverified; project-wide defaults have not
changed. This is CPU software rendering, not NVIDIA hardware acceleration.

See [the current workaround and complete application/rollback procedure](troubleshooting.md#current-workaround-explicit-swangle-with-guest-vulkan-disabled).
Changing the global default alone does not update existing instance configs.
Guest Vulkan exposure and ANGLE's internal Vulkan backend are separate.


## RTX 3090 performance trial (existing instances)

The four-device fleet defaults to CPU-based SwANGLE for the previously observed software renderer crashes. Lots of GPU VRAM alone will not accelerate it. KVM is already explicitly required with `-accel on`; diagnose CPU pressure, memory/swap, renderer and capture overhead before increasing vCPU counts.

Update the host installation using the normal stopped-fleet upgrade procedure before using the new commands. Start with one instance, keeping others stopped:

```sh
androidctl performance --json
sudo androidctl stop 01
sudo androidctl renderer 01 --gpu host
sudo androidctl start 01
androidctl status 01 --json
nvidia-smi
sudo androidctl logs 01 --since 5m
```

`renderer` defaults to automatic selection only when there is exactly one NVIDIA GPU (or one eligible Mesa GPU if no NVIDIA exists). `--gpu-pci PCI` chooses a specific supported PCI identity. The original instance config is saved once as `01.conf.before-renderer`; userdata is preserved and existing guest-Vulkan policy is unchanged. Hardware rendering depends on installed NVIDIA OpenGL/EGL userspace drivers and their compatibility with the emulator in headless mode. No drivers are installed by this command. Confirm the emulator's renderer in its journal and GPU process/utilization during actual interaction; merely saving `gpu_mode=host` or seeing a healthy boot is not performance proof. An unavailable headless GL/EGL context may still require host graphics setup.

Rollback without wiping data:

```sh
sudo androidctl stop 01
sudo androidctl renderer 01 --gpu swangle
sudo androidctl start 01
```

The read-only performance report includes load, CPU pressure, memory, emulator configuration, KVM acceleration check, GPU inventory, NVIDIA utilization/VRAM/processes and highest-CPU processes. Inspect these before stopping any GPU model workload. Stop only the identified model service/container using its normal supervisor; do not blanket-kill GPU processes. This release does not unload models automatically. Compare the same app action with one instance, native scrcpy, no browser previews, then with browser previews enabled and at 50% logical resolution. That separates guest/rendering latency from screenshot latency. No live RTX 3090 performance gain has been measured in the development environment.

Sources: [official Android acceleration guide](https://developer.android.com/studio/run/emulator-acceleration), [NVIDIA PRIME render offload](https://download.nvidia.com/XFree86/Linux-x86_64/550.54.14/README/primerenderoffload.html).


## Confirmed headless GLX failure on the RTX 3090

The host log on 2026-10-17 shows `GlxEnginegetDefaultDisplay: Failed to open display 0. DISPLAY: [(null)]`, followed by framebuffer initialization failure. GPU device access alone is insufficient for this emulator's `host` GLX path. The later timeout and forced termination are consequences of renderer failure, not evidence of insufficient GPU memory.

After updating the checkout and installed manager, select host rendering for a stopped instance, then run:

```sh
sudo bash scripts/setup-nvidia-display.sh 01
```

This installs Xorg/xauth/glxinfo if absent (no NVIDIA driver replacement), creates a dedicated NVIDIA-backed headless X display `:99`, authenticates it with a service-group-readable cookie, disables TCP listening, and verifies that `glxinfo -B` under the Android service identity reports NVIDIA before starting Android. It uses the selected GPU's PCI identity and requires its existing NVIDIA Xorg module. It refuses an occupied `:99`; it does not stop your desktop X server. The per-instance drop-in supplies DISPLAY/XAUTHORITY and disables PrivateTmp for that instance so the X socket is visible. Other unit restrictions remain. The Xorg unit starts as a dependency; no global desktop config is overwritten. This setup has syntax/unit-level validation only, not live hardware validation.

The launcher no longer forces PRIME render offload; the dedicated X screen already belongs to NVIDIA. Confirm the actual emulator renderer in its journal and measure app responsiveness after boot.

To remove the integration from instance 01, stop it, remove only `/etc/systemd/system/android-emulator@01.service.d/nvidia-display.conf`, run `sudo systemctl daemon-reload`, then select `--gpu swangle` and start it. Stop `androidctl-nvidia-xorg.service` only after no other instances use its display. Keep its configuration/cookie for repeat setup, or remove them after stopping the display if no longer needed.
