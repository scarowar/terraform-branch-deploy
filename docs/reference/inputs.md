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

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `environment` | Yes | - | Target environment from branch-deploy outputs |
| `operation` | Yes | - | `plan` or `apply` |
| `sha` | Yes | - | Commit SHA from branch-deploy outputs |
| `deployment-id` | No | - | Deployment ID for status updates |
| `pr-number` | No | - | PR number for comments |
| `is-rollback` | No | `false` | Set `true` for rollback (allows apply without plan) |
| `extra-args` | No | - | Extra terraform arguments |

## Branch-Deploy Passthrough Inputs

These inputs are passed to `github/branch-deploy` in dispatch mode.

### Command Triggers

| Input | Default | Description |
|-------|---------|-------------|
| `trigger` | `.apply` | Deploy command trigger |
| `noop-trigger` | `.plan` | Plan command trigger |
| `lock-trigger` | `.lock` | Lock command trigger |
| `unlock-trigger` | `.unlock` | Unlock command trigger |
| `help-trigger` | `.help` | Help command trigger |
| `lock-info-alias` | `.wcid` | Lock info alias |
| `param-separator` | `\|` | Parameter separator |

### Environment Configuration

| Input | Default | Description |
|-------|---------|-------------|
| `environment-targets` | (auto) | Comma-separated environments (auto-detected from config) |
| `production-environments` | (auto) | Comma-separated production environments |
| `environment-urls` | - | Environment URLs mapping |
| `draft-permitted-targets` | - | Environments allowing draft PR deployments |

### Branch & Rollback

| Input | Default | Description |
|-------|---------|-------------|
| `stable-branch` | `main` | Stable branch for rollbacks |
| `update-branch` | `warn` | `disabled`, `warn`, or `force` |
| `outdated-mode` | `strict` | `strict`, `pr_base`, or `default_branch` |
| `allow-sha-deployments` | `false` | Allow deploying specific SHAs |
| `enforced-deployment-order` | - | Required deployment order (e.g., `dev,staging,prod`) |

### Permissions & Security

| Input | Default | Description |
|-------|---------|-------------|
| `permissions` | `write,admin` | Required GitHub permissions |
| `admins` | `false` | Admin users/teams (bypass approvals) |
| `admins-pat` | `false` | PAT for admin team lookups |
| `commit-verification` | `false` | Require verified commits |
| `allow-forks` | `true` | Allow fork deployments |
| `allow-non-default-target-branch` | `false` | Allow non-default target branch deployments |
| `disable-naked-commands` | `true` | Require environment in commands |

### CI & Checks

| Input | Default | Description |
|-------|---------|-------------|
| `checks` | `all` | CI check requirements: `all`, `required`, or check names |
| `ignored-checks` | - | Checks to ignore |
| `skip-ci` | - | Environments that skip CI |
| `skip-reviews` | - | Environments that skip reviews |
| `required-contexts` | `false` | Manually required status contexts |

### Locking

| Input | Default | Description |
|-------|---------|-------------|
| `sticky-locks` | `false` | Keep locks after deployment |
| `sticky-locks-for-noop` | `false` | Keep locks for plan operations |
| `global-lock-flag` | `--global` | Global lock flag |

### Labels

| Input | Default | Description |
|-------|---------|-------------|
| `successful-deploy-labels` | - | Labels for successful deploy |
| `successful-noop-labels` | - | Labels for successful plan |
| `failed-deploy-labels` | - | Labels for failed deploy |
| `failed-noop-labels` | - | Labels for failed plan |
| `skip-successful-noop-labels-if-approved` | `false` | Skip noop labels if PR approved |
| `skip-successful-deploy-labels-if-approved` | `false` | Skip deploy labels if PR approved |

### Advanced

| Input | Default | Description |
|-------|---------|-------------|
| `deployment-confirmation` | `false` | Require deployment confirmation |
| `deployment-confirmation-timeout` | `60` | Confirmation timeout in seconds |
| `use-security-warnings` | `true` | Show security warnings in logs |
| `merge-deploy-mode` | `false` | Enable merge deploy mode |
| `unlock-on-merge-mode` | `false` | Unlock environments on PR merge |
| `environment-url-in-comment` | `true` | Append environment URL to success comment |
| `deploy-message-path` | `.github/deployment_message.md` | Custom deployment message template |
| `reaction` | `eyes` | Reaction emoji for trigger detection |

---

# Outputs Reference

## Dispatch Mode Outputs

From `github/branch-deploy`:

| Output | Description |
|--------|-------------|
| `continue` | `'true'` if deployment should proceed |
| `triggered` | `'true'` if command was detected |
| `environment` | Target environment |
| `sha` | Commit SHA to deploy |
| `ref` | Branch ref to deploy |
| `noop` | `'true'` for plan operations |
| `actor` | User who triggered deployment |
| `params` | Raw parameters from command |
| `comment-id` | Triggering comment ID |
| `deployment-id` | GitHub deployment ID |
| `type` | Command type (`deploy`, `lock`, `unlock`, etc.) |
| `issue-number` | PR/Issue number |

## Terraform-Specific Outputs

| Output | Description |
|--------|-------------|
| `working-directory` | Resolved Terraform working directory |
| `var-files` | JSON array of var files |
| `is-production` | `'true'` if production environment |
| `plan-file` | Path to generated plan file |
| `plan-checksum` | SHA256 of plan file |
| `has-changes` | `'true'` if plan detected changes |
