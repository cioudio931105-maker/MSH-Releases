# Third-party release review

The project owner selected public application source on 2026-10-19. MSH
first-party source uses AGPL-3.0-only; third-party works keep their original terms.
The full installed-version notice inventory is in [licenses/README.md](licenses/README.md).
This records the source-release direction, not completed public distribution.

The [2026-10-20 native/source audit](docs/THIRD_PARTY_RELEASE_AUDIT_v0.1.4_zh_TW.md)
records the current licensed candidate separately from the older build below.
It identifies unresolved native pylon / AGPL combination rights, exact source
delivery and runtime-notice requirements. Public source selection alone is not
clearance for this binary combination. The working-tree notice collection now
has 114 original texts after recognizing tqdm's British-spelled `LICENCE`;
the already-built source/binary review bundle remains unchanged.

Further source retrieval verified eight PyPI source archives and all 891 checked
installed Python files, and preserved a pinned pypylon wrapper source snapshot.
The candidate FFmpeg DLL exactly matches the pinned upstream OpenCV third-party
binary by SHA-256. Twelve base-runtime notices plus the pyserial upstream license
and NVIDIA embedded license header bring the working-tree total to 128 texts.
See [source evidence and remaining gaps](docs/THIRD_PARTY_SOURCE_INVENTORY_v0.1.4.md)
and [supplemental notices](licenses/SUPPLEMENTAL_NOTICES.md).
These additions require a future source freeze/build and do not clear the native
pylon/AGPL combination or establish complete corresponding-source delivery.

This file is a release-review aid, not legal advice. Confirm the exact package
versions, model provenance, and intended distribution with the project owner
before every public release.

- **Basler pylon / pypylon:** Basler publishes deployment options and an EULA.
  Use only the approved runtime redistributable or copy-deployment path; do not
  redistribute arbitrary SDK files. Include the applicable Basler notices and
  requirements with any release.
- **Ultralytics:** current Ultralytics distribution is offered under AGPL-3.0 or
  an Enterprise license. Public proprietary distribution requires a licensing
  decision before release.
- **PyTorch:** project code is under a BSD-style license; preserve applicable
  notices for bundled binaries and dependencies.
- **OpenCV:** review the Apache-2.0 notice for the version bundled in the build.
- **Models and training data:** current application-only policy excludes all
  model weights and research data from new installers, source handoffs and Git
  commits. Users manage their own model/data rights. Removing weights does not
  remove obligations for the libraries still included in the application.

## v0.1.4 CPU candidate review — 2026-10-19

This is an incomplete redistribution review, not release clearance or a complete
third-party license bundle. The local environment metadata inventory covers 61
distributions at `tmp/msh014-cpu-dependencies.json`; environment membership does
not prove every distribution is included in the frozen executable.

| Component | Candidate build version | Evidence / outstanding action |
| --- | --- | --- |
| Ultralytics | 8.4.123 | Installed metadata identifies AGPL-3.0. Record the applicable source-disclosure/compliance plan or Enterprise entitlement before distributing MSH. User-supplied weights do not remove this bundled library. |
| pypylon | 26.7 | Metadata says Other/Proprietary, but the wheel's own LICENSE has BSD-style redistribution conditions. Read actual notices rather than relying on the metadata label. Review bundled pylon native libraries separately. |
| PyTorch / torchvision | 2.6.0+cpu / 0.21.0+cpu | Metadata identifies BSD-style terms; collect notices for the actual native dependency set too. |
| OpenCV | 5.0.0.93 | Metadata identifies Apache 2.0; review the wheel's bundled native components and notices. |

The checked 4,710-file payload did not contain standalone Ultralytics or pypylon
wheel LICENSE files at their package paths. Some other notices are present,
including torchvision and NumPy notices; that is not a complete license audit.
Before a new public build, collect and package the applicable notices and record
the native-runtime deployment rights. No new license, public-source publication,
vendor contact or paid subscription was selected by that initial review. The
owner subsequently chose the public-source direction; see
[the source release plan](docs/OPEN_SOURCE_RELEASE_zh_TW.md).

The working-tree spec now includes LICENSE, this document and the collected
notice texts in future builds. The existing candidate installer is unchanged
and does not retroactively include those new resources. Native-runtime rights,
complete corresponding sources and exact final binary notices still need review.

Primary references checked on 2026-10-19:

- [Ultralytics licensing](https://www.ultralytics.com/license) describes its AGPL
  source requirements and Enterprise alternative for embedding its software.
- [Basler pypylon LICENSE](https://github.com/basler/pypylon/blob/master/LICENSE)
  covers the wrapper's redistribution conditions; it does not alone settle every
  native pylon component's terms.
- [Basler software licensing information](https://docs.baslerweb.com/pylonapi/cpp/licensing)
  directs users to the licenses supplied with their pylon installation.
