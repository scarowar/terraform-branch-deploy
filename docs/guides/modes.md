# Modes

Terraform Branch Deploy uses a **two-mode architecture**: **trigger** and **execute**.

## Overview

| Mode | Purpose |
|------|---------|
| `trigger` | Parse PR comment, export `TF_BD_*` env vars, STOP |
| `execute` | Run terraform with lifecycle completion |

This split enables credential injection between jobs.

## Trigger Mode

Parses the deployment command via `github/branch-deploy` and exports context to environment variables.

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    mode: trigger
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

**After trigger mode, these variables are available:**

| Variable | Description |
|----------|-------------|
| `TF_BD_CONTINUE` | Whether to continue with execution |
| `TF_BD_ENVIRONMENT` | Target environment (dev, prod, etc.) |
| `TF_BD_OPERATION` | Operation: plan, apply, or rollback |
| `TF_BD_IS_ROLLBACK` | Whether this is a rollback |
| `TF_BD_REF` | Git ref to checkout |
| `TF_BD_SHA` | Git commit SHA |

## Execute Mode

Runs terraform and completes the deployment lifecycle (reactions, comments, locks).

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    mode: execute
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

Execute mode reads from `TF_BD_*` environment variables set by trigger mode.

## Complete Workflow

```yaml
jobs:
  trigger:
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

  configure-credentials:
    needs: trigger
    if: env.TF_BD_CONTINUE == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789:role/${{ env.TF_BD_ENVIRONMENT }}

  execute:
    needs: [trigger, configure-credentials]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ env.TF_BD_REF }}
      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Lifecycle Completion

Execute mode automatically handles:

1. Updates deployment status (success/failure)
2. Removes initial 👀 reaction
3. Adds result reaction (🚀 success, 👎 failure)
4. Posts deployment result comment
5. Removes non-sticky locks

## Comparison

| Aspect | Trigger | Execute |
|--------|---------|---------|
| Comment parsing | ✅ Yes | ❌ No |
| Env var export | ✅ Yes | ❌ No |
| Terraform execution | ❌ No | ✅ Yes |
| Lifecycle completion | ❌ No | ✅ Yes |
| Runs built-in hooks | ❌ No | ✅ Yes |
