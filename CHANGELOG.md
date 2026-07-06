# Changelog

All notable changes to Terraform Branch Deploy are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - Unreleased

### Changed

- **Breaking:** Saved plans now persist between the plan and apply runs as GitHub Actions workflow artifacts instead of the Actions cache. GitHub made the Actions cache read-only for `issue_comment`-triggered workflows on 2026-06-26, which silently broke cache-based plan saves. Workflows must grant `actions: read` to the GitHub token so apply can list and download plan artifacts.
- Plans saved by v0.2.x (Actions cache) are not restored; re-run `.plan` after upgrading.
- Embedded `github/branch-deploy` updated from v11.1.4 to v11.1.5.

### Added

- Plan intent records: every plan run uploads an intent artifact before Terraform runs, and apply resolves the plan only through the newest intent — a superseded plan (for example, one created with different `-target` arguments) can never be applied, and a failed latest plan attempt blocks apply with an actionable comment.
- `plan-retention-days` input controlling how long saved plan artifacts are kept (default 7 days, matching the previous cache eviction window).
- `restore-plan` and `declare-plan-intent` CLI commands backing the artifact persistence and intent guardrails.

### Fixed

- A plan that cannot be persisted now fails the plan run with an actionable PR comment instead of silently succeeding and leaving a later apply unable to find the plan.
- Artifact selection no longer relies on the GitHub API's undocumented list order; the latest plan intent is chosen by an explicit numeric sort of workflow run identifiers.
- GitHub API calls during artifact listing and download now carry explicit timeouts, converting network stalls into loud failures instead of hung jobs.
- A truncated artifact search (page cap) now fails the restore instead of reporting "no plan found".

### Security

- Plan artifact restore rejects artifacts uploaded by workflow runs of fork repositories, closing a plan-spoofing vector; workflow artifacts are also immutable once uploaded, unlike cache entries.
- Artifact names claiming a workflow run other than the one that uploaded them are rejected as spoofed.
- Artifact extraction never trusts archive member paths: absolute paths, traversal components, and unexpected file names abort the restore.

## [0.2.0] - 2026-05-26

### Added

- Two-mode GitHub Action flow with separate `trigger` and `execute` phases.
- Environment configuration through `.tf-branch-deploy.yml`.
- Saved Terraform plan files with metadata and checksum verification.
- Terraform plan, apply, rollback, lock, unlock, and status workflows through Branch Deploy commands.
- GitHub Enterprise Cloud and GitHub Enterprise Server compatible token handling for runtime setup.

### Changed

- Normal apply now requires the latest successful saved plan for the same environment and commit.
- Extra Terraform arguments from PR comments are accepted only on plan commands.
- Rollback uses the configured stable branch directly and does not consume pull request saved plans.
- Documentation now separates quickstart, configuration, command reference, security, troubleshooting, and upgrading guidance.

### Fixed

- Targeted plans followed by plain apply use the saved targeted plan instead of running a fresh untargeted apply.
- Deployment lifecycle completion now releases non-sticky Branch Deploy locks after successful operations.
- Plan metadata validation now blocks stale, missing, mismatched, or tampered saved plans before apply.
- Apply now refuses restored plans when the cache key params hash and saved metadata params hash do not match.

### Security

- PR comment `-var-file` paths are restricted to relative paths inside the environment working directory after symlink resolution.
- Direct normal apply without a saved plan is blocked.
- Workflow guidance now keeps privileged checkout and cloud credentials behind Branch Deploy approval.

## [0.1.0] - 2025-07-27

### Added

- Initial Terraform Branch Deploy action release.

[0.3.0]: https://github.com/scarowar/terraform-branch-deploy/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/scarowar/terraform-branch-deploy/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/scarowar/terraform-branch-deploy/releases/tag/v0.1.0
