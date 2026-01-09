# Modes

Terraform Branch Deploy has two modes: **dispatch** (default) and **execute**.

## Dispatch Mode (Default)

All-in-one: Handles comment parsing, locking, status updates, and Terraform execution.

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

Use dispatch mode for 95% of use cases.

## Execute Mode

Runs **only** Terraform. You manage `github/branch-deploy` yourself.

Use this when you need:

- Separate jobs for OPA policy checks
- Manual approval gates
- Matrix builds between parsing and execution

### Example: Policy Check Workflow

```yaml
jobs:
  # Job 1: Parse the command
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

  # Job 2: Policy Check
  policy:
    needs: parse
    if: needs.parse.outputs.continue == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/opa-check.sh ${{ needs.parse.outputs.environment }}

  # Job 3: Execute Terraform
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

## Comparison

| Aspect | Dispatch | Execute |
|--------|----------|---------|
| Comment parsing | ✅ Included | ❌ You handle |
| Locking | ✅ Included | ❌ You handle |
| Status updates | ✅ Included | ❌ You handle |
| Policy gates | Via hooks | ✅ Separate job |
| Setup complexity | Low | Higher |
