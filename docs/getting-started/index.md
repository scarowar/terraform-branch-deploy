# Getting Started

## Prerequisites

- A GitHub repository
- Terraform configurations in your repo

## Step 1: Create Config

Create `.tf-branch-deploy.yml` in your repository root:

```yaml
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/dev
  prod:
    working-directory: terraform/prod
```

## Step 2: Create Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Terraform Deploy

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

      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Step 3: Push and Deploy

```bash
git add .github/workflows/deploy.yml .tf-branch-deploy.yml
git commit -m "Add terraform-branch-deploy"
git push
```

Open a pull request and comment:

```
.plan to dev
```

## Next Steps

- [Configuration Guide](../guides/configuration.md)
- [Modes: Dispatch vs Execute](../guides/modes.md)
- [Pre-Terraform Hooks](../guides/hooks.md)
