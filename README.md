<div align="center">

# Terraform Branch Deploy

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/images/cover-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/images/cover-light.png">
  <img alt="Terraform Branch Deploy" src="docs/assets/images/cover-light.png" width="600">
</picture>

**Terraform integrated into the [Branch Deploy](https://github.com/github/branch-deploy) operating model.**

[![GitHub release](https://img.shields.io/github/v/release/scarowar/terraform-branch-deploy?style=flat-square)](https://github.com/scarowar/terraform-branch-deploy/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/scarowar/terraform-branch-deploy/ci.yml?style=flat-square&label=CI)](https://github.com/scarowar/terraform-branch-deploy/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/scarowar/terraform-branch-deploy?style=flat-square&label=scorecard)](https://securityscorecards.dev/viewer/?uri=github.com/scarowar/terraform-branch-deploy)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

[**Documentation**](https://scarowar.github.io/terraform-branch-deploy/) · [**Quickstart**](https://scarowar.github.io/terraform-branch-deploy/quickstart/) · [**Configuration**](https://scarowar.github.io/terraform-branch-deploy/configuration/)

</div>

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

- [**Quickstart**](https://scarowar.github.io/terraform-branch-deploy/quickstart/) — First deployment in 5 minutes
- [**Trigger and Execute**](https://scarowar.github.io/terraform-branch-deploy/concepts/modes/) — Two-mode architecture
- [**Configuration**](https://scarowar.github.io/terraform-branch-deploy/configuration/) — Environment setup
- [**Commands**](https://scarowar.github.io/terraform-branch-deploy/reference/commands/) — All PR commands
- [**Security**](https://scarowar.github.io/terraform-branch-deploy/security/) — Access control
- [**Troubleshooting**](https://scarowar.github.io/terraform-branch-deploy/troubleshooting/) — Common issues

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
