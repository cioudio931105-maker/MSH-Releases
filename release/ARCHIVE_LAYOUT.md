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

No long-term storage location is selected here. Preserve local originals and
independent backups until another location is chosen, transfer is verified and
any removal separately approved. Published version paths should be immutable.
The build script writes future artifacts directly into `v<version>\` and refuses
to overwrite an existing installer.

Before moving an installer, verify that its `.sha256` file matches. Do not add
installers, models, datasets, or other generated artifacts to the source Git
history.

Finalization requires exactly one formal CPU/GPU installer, matching checksum,
build manifest and release notes. It rejects extra files/directories, candidate
or dirty builds, bundled-model/research-data manifests and existing finalized
metadata. It creates local `latest.json` and `release-record.json`; it does not
upload, unpack the installer or select storage for user research artifacts.
Keep runtime variants in separate bundles and retain the original payload audit,
clean-machine and hardware acceptance requirements.

See [storage and sync](../docs/RELEASE_STORAGE_AND_SYNC.md) for the provider-neutral
source, artifact and update layout.
