# Official tooling references

Reviewed 2026-10-07. Runtime capability checks and the installed version remain authoritative.

- [Emulator command line](https://developer.android.com/studio/run/emulator-commandline): headless launch, persistent AVDs, port pairs, snapshot flags.
- [Hardware acceleration](https://developer.android.com/studio/run/emulator-acceleration): KVM, native architecture matching, current graphics modes and deprecated renderer names.
- [Android CLI SDK install](https://developer.android.com/tools/agents/android-cli/commands/sdk_install): current package installation interface.
- [Android CLI SDK list](https://developer.android.com/tools/agents/android-cli/commands/sdk_list): package discovery and slash/semicolon compatibility.
- [SDK manager compatibility interface](https://developer.android.com/tools/sdkmanager): legacy tooling and license review.
- [AVD manager compatibility interface](https://developer.android.com/tools/avdmanager): device discovery and persistent AVD creation.
- [Official downloads and checksums](https://developer.android.com/studio): command-line-tools ZIP build/hash.
- [Mesa environment variables](https://docs.mesa3d.org/envvars.html): stable DRI_PRIME device selection.

The default archive pin is the official Linux command-line-tools build 15859902. The matching SHA-256 is in the global config example. This is configurable; it is not a promise that the pin will remain the newest release.
