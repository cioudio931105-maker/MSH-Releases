# Local installer archive layout

Packaged installers are generated artifacts and remain Git-ignored. Keep the
current build under `dist\release\v<version>\` so that the installer, checksum,
manifest, release notes, and release record stay together until the immutable
version folder is uploaded and independently verified.

```text
dist\release\
  v0.1.0\
  v0.1.1\
    backup\
  v0.1.3\
```

Do not create continuing `backup\` copies on every desktop. The configured remote
binary store is the long-term archive; each version path is immutable. Retain a
local copy only while upload or independent download verification is incomplete.
The build script writes future artifacts directly into `v<version>\` and refuses
to overwrite an existing installer.

Before moving an installer, verify that its `.sha256` file matches. Do not add
installers, models, datasets, or other generated artifacts to the source Git
history.

See `docs/RELEASE_STORAGE_AND_SYNC.md` for the provider-neutral source, artifact,
and update layout.
