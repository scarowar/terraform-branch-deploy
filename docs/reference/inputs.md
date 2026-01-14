# Inputs Reference

All action inputs for `scarowar/terraform-branch-deploy`.

## Core Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | Yes | - | GitHub token with PR write access |
| `mode` | No | `dispatch` | `dispatch` or `execute` |
| `config-path` | No | `.tf-branch-deploy.yml` | Path to config file |
| `terraform-version` | No | `latest` | Terraform version to install |
| `dry-run` | No | `false` | Print commands without executing |
| `pre-terraform-hook` | No | - | Shell commands before TF runs |

## Execute Mode Inputs

Required when `mode: execute`:

| Input | Description |
|-------|-------------|
| `environment` | Target environment from branch-deploy outputs |
| `operation` | `plan` or `apply` |
| `sha` | Commit SHA from branch-deploy outputs |
| `deployment-id` | Deployment ID for status updates |
| `pr-number` | PR number for comments |
| `is-rollback` | Set `true` for rollback (allows apply without plan) |
| `extra-args` | Extra terraform arguments |

## Branch-Deploy Passthrough

These are passed to `github/branch-deploy` in dispatch mode:

| Input | Default | Description |
|-------|---------|-------------|
| `trigger` | `.apply` | Deploy command trigger |
| `noop-trigger` | `.plan` | Plan command trigger |
| `lock-trigger` | `.lock` | Lock command trigger |
| `unlock-trigger` | `.unlock` | Unlock command trigger |
| `help-trigger` | `.help` | Help command trigger |
| `lock-info-alias` | `.wcid` | Lock info alias |
| `param-separator` | `\|` | Parameter separator |
| `stable-branch` | `main` | Stable branch for rollbacks |
| `update-branch` | `warn` | `disabled`, `warn`, or `force` |
| `outdated-mode` | `strict` | `strict` or `warn` |
| `sticky-locks` | `false` | Keep locks after deploy |
| `checks` | `all` | Which checks to require |
| `permissions` | `write,admin` | Required permissions |

# Outputs Reference

| Output | Description |
|--------|-------------|
| `working_directory` | Resolved working directory |
| `var_files` | JSON array of var files |
| `is_production` | `true` if production environment |
| `plan_file` | Path to generated plan file |
| `plan_checksum` | SHA256 of plan file |
| `has_changes` | `true` if plan detected changes |
