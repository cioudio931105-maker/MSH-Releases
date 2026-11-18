# Local installer archive layout

Packaged installers are generated artifacts and remain Git-ignored. Keep them
under `dist\release\v<version>\` so that every installer, checksum, and
version-specific delivery note stays together.

```text
dist\release\
  v0.1.0\
  v0.1.1\
    backup\
  v0.1.3\
```

The `backup\` folder is an intentional second copy retained before a newer
candidate is built. Do not overwrite or delete an earlier installer while the
newer candidate still awaits B-site testing. The build script writes future
artifacts directly into `v<version>\`.

Before moving an installer, verify that its `.sha256` file matches. Do not add
installers, models, datasets, or other generated artifacts to the source Git
history.
