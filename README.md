# Terraform Branch Deploy

Terraform Branch Deploy brings Terraform into the [Branch Deploy](https://github.com/github/branch-deploy) operating model. It is not a standalone Terraform action—it is Terraform integrated into a deployment workflow designed around stability and reviewability.

---

## The Foundation: Branch Deploy and IssueOps

Branch Deploy is built on a simple principle: **the main branch should always be deployable**.

Traditional CI/CD follows a merge → deploy model: code lands on main, then gets deployed. If the deployment fails, main is now broken. You have merged code that does not work in production. Rollback requires reverting, getting CI green again, and redeploying.

Branch Deploy inverts this. You deploy from the pull request branch *before* merging. If the deployment succeeds, you merge. If it fails, main remains untouched. To roll back, you simply deploy main—it is always in a known-good state.

This model is called **IssueOps**: using GitHub issues and pull requests as the control plane for operations. Instead of pushing buttons in a console or running scripts locally, you post a comment—`.deploy`—and the system handles the rest. The pull request becomes the audit log, the approval gate, and the deployment trigger all in one.

Branch Deploy implements this for application deployments. Terraform Branch Deploy extends it to infrastructure.

---

## Why Terraform Needs This

Terraform has a unique challenge: the plan-apply lifecycle.

A Terraform plan shows what *will* change. An apply executes those changes. The problem is that plans can go stale. If you plan on Monday, approve on Tuesday, and apply on Wednesday, the infrastructure may have drifted. The plan you approved no longer reflects reality.

Most Terraform CI/CD solves this by running `terraform apply -auto-approve` on merge—accepting whatever the current state happens to be. This abandons the core value of Terraform: knowing what will change before it changes.

Terraform Branch Deploy preserves that value. You plan. You review. You apply *that exact plan*. If the branch changes, you re-plan. The plan file is cached, checksummed, and tied to a specific commit. Nothing is applied without explicit approval, and what you approve is what gets applied.

---

## How It Works

The workflow mirrors Branch Deploy, extended for Terraform's two-phase lifecycle.

**Plan**: Post `.plan to dev` on a pull request. The system checks out your branch, runs `terraform plan`, and posts the result as a comment. The plan file is cached.

**Apply**: Post `.apply to dev`. The system retrieves the cached plan, verifies it matches the current commit, and runs `terraform apply` against that exact plan. Results are reported back to the pull request.

**Rollback**: If something goes wrong, post `.apply main to dev`. This deploys the stable main branch directly, bypassing the plan requirement. It is an emergency latch—a fast path back to known-good state.

Environment locking ensures only one deployment runs at a time. No concurrent applies. No state corruption.

---

## Configuration

Create `.tf-branch-deploy.yml` in your repository:

```yaml
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/environments/dev
  prod:
    working-directory: terraform/environments/prod
```

---

## Workflow

The action runs in two phases: **trigger** and **execute**.

```yaml
name: deploy
on:
  issue_comment:
    types: [created]

permissions:
  pull-requests: write
  contents: write
  deployments: write
  id-token: write

jobs:
  deploy:
    if: github.event.issue.pull_request
    runs-on: ubuntu-latest
    steps:
      # Checkout to read config
      - uses: actions/checkout@v4

      # Parse command, acquire lock, export context
      - uses: scarowar/terraform-branch-deploy@v0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

      # Checkout the PR branch
      - uses: actions/checkout@v4
        if: env.TF_BD_CONTINUE == 'true'
        with:
          ref: ${{ env.TF_BD_REF }}

      # Configure cloud credentials
      - uses: aws-actions/configure-aws-credentials@v4
        if: env.TF_BD_CONTINUE == 'true'
        with:
          role-to-assume: arn:aws:iam::${{ vars.AWS_ACCOUNT_ID }}:role/deploy-${{ env.TF_BD_ENVIRONMENT }}
          aws-region: us-east-1

      # Run Terraform
      - uses: scarowar/terraform-branch-deploy@v0
        if: env.TF_BD_CONTINUE == 'true'
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

Trigger mode parses the command, validates permissions, and acquires the environment lock. Execute mode runs Terraform and reports results. Between them, you control checkout, credentials, and any custom steps.

---

## Commands

| Command | Effect |
|---------|--------|
| `.plan to <env>` | Run `terraform plan`, cache the result |
| `.apply to <env>` | Apply the cached plan |
| `.apply main to <env>` | Deploy main branch directly (rollback) |
| `.lock <env>` | Acquire environment lock |
| `.unlock <env>` | Release environment lock |
| `.help` | Show available commands |

Pass extra arguments with a pipe: `.plan to prod | -target=module.database`

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Getting Started](docs/getting-started/index.md) | First deployment walkthrough |
| [Configuration](docs/reference/configuration.md) | Full schema reference |
| [Inputs](docs/reference/inputs.md) | Action inputs and defaults |
| [Troubleshooting](docs/troubleshooting.md) | Common issues |

---

## License

MIT
