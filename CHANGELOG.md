# Changelog

## 0.2.0 (2026-01-09)

### Breaking Changes

* Remove deprecated `run` CLI command - use `parse` or `execute` instead

### Features

* Restructure CLI with three clear commands: `parse`, `execute`, and `validate`
* Add plan-before-apply safety (requires plan file for same SHA before apply)
* Add environment locking via `.lock` and `.unlock` commands
* Add rollback support with `.apply main to <env>` syntax
* Add pre-terraform hooks for custom pre-deploy logic
* Add dynamic arguments via PR comments (e.g., `.plan to dev | -target=module.api`)

### Improvements

* Update all action references to `@v0.2.0`
* Remove hypothesis and httpx dependencies for simpler test setup
* Simplify pyproject.toml configuration
* Restructure README with substantive feature descriptions
* Align documentation structure with insomnia-run project

### Removed

* Remove deprecated `run` CLI command
* Remove release-please workflow (manual releases)
* Remove `.actrc` and act event fixtures
* Remove `.hypothesis` test cache

---

## 0.1.0 (2025-07-27)

### Features

* create foundational composite action ([857b8cf](https://github.com/scarowar/terraform-branch-deploy/commit/857b8cfb28d546aa14d8fa816937f9945e48e5b4))
* support multiple terraform args ([b340023](https://github.com/scarowar/terraform-branch-deploy/commit/b340023dde3dadb36a258e743ade9df8c6e75c43))

### Bug Fixes

* pin workflows to full length commit hash ([dcb2df0](https://github.com/scarowar/terraform-branch-deploy/commit/dcb2df0cc5cabc96530c8ef93b4e7f5bcbfa56da))
* restrict github token permissions within ci ([61cd4c4](https://github.com/scarowar/terraform-branch-deploy/commit/61cd4c46049667eb9f5108eee4ba1cce4b9e9ccb))

### Miscellaneous Chores

* release 0.1.0 ([c4793a9](https://github.com/scarowar/terraform-branch-deploy/commit/c4793a9aa5c6cd0bed9458862a39b3c3c4e633ab))
