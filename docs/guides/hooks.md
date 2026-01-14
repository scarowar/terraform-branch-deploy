# Pre-Terraform Hooks

Run custom shell commands before Terraform executes.

## Usage

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    pre-terraform-hook: |
      echo "Building Lambda..."
      npm ci && npm run build
```

## Available Environment Variables

| Variable | Description |
|----------|-------------|
| `TF_BD_ENVIRONMENT` | Target environment (e.g., `dev`) |
| `TF_BD_SHA` | Git commit SHA |
| `TF_BD_OPERATION` | `plan` or `apply` |

## Examples

### Build Lambda Functions

```yaml
pre-terraform-hook: |
  cd lambda
  npm ci
  npm run build
  zip -r function.zip .
```

### Fetch Dynamic Secrets

```yaml
pre-terraform-hook: |
  aws secretsmanager get-secret-value \
    --secret-id "myapp/$TF_BD_ENVIRONMENT/db" \
    --query SecretString --output text > .env
```

### Conditional Logic

```yaml
pre-terraform-hook: |
  if [ "$TF_BD_OPERATION" == "apply" ]; then
    ./scripts/run-migrations.sh --env $TF_BD_ENVIRONMENT
  fi
```

### Multi-Step Build

```yaml
pre-terraform-hook: |
  echo "=== Step 1: Install dependencies ==="
  npm ci

  echo "=== Step 2: Build ==="
  npm run build

  echo "=== Step 3: Validate ==="
  npm run lint
```

## Exit Behavior

If the hook exits with a non-zero code, the workflow fails and Terraform does not run.

## Secrets Access

Hooks run in the workflow context. Pass secrets via environment variables:

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    pre-terraform-hook: |
      ./scripts/auth.sh
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```
