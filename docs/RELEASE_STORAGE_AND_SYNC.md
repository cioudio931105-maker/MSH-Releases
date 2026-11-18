# MSH source, release, and update storage

MSH does not need a database to keep application versions consistent. Use three
separate layers, each with one responsibility:

1. The Git repository is the editable source of truth. Every machine works
   from a clone, branch, commit, and reviewed tag rather than copied source folders.
2. An approved HTTPS download location serves application installers. Each
   immutable version lives at `v<version>/`; `latest.json` is the moving pointer.
3. Each installed MSH client reads the public HTTPS `latest.json`, compares Semantic
   Versions, and asks the user before opening the installer download.

User models, datasets, captures, labels, experiment results and historical backups
are a separate storage concern. They are excluded from source handoffs and
application bundles. No storage account/provider is selected by this document;
choosing where research artifacts live is independent of the application URL.
Existing local originals/backups stay in place until a separate verified transfer
and any removal are approved. See [the application-only policy](APPLICATION_ONLY_POLICY.md).

Git credentials, user research data and signing keys never belong in the public
download area. Application source/notice delivery follows the current
[source-delivery policy](OPEN_SOURCE_RELEASE_zh_TW.md); the historical Git repository
must not be made public as a shortcut because earlier history contains data.

## Provider-neutral download layout

An authorized GitHub Release or another approved public HTTPS origin may be used.
`https://downloads.example.org/msh` is a placeholder, not a configured service.
The local finalization tool neither creates storage nor uploads anything, and it
does not change the compiled updater URL in `msh_update.py`.

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

The local `dist/release/v<version>/` directory is a build workspace. Preserve the
original installers and independent backups until long-term storage has been
chosen and any removal separately approved. A source rebuild does not guarantee
byte-identical reconstruction of an older installer. Keep one runtime per
finalized bundle; CPU/GPU variants need separate bundles/public base paths.

## Standard release flow

1. On a trusted development machine, clone or safely synchronize the source
   repository and create a release branch.
2. Keep user models/research data outside the application. No old WBC model or
   dataset is required to build MSH; users select their own models in the GUI.
3. Run tests and save their machine-readable result in the release record/work log.
4. Commit reviewed source, create the annotated `v<version>` tag, and build from a
   clean worktree with `scripts/build_release.ps1`.
5. The build copies matching notes from `docs/release/` into the generated version
   directory. If `-PublicBaseUrl` was not supplied to the build, run:

   ```powershell
   .\scripts\finalize_release_bundle.ps1 `
     -BundleDirectory .\dist\release\v0.1.4 `
     -PublicBaseUrl https://downloads.example.org/msh
   ```

   Finalization checks checksums, build identity and explicit user-supplied-model/
   no-research-data fields. It rejects candidate/dirty builds, extra files or
   directories and existing finalized metadata. It does not unpack the installer
   or perform installation/hardware acceptance. `-PublicBaseUrl` cannot be combined
   with `-Candidate` or `-SkipInstaller`; no destination is needed merely to build.

6. After publication is authorized and required acceptance/source delivery is
   complete, upload that version directory. Verify a fresh download against its SHA-256.
7. Publish the generated `latest.json` at the bucket root only after validation.

Upload credentials must be stored in the machine or CI secret store, never in Git,
the build manifest, a batch file, or the installed application.

## Portability checklist

To work from another city or country, the new machine needs only:

- access to the application source, including reviewed branches and tags;
- separately supplied local models/data only for the tasks that need them;
- the documented Python/build toolchain or a controlled Windows CI builder;
- publication credentials held by the operator or CI secret store.

Camera profiles, COM choices, motor parameters, calibration data, captured images,
datasets, and user output remain device/local-data concerns. They must not be
silently replaced by an application update.

The [v0.1.3 audit](releases/v0.1.3-evidence.md) is historical evidence. Its old
installer/model hashes and missing exact GUI-source findings do not authorize
publishing that build or require bundling old models in current MSH.
