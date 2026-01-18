# Inputs

All action inputs for `scarowar/terraform-branch-deploy`.

---

## Core Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | Yes | - | GitHub token with PR write access |
| `mode` | Yes | - | `trigger` or `execute` |
| `config-path` | No | `.tf-branch-deploy.yml` | Path to config file |
| `terraform-version` | No | `latest` | Terraform version to install |
| `dry-run` | No | `false` | Print commands without executing |

---

## Command Triggers

| Input | Default | Description |
|-------|---------|-------------|
| `trigger` | `.apply` | Deploy command trigger |
| `noop-trigger` | `.plan` | Plan command trigger |
| `lock-trigger` | `.lock` | Lock command trigger |
| `unlock-trigger` | `.unlock` | Unlock command trigger |
| `help-trigger` | `.help` | Help command trigger |
| `lock-info-alias` | `.wcid` | Lock info alias |
| `param-separator` | `\|` | Parameter separator |

---

## Environment Configuration

| Input | Default | Description |
|-------|---------|-------------|
| `environment-targets` | (auto) | Comma-separated environments (auto-detected from config) |
| `production-environments` | (auto) | Comma-separated production environments |
| `environment-urls` | - | Environment URLs mapping |
| `draft-permitted-targets` | - | Environments allowing draft PR deployments |

---

## Branch & Rollback

| Input | Default | Description |
|-------|---------|-------------|
| `stable-branch` | `main` | Stable branch for rollbacks |
| `update-branch` | `warn` | `disabled`, `warn`, or `force` |
| `outdated-mode` | `strict` | `strict`, `pr_base`, or `default_branch` |
| `allow-sha-deployments` | `false` | Allow deploying specific SHAs |
| `enforced-deployment-order` | - | Required deployment order (e.g., `dev,staging,prod`) |

---

## Permissions & Security

| Input | Default | Description |
|-------|---------|-------------|
| `permissions` | `write,admin` | Required GitHub permissions |
| `admins` | `false` | Admin users/teams (bypass approvals) |
| `admins-pat` | `false` | PAT for admin team lookups |
| `commit-verification` | `false` | Require verified commits |
| `allow-forks` | `true` | Allow fork deployments |
| `allow-non-default-target-branch` | `false` | Allow non-default target branch deployments |
| `disable-naked-commands` | `true` | Require environment in commands |

---

## CI & Checks

| Input | Default | Description |
|-------|---------|-------------|
| `checks` | `all` | CI check requirements: `all`, `required`, or check names |
| `ignored-checks` | - | Checks to ignore |
| `skip-ci` | - | Environments that skip CI |
| `skip-reviews` | - | Environments that skip reviews |
| `required-contexts` | `false` | Manually required status contexts |

---

## Locking

| Input | Default | Description |
|-------|---------|-------------|
| `sticky-locks` | `false` | Keep locks after deployment |
| `sticky-locks-for-noop` | `false` | Keep locks for plan operations |
| `global-lock-flag` | `--global` | Global lock flag |

