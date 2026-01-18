# Security

Security and governance features to protect your infrastructure from accidental or unauthorized changes.

## Quick Setup by Team Size

=== "Solo / Small Team"

    ```yaml
    - uses: scarowar/terraform-branch-deploy@v0.2.0
      with:
        github-token: ${{ secrets.GITHUB_TOKEN }}
        # Minimal guardrails - fast iteration
        checks: required
        disable-naked-commands: true
    ```

=== "Team (5-20 people)"

    ```yaml
    - uses: scarowar/terraform-branch-deploy@v0.2.0
      with:
        github-token: ${{ secrets.GITHUB_TOKEN }}
        # Standard guardrails
        checks: all
        disable-naked-commands: true
        sticky-locks: true
        outdated-mode: strict
        admins: "lead-dev,platform-team"
    ```

=== "Enterprise"

    ```yaml
    - uses: scarowar/terraform-branch-deploy@v0.2.0
      with:
        github-token: ${{ secrets.GITHUB_TOKEN }}
        # Maximum guardrails
        checks: all
        disable-naked-commands: true
        sticky-locks: true
        outdated-mode: strict
        commit-verification: true
        allow-forks: false
        deployment-confirmation: true
        enforced-deployment-order: "dev,staging,prod"
        admins: "my-org/platform-admins"
        admins-pat: ${{ secrets.ADMIN_PAT }}
    ```

---

## Access Control

### `admins`

**What it does:** Designates users or teams who can deploy without waiting for PR approvals.

**Default:** `false` (no admins)

**When to use:**

- On-call engineers need to deploy hotfixes quickly
- Platform team needs to bypass reviews for emergencies

```yaml
# Single users
admins: "alice,bob"

# GitHub team (requires admins-pat)
admins: "my-org/platform-team"

# Mixed
admins: "alice,my-org/sre-team"
```

!!! warning "Security Consideration"
    Admins bypass branch protection approvals. Grant this sparingly.

### `admins-pat`

**What it does:** Personal Access Token with `read:org` scope for team membership lookups.

**Default:** `false`

**When to use:** Only when using GitHub teams in the `admins` input.

```yaml
admins: "my-org/platform-team"
admins-pat: ${{ secrets.ADMIN_PAT }}
```

### `permissions`

**What it does:** Required GitHub permissions to trigger deployments.

**Default:** `write,admin`

**Options:** `read`, `write`, `admin`, `maintain`

```yaml
# Only collaborators with write access
permissions: "write,admin"

# Also allow maintainers
permissions: "write,admin,maintain"
```

---

## CI/CD Gates

### `checks`

**What it does:** Controls which CI checks must pass before deployment.

**Default:** `all`

**Options:**

| Value | Behavior |
|-------|----------|
| `all` | All CI checks must pass |
| `required` | Only branch protection required checks must pass |
| `check1,check2` | Specific checks by name |

```yaml
# Wait for all checks
checks: all

# Only wait for required checks
checks: required

# Specific checks
checks: "test,lint,security-scan"
```

### `ignored-checks`

**What it does:** Skips specific checks regardless of `checks` setting.

**Default:** `""` (none)

**When to use:** Non-blocking checks like label bots or documentation updates.

```yaml
ignored-checks: "pr-labeler,markdown-lint,dependabot"
```

### `skip-ci`

**What it does:** Environments where CI checks are not required.

**Default:** `""` (all environments require CI)

```yaml
# Dev doesn't need CI for fast iteration
skip-ci: "dev"

# Multiple environments
skip-ci: "dev,sandbox"
```

!!! warning
    Only use this for non-production environments.

### `skip-reviews`

**What it does:** Environments where PR reviews are not required.

**Default:** `""` (all environments require reviews)

```yaml
skip-reviews: "dev"
```

---

## Branch Protection

### `outdated-mode`

**What it does:** How to handle PRs that are behind the target branch.

**Default:** `strict`

**Options:**

| Mode | Behavior |
|------|----------|
| `strict` | Block deployment if branch is behind `main` |
| `pr_base` | Only check against the PR base at time of creation |
| `default_branch` | Check against the default branch only |

```yaml
# Strictest - always deploy latest
outdated-mode: strict

# More lenient
outdated-mode: pr_base
```

### `update-branch`

**What it does:** What to do when a branch is outdated.

**Default:** `warn`

**Options:**

| Value | Behavior |
|-------|----------|
| `disabled` | Don't check if branch is outdated |
| `warn` | Warn user but don't block |
| `force` | Auto-update the branch (not recommended) |

```yaml
update-branch: warn
```

### `commit-verification`

**What it does:** Require signed/verified commits.

**Default:** `false`

**When to use:** High-security environments requiring GPG-signed commits.

```yaml
commit-verification: true
```

### `allow-forks`

**What it does:** Allow deployments from forked repositories.

**Default:** `true`

**When to use:** Set to `false` for private repos or security-sensitive projects.

```yaml
# Block fork deployments
allow-forks: false
```

!!! tip
    Disable this for internal enterprise repositories.

### `allow-non-default-target-branch`

**What it does:** Allow deploying PRs targeting branches other than `main`.

**Default:** `false`

```yaml
# For release branch workflows
allow-non-default-target-branch: true
```

---

## Deployment Locking

### `sticky-locks`

**What it does:** Keep environment locks after deployment completes.

**Default:** `false`

**When to use:** Long-running deployments or when you need to prevent others from deploying during a change window.

```yaml
sticky-locks: true
```

With sticky locks:

- `.lock dev` - Lock environment
- Deploy changes
- `.unlock dev` - Manually release when done

### `sticky-locks-for-noop`

**What it does:** Also use sticky locks for `.plan` commands.

**Default:** `false`

!!! note
    This can cause locks to be forgotten after plan-only workflows.

### Global Locks

Use `.lock --global` to lock all environments at once:

```
.lock --global
```

---

## Deployment Safety

### `disable-naked-commands`

**What it does:** Require explicit environment in commands.

**Default:** `true`

| Command | `disable-naked-commands: true` | `disable-naked-commands: false` |
|---------|-------------------------------|--------------------------------|
| `.plan` | ❌ Blocked | ✅ Uses default-environment |
| `.plan to dev` | ✅ Works | ✅ Works |
| `.apply` | ❌ Blocked | ✅ Uses default-environment |

```yaml
# Enforce explicit environment (recommended)
disable-naked-commands: true
```

### `enforced-deployment-order`

**What it does:** Require deployments in a specific order.

**Default:** `""` (no order enforced)

**When to use:** Ensure changes go through dev → staging → prod.

```yaml
enforced-deployment-order: "dev,staging,prod"
```

If you try to deploy to `prod` before `staging`, you'll get an error.

### `deployment-confirmation`

**What it does:** Require a confirmation step before deployment proceeds.

**Default:** `false`

```yaml
deployment-confirmation: true
deployment-confirmation-timeout: 60  # seconds
```

User must confirm within the timeout window.

### `allow-sha-deployments`

**What it does:** Allow deploying specific commit SHAs instead of branches.

**Default:** `false`

```yaml
# Enable SHA deployments (use with caution)
allow-sha-deployments: true
```

!!! danger
    SHA deployments bypass branch protection. Only enable if absolutely necessary.

---

## Production Protection

### `production-environments`

Set in `.tf-branch-deploy.yml`:

```yaml
production-environments:
  - prod
  - prod-eu
  - prod-asia
```

Production environments get:

- Extra confirmation in comments
- Different styling in tfcmt output
- Separate deployment tracking

### Plan Before Apply

terraform-branch-deploy **requires** a successful `.plan` before `.apply`:

```
❌ .apply to prod
   → Error: No plan file found for this SHA

✅ .plan to prod
   → Plan saved

✅ .apply to prod
   → Applies the saved plan
```

### Rollback Safety

Rollbacks from stable branch don't require a plan:

```
.apply main to prod
```

This applies the known-good state from `main` directly.

---

## Security Warnings

### `use-security-warnings`

**What it does:** Show security warnings in logs for potentially dangerous operations.

**Default:** `true`

```yaml
# Keep security warnings enabled
use-security-warnings: true
```

---

## Complete Enterprise Example

```yaml title=".github/workflows/deploy.yml"
name: Terraform Deploy

on:
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write
  deployments: write
  checks: read
  statuses: read

jobs:
  deploy:
    if: github.event.issue.pull_request
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

          # Access Control
          admins: "my-org/platform-team"
          admins-pat: ${{ secrets.ADMIN_PAT }}
          permissions: "write,admin"

          # CI/CD Gates
          checks: all
          ignored-checks: "pr-labeler"

          # Branch Protection
          outdated-mode: strict
          update-branch: warn
          commit-verification: true
          allow-forks: false

          # Deployment Safety
          disable-naked-commands: true
          enforced-deployment-order: "dev,staging,prod"
          sticky-locks: true

      - uses: actions/checkout@v4
        if: env.TF_BD_CONTINUE == 'true'
        with:
          ref: ${{ env.TF_BD_REF }}

      - uses: scarowar/terraform-branch-deploy@v0.2.0
        if: env.TF_BD_CONTINUE == 'true'
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Guardrails Checklist

Use this checklist to ensure your setup is secure:

- [ ] `disable-naked-commands: true` - Prevent accidental deploys
- [ ] `checks: all` or `checks: required` - Require CI
- [ ] `outdated-mode: strict` - Always deploy latest code
- [ ] `allow-forks: false` - Block untrusted forks (for private repos)
- [ ] `admins` set to specific users/teams - Limit bypass access
- [ ] `production-environments` defined - Mark production envs
- [ ] `enforced-deployment-order` set - Ensure staging before prod
- [ ] `sticky-locks: true` - Prevent concurrent deploys (optional)
- [ ] `commit-verification: true` - Require signed commits (optional)
