# Quickstart

Get started with Terraform Branch Deploy in your repository in just a few steps.

## Prerequisites

Before you begin, make sure you have:

- A GitHub repository with your Terraform configuration files
- Cloud provider credentials (AWS, Azure, GCP, etc.)
- Permissions to use GitHub Actions and Deployments

## 1. Add the Workflow

Create a workflow file at `.github/workflows/terraform-deploy.yml` in your repository:

```yaml linenums="1" title=".github/workflows/terraform-deploy.yml"
name: "Terraform Branch Deploy"

on:
  issue_comment:
    types: [created]

permissions:
  pull-requests: write
  deployments: write
  contents: write
  checks: read
  statuses: read

jobs:
  terraform_deployment:
    if: ${{ github.event.issue.pull_request }}
    runs-on: ubuntu-latest
    steps:
      # Add your cloud authentication here (AWS, Azure, GCP, etc.)
      - name: terraform-branch-deploy
        uses: scarowar/terraform-branch-deploy@v0.1.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## 2. Configure Environments

Add a `.tf-branch-deploy.yml` file to your repository root. Example:

```yaml linenums="1" title=".tf-branch-deploy.yml"
# yaml-language-server: $schema=./tf-branch-deploy.schema.json

default-environment: dev
production-environments:
  - prod
defaults:
  var-files:
    paths:
      - common.tfvars
environments:
  dev:
    working-directory: ./terraform/dev
    var-files:
      paths:
        - ./terraform/dev/dev.tfvars
  prod:
    working-directory: ./terraform/prod
    var-files:
      inherit: false
      paths:
        - ./terraform/prod/prod.tfvars
        - ./terraform/prod/secrets.tfvars
```

## 3. Deploy from a Pull Request

Comment on any pull request to preview, deploy, or rollback changes:

- `.plan to dev` — Preview changes for the `dev` environment
- `.apply to dev` — Deploy changes to the `dev` environment
- `.apply main to prod` — Rollback `prod` to the `main` branch

!!! tip

    Add extra Terraform arguments with a pipe, e.g. `.plan to dev | -var=debug=true`

## Next Steps

- See [Configuration](configuration.md) for advanced options
- Explore [Commands](commands.md) for all supported PR commands
- Learn about [Advanced Workflows](advanced.md) and best practices
