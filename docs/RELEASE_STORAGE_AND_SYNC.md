# MSH source, release, and update storage

MSH does not need a database to keep application versions consistent. Use three
separate layers, each with one responsibility:

1. A private Git repository is the editable source of truth. Every machine works
   from a clone, branch, commit, and reviewed tag rather than copied source folders.
2. One object-storage bucket is the binary source of truth. Each immutable version
   lives at `v<version>/`; `latest.json` is the only moving pointer.
3. Each installed MSH client reads the public HTTPS `latest.json`, compares Semantic
   Versions, and asks the user before opening the installer download.

No source code, Git credentials, model-development data, or signing key belongs in
the public bucket. Public downloads contain only an approved installer and its
release evidence.

## Recommended hosted layout

Use a Cloudflare R2 public bucket behind a custom domain, for example
`https://downloads.example.org/msh`. R2 is S3-compatible, so it can later be
uploaded from GitHub Actions, `rclone`, or another S3 client without changing the
MSH update protocol.

```text
msh/
  latest.json
  v0.1.4/
    MSH_Setup_v0.1.4_CPU.exe
    MSH_Setup_v0.1.4_CPU.exe.sha256
    MSH_Setup_v0.1.4_CPU.exe.build-manifest.json
    RELEASE_NOTES_v0.1.4.md
    release-record.json
    latest.json
```

The version directory is immutable. Upload it once and never replace its files.
After verifying the public URLs and hashes, copy that version's `latest.json` to
the bucket root as the final publication step. Rolling back means repointing the
root manifest to a previously verified version; it does not mean rebuilding or
renaming an old installer.

The local `dist/release/v<version>/` directory is a build workspace, not the
long-term archive. Once the verified bundle is uploaded and independently
download-tested, it can be regenerated locally from the private Git tag and the
approved private model archive. Do not maintain a growing set of desktop copies.

## Standard release flow

1. On any trusted development machine, clone or fast-forward the private source
   repository and create a release branch.
2. Restore the separately protected approved model by its recorded SHA-256.
3. Run tests and save their machine-readable result in the release record/work log.
4. Commit reviewed source, create the annotated `v<version>` tag, and build from a
   clean worktree with `scripts/build_release.ps1`.
5. The build copies the matching release notes into the generated version
   directory. If `-PublicBaseUrl` was not supplied to the build, run:

   ```powershell
   .\scripts\finalize_release_bundle.ps1 `
     -BundleDirectory .\dist\release\v0.1.4 `
     -PublicBaseUrl https://downloads.example.org/msh
   ```

6. Upload that one version directory. Verify a fresh download against its SHA-256.
7. Publish the generated `latest.json` at the bucket root only after validation.

Upload credentials must be stored in the machine or CI secret store, never in Git,
the build manifest, a batch file, or the installed application.

## Portability checklist

To work from another city or country, the new machine needs only:

- access to the private Git repository, including reviewed branches and tags;
- the approved private model artifact or permission to retrieve it from private
  object storage, verified by SHA-256;
- the documented Python/build toolchain or a controlled Windows CI builder;
- publication credentials held by the operator or CI secret store.

Camera profiles, COM choices, motor parameters, calibration data, captured images,
datasets, and user output remain device/local-data concerns. They must not be
silently replaced by an application update.
