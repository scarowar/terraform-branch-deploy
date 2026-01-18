# Quickstart

Deploy your first infrastructure change in 5 minutes.

## Prerequisites

- GitHub repository with Terraform configurations
- GitHub Actions enabled

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

## Step 2: Create Workflow

Create `.github/workflows/deploy.yml`:

```yaml title=".github/workflows/deploy.yml"
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
      # Checkout to read config file
      - uses: actions/checkout@v4

      # Parse command, acquire lock, export context
      - uses: scarowar/terraform-branch-deploy@v0
        with:
          mode: trigger
          github-token: ${{ secrets.GITHUB_TOKEN }}

      # Checkout PR branch for Terraform
      - uses: actions/checkout@v4
        if: env.TF_BD_CONTINUE == 'true'
        with:
          ref: ${{ env.TF_BD_REF }}

      # Run Terraform
      - uses: scarowar/terraform-branch-deploy@v0
        if: env.TF_BD_CONTINUE == 'true'
        with:
          mode: execute
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

!!! note "Single Job Architecture"
    All steps run in one job. Environment variables from trigger mode are available to subsequent steps automatically.

## Step 3: Add Cloud Credentials

Insert cloud credentials between the checkouts:

=== "AWS"

    ```yaml
    - uses: aws-actions/configure-aws-credentials@v4
      if: env.TF_BD_CONTINUE == 'true'
      with:
        role-to-assume: arn:aws:iam::123456789012:role/terraform
        aws-region: us-east-1
    ```

=== "GCP"

    ```yaml
    - uses: google-github-actions/auth@v2
      if: env.TF_BD_CONTINUE == 'true'
      with:
        workload_identity_provider: projects/123/locations/global/workloadIdentityPools/github/providers/github
        service_account: terraform@project.iam.gserviceaccount.com
    ```

=== "Azure"

    ```yaml
    - uses: azure/login@v2
      if: env.TF_BD_CONTINUE == 'true'
      with:
        client-id: ${{ secrets.AZURE_CLIENT_ID }}
        tenant-id: ${{ secrets.AZURE_TENANT_ID }}
        subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
    ```

## Step 4: Deploy

1. Push the workflow and config files
2. Create a branch with Terraform changes
3. Open a pull request
4. Comment on the PR:

```
.plan to dev
```

The action runs `terraform plan` and posts the output as a PR comment.

After reviewing, apply:

```
.apply to dev
```

---

## Next Steps

- [Trigger and Execute](concepts/modes.md) — How the two-mode architecture works
- [Configuration](configuration/index.md) — Full config reference with inheritance
- [Security](security.md) — Access control and guardrails
