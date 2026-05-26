# Changelog

All notable changes to Terraform Branch Deploy are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

[0.2.0]: https://github.com/scarowar/terraform-branch-deploy/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/scarowar/terraform-branch-deploy/releases/tag/v0.1.0
