# Terraform Branch Deploy

[![GitHub release](https://img.shields.io/github/v/release/scarowar/terraform-branch-deploy)](https://github.com/scarowar/terraform-branch-deploy/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-zensical-purple)](https://scarowar.github.io/terraform-branch-deploy/)

Terraform integrated into the [Branch Deploy](https://github.com/github/branch-deploy) operating model.

**[Documentation](https://scarowar.github.io/terraform-branch-deploy/)** · **[Quickstart](https://scarowar.github.io/terraform-branch-deploy/quickstart/)** · **[Configuration](https://scarowar.github.io/terraform-branch-deploy/configuration/)**

---

## The Problem

Traditional CI/CD deploys after merging. If deployment fails, main is broken.

## The Solution

Branch Deploy inverts this: deploy from your PR branch first, then merge if successful. Main stays stable. To roll back, deploy main.

Terraform Branch Deploy applies this model to infrastructure:

1. **Plan** from your pull request
2. **Review** the changes
3. **Apply** that exact plan

The plan is cached and checksummed. What you review is what gets applied.

---

## Quick Start

**1. Create `.tf-branch-deploy.yml`:**

```yaml
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/dev
  prod:
    working-directory: terraform/prod
```

**2. Create `.github/workflows/deploy.yml`:**

```yaml
name: Deploy
on:
  issue_comment:
    types: [created]

permissions:
  contents: write
  pull-requests: write
  deployments: write

jobs:
  deploy:
    if: github.event.issue.pull_request
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: scarowar/terraform-branch-deploy@v0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/checkout@v4
        if: env.TF_BD_CONTINUE == 'true'
        with:
          ref: ${{ env.TF_BD_REF }}

      - uses: scarowar/terraform-branch-deploy@v0
        if: env.TF_BD_CONTINUE == 'true'
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

**3. Comment on a PR:** `.plan to dev`

---

## Commands

| Command | Effect |
|---------|--------|
| `.plan to <env>` | Preview infrastructure changes |
| `.apply to <env>` | Apply the reviewed plan |
| `.apply main to <env>` | Rollback to main branch |
| `.lock <env>` | Acquire environment lock |
| `.unlock <env>` | Release lock |

Pass extra arguments: `.plan to prod | -target=module.database`

---

## Documentation

- **[Quickstart](https://scarowar.github.io/terraform-branch-deploy/quickstart/)** — First deployment in 5 minutes
- **[Trigger and Execute](https://scarowar.github.io/terraform-branch-deploy/concepts/modes/)** — Two-mode architecture
- **[Configuration](https://scarowar.github.io/terraform-branch-deploy/configuration/)** — Environment setup and inheritance
- **[Commands Reference](https://scarowar.github.io/terraform-branch-deploy/reference/commands/)** — All PR comment commands
- **[Inputs Reference](https://scarowar.github.io/terraform-branch-deploy/reference/inputs/)** — Workflow configuration
- **[Security](https://scarowar.github.io/terraform-branch-deploy/security/)** — Access control and guardrails
- **[Troubleshooting](https://scarowar.github.io/terraform-branch-deploy/troubleshooting/)** — Common issues

---

## Requirements

- GitHub repository with Terraform configurations
- GitHub Actions enabled
- Cloud provider credentials (AWS, GCP, or Azure)

---

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

---

## License

[MIT](LICENSE)
