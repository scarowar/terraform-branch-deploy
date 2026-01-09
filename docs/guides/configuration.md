# Configuration

The `.tf-branch-deploy.yml` file defines your environments and Terraform settings.

## Minimal Config

```yaml
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/dev
  prod:
    working-directory: terraform/prod
```

## Full Config

```yaml
default-environment: dev
production-environments: [prod]
stable-branch: main

defaults:
  var-files:
    paths:
      - ../common.tfvars
  plan-args:
    args:
      - "-parallelism=20"

environments:
  dev:
    working-directory: terraform/dev
    var-files:
      inherit: true
      paths:
        - dev.tfvars
  
  prod:
    working-directory: terraform/prod
    var-files:
      inherit: true
      paths:
        - prod.tfvars
    plan-args:
      inherit: false
      args:
        - "-parallelism=10"
```

## Fields

| Field | Required | Description |
|-------|----------|-------------|
| `default-environment` | Yes | Default when no env specified |
| `production-environments` | Yes | List of production environments |
| `stable-branch` | No | Branch for rollbacks (default: `main`) |
| `environments` | Yes | Environment definitions |

## Environment Fields

| Field | Description |
|-------|-------------|
| `working-directory` | Path to Terraform root module |
| `var-files` | Variable files to pass to TF |
| `backend-configs` | Backend configuration values |
| `plan-args` | Additional `terraform plan` args |
| `apply-args` | Additional `terraform apply` args |
| `init-args` | Additional `terraform init` args |

## Inheritance

By default, environments inherit from `defaults`. Disable with:

```yaml
prod:
  var-files:
    inherit: false
    paths:
      - prod-only.tfvars
```

## Schema Validation

IDE validation is available via JSON schema:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/scarowar/terraform-branch-deploy/main/tf-branch-deploy.schema.json
```
