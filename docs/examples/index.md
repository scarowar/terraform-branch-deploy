# Examples

## Basic Setup

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

## With AWS Authentication

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789:role/terraform
    aws-region: us-east-1

- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

## With Pre-Terraform Hook

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    pre-terraform-hook: |
      npm ci
      npm run build
```

## Execute Mode with Policy Check

```yaml
jobs:
  parse:
    runs-on: ubuntu-latest
    outputs:
      continue: ${{ steps.branch-deploy.outputs.continue }}
      environment: ${{ steps.branch-deploy.outputs.environment }}
      sha: ${{ steps.branch-deploy.outputs.sha }}
      noop: ${{ steps.branch-deploy.outputs.noop }}
    steps:
      - uses: github/branch-deploy@v11
        id: branch-deploy
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}

  policy:
    needs: parse
    if: needs.parse.outputs.continue == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/opa-check.sh

  deploy:
    needs: [parse, policy]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: scarowar/terraform-branch-deploy@v0.2.0
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
          environment: ${{ needs.parse.outputs.environment }}
          sha: ${{ needs.parse.outputs.sha }}
          operation: ${{ needs.parse.outputs.noop == 'true' && 'plan' || 'apply' }}
```

## With Terraform Version Pin

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    terraform-version: "1.7.0"
```

## Dynamic Arguments

Comment on PR:

```text
.plan to dev | --target=module.api --refresh=false
```

These arguments are passed to `terraform plan`.
