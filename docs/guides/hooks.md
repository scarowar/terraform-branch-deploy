# Pre-Terraform Hooks

Run custom shell commands before Terraform executes.

## Usage

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    pre-terraform-hook: |
      echo "Building assets..."
      npm ci && npm run build
```

## Available Environment Variables

| Variable | Description |
|----------|-------------|
| `TF_BD_ENVIRONMENT` | Target environment (e.g., `dev`) |
| `TF_BD_SHA` | Git commit SHA |
| `TF_BD_OPERATION` | `plan` or `apply` |

## Examples

### Build Assets

```yaml
pre-terraform-hook: |
  cd assets
  npm ci
  npm run build
  zip -r function.zip dist/
```

### Fetch Dynamic Configuration

```yaml
pre-terraform-hook: |
  ./scripts/fetch-config.sh \
    --env "$TF_BD_ENVIRONMENT" \
    --output terraform.tfvars.json
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
    API_KEY: ${{ secrets.API_KEY }}
    SECRET_TOKEN: ${{ secrets.SECRET_TOKEN }}
```
