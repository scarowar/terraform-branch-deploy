# Getting Started

Deploy your first infrastructure change in 5 minutes.

## Prerequisites

- A GitHub repository with Terraform configurations
- GitHub Actions enabled on the repository

## Step 1: Create Configuration

Create `.tf-branch-deploy.yml` in your repository root:

```yaml title=".tf-branch-deploy.yml"
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/dev
  prod:
    working-directory: terraform/prod
```

> [!TIP]
> Add as many environments as you need. Each maps to a Terraform root module directory.

## Step 2: Create Workflow

Create `.github/workflows/deploy.yml`:

```yaml title=".github/workflows/deploy.yml"
name: Terraform Deploy

on:
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write
  deployments: write

jobs:
  trigger:
    if: github.event.issue.pull_request
    runs-on: ubuntu-latest
    steps:
      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

  execute:
    needs: trigger
    if: env.TF_BD_CONTINUE == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ env.TF_BD_REF }}

      # Optional: Configure cloud provider credentials
      # - uses: aws-actions/configure-aws-credentials@v4
      #   with:
      #     role-to-assume: arn:aws:iam::123456789012:role/terraform
      #     aws-region: us-east-1

      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Step 3: Push and Deploy

```bash
git add .github/workflows/deploy.yml .tf-branch-deploy.yml
git commit -m "Add terraform-branch-deploy"
git push
```

## Step 4: Open a Pull Request

1. Create a branch with Terraform changes
2. Open a pull request
3. Comment on the PR:

```text
.plan to dev
```

The action will:

1. ✅ Parse your command (trigger mode)
2. ✅ Lock the environment
3. ✅ Run `terraform init` and `terraform plan` (execute mode)
4. ✅ Post the plan output as a PR comment
5. ✅ Unlock the environment

## Step 5: Apply Changes

After reviewing the plan, apply with:

```text
.apply to dev
```

The action will:

1. ✅ Verify the plan SHA matches the current commit
2. ✅ Run `terraform apply` with the saved plan
3. ✅ Post the apply output as a PR comment

---

## Available Commands

| Command | Description |
|---------|-------------|
| `.plan to <env>` | Run terraform plan |
| `.apply to <env>` | Run terraform apply |
| `.lock <env>` | Lock environment |
| `.unlock <env>` | Release lock |
| `.wcid` | Who's currently deploying? |
| `.help` | Show available commands |

---

## Next Steps

- **[Configuration Guide](../guides/configuration.md)** — Define environments, var files, backend configs
- **[Guardrails & Security](../guides/guardrails.md)** — Set up access controls, CI gates, deployment safety
- **[Modes](../guides/modes.md)** — Learn about trigger and execute modes
- **[Examples](../examples/index.md)** — Cloud provider auth, monorepos, and more

