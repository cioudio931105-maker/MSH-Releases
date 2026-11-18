# Workstage migration — 2026-11-18

This is a source-only migration of all visible local and fetched remote branch stages. Each feature/experimental branch stays independent. No hardware branch is automatically merged into the application.

Coverage: 24 source refs; 21 clean snapshots/shared bases; 17 destination working branches; 6 original worktrees; no stashes.

| New branch | Original ref(s) |
|---|---|
| codex/client-update-check | refs/heads/codex/client-update-check |
| codex/integrated-cpu-candidate-20261109 | refs/heads/codex/integrated-cpu-candidate-20261109, refs/remotes/origin/codex/integrated-cpu-candidate-20261109 |
| codex/msh-009-launcher-diagnostics | refs/heads/codex/msh-009-launcher-diagnostics, refs/remotes/origin/codex/msh-009-launcher-diagnostics |
| codex/msh-036-a-site-evidence | refs/heads/codex/msh-036-a-site-evidence, refs/remotes/origin/codex/msh-036-a-site-evidence |
| codex/msh-036-core-integration | refs/heads/codex/msh-036-core-integration, refs/remotes/origin/codex/msh-036-core-integration |
| codex/msh-037-preview-controls | refs/heads/codex/msh-037-preview-controls, refs/remotes/origin/codex/msh-037-preview-controls |
| codex/online-install-update | refs/heads/codex/online-install-update |
| codex/physician-review-v1 | refs/heads/codex/physician-review-v1 |
| codex/release-layout-artifact-review | refs/heads/codex/release-layout-artifact-review, refs/remotes/origin/codex/release-layout-artifact-review |
| codex/user-supplied-models | refs/heads/codex/user-supplied-models, refs/remotes/origin/codex/user-supplied-models |
| codex/migrated-main | refs/heads/main, refs/remotes/origin/main |
| codex/remote-client-update-check | refs/remotes/origin/codex/client-update-check |
| codex/motor-phoenix | refs/remotes/origin/codex/motor-phoenix |
| codex/msh-014-position-validity | refs/remotes/origin/codex/msh-014-position-validity |
| codex/msh-014-release-bsite | refs/remotes/origin/codex/msh-014-release-bsite |
| codex/msh-015-stop-hold | refs/remotes/origin/codex/msh-015-stop-hold |
| codex/single-repo-development | prepared-current-application |

The original main is retained as codex/migrated-main. The destination main is not changed by snapshot preparation. The older local client-update revision and its newer remote revision are both retained.

The active application branch is codex/single-repo-development. Its single-repository publish workflow uses managed per-job authorization. Historical branches preserve unfinished implementations and are not automatically ready for binary release or deployment.

Local metadata, project TODO/work-state snapshots, original external-data locations and environment bindings live under ignored .migration-local. Never force-add it. Original research data/models, old Git history, installed environments and old binaries stay at their existing private/local locations.

Camera, motor and firmware bytes are preserved. Migration is verified by source inventories/hashes and software/mock tests only; all existing B-site, clean-Windows, license and real-update acceptance remains pending.

Only clean migration commits created after explicit authorization can establish these snapshots as new Git branch histories. Nothing is pushed, merged or deleted merely by preparing this record.
