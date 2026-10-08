# Graphics selection

Software rendering is the default. It requires CPU time but no physical GPU device permissions. `host` and `auto` require a PCI selection via `--gpu-pci` or a stable `dri_prime` default; they never select an NVIDIA accelerator merely because one exists.

1. Run `androidctl gpu list --json` to view PCI identities, kernel drivers, render nodes and card nodes.
2. Choose a supported Mesa device (i915, xe, amdgpu, radeon or nouveau).
3. Create the device with `--gpu host --gpu-pci <PCI_ADDRESS>`.
4. Inspect emulator logs, EGL diagnostics and GPU activity on the host.

The Mesa selector transforms a PCI address's colon/dot separators into underscores and prefixes `pci-`. Use a value derived from your discovery output, not a copied machine-specific address. `androidctl config set dri_prime <SELECTOR>` applies to future instances. Proprietary NVIDIA offload/selection is intentionally rejected in this release; CUDA/NVIDIA services and driver configuration are not changed.

Hardware instances receive systemd allow rules for only the chosen card/render nodes. Mesa receives DRI_PRIME; other GPU nodes remain blocked. Software instances get no GPU nodes. If the host's driver cannot render with this policy on a headless server, the launch fails; choose a supported software renderer rather than expanding access to unrelated GPUs automatically.

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
