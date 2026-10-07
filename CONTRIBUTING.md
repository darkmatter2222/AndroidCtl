# Contributing

Keep runtime dependencies in the standard library. Preserve stopped userdata and static port assignments. Add regression tests for lifecycle, data loss, races and configuration bugs. Never run destructive host operations in ordinary CI.

Install `requirements-dev.txt`, run the README's checks, and describe any hardware validation separately. Do not report an emulator boot or GPU selection as tested when only mocks ran. Changes to unit ordering, stop behavior, admission locks and disk paths need focused review. Public fixtures must be synthetic and contain no personal keys, addresses or host names.
