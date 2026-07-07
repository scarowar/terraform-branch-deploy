# Configuration

`.tf-branch-deploy.yml` defines the Terraform environments that can be targeted from pull request comments.

## Minimal Configuration

```yaml title=".tf-branch-deploy.yml"
default-environment: dev
production-environments: [prod]

environments:
  dev:
    working-directory: terraform/dev
  prod:
    working-directory: terraform/prod
```

## Root Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| `default-environment` | Yes | none | Environment used by Branch Deploy when a command omits an explicit environment. |
| `production-environments` | Yes | none | Environments that should be treated as production. |
| `stable-branch` | No | `main` | Stable branch recorded in the config. In GitHub Actions, rollback command parsing is controlled by the action input `stable-branch`; set that input too when the stable branch is not `main`. |
| `environments` | Yes | none | Environment definitions keyed by command target name. |
| `defaults` | No | none | Shared Terraform settings inherited by environments. |

For safer workflows, use `disable-naked-commands: true` in the action inputs so users must always write commands such as `.plan to dev`.

## Environment Fields

| Field | Default | Description |
| --- | --- | --- |
| `working-directory` | `.` | Terraform root module path for the environment. |
| `var-files` | none | `.tfvars` files passed to `terraform plan` and direct apply paths such as rollback. Normal saved plan apply uses the saved plan file. |
| `backend-configs` | none | Files passed to `terraform init` as `-backend-config`. |
| `init-args` | none | Extra arguments for `terraform init`. |
| `plan-args` | none | Extra arguments for `terraform plan`. |
| `apply-args` | none | Extra arguments for direct `terraform apply` paths such as rollback. Normal saved plan apply uses the saved plan file. Target and replace arguments are rejected. |
| `timeout` | `3600` | Environment timeout in seconds. Must be between `60` and `14400`. |

Paths are resolved relative to the environment `working-directory`.

Normal apply is intentionally plan-file based: `.apply to <env>` restores the latest successful saved plan for the same environment and commit SHA, then passes that plan file to Terraform. The restored plan artifact name and saved metadata must agree on the plan argument hash. It does not add `var-files` or `apply-args` again. Extra Terraform arguments from PR comments are accepted only on `.plan`.

Rollback applies the stable branch directly. It does not accept PR comment
arguments such as `-target`, because Terraform does not provide a deterministic
target-only rollback operation.

If your stable branch is not `main`, set it in both the config and the trigger-mode action input:

```yaml title=".tf-branch-deploy.yml"
stable-branch: release
```

```yaml title=".github/workflows/deploy.yml"
- uses: scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>
  with:
    mode: trigger
    github-token: ${{ secrets.GITHUB_TOKEN }}
    stable-branch: release
```

## Shared Defaults

Use `defaults` for arguments and files shared by multiple environments:

```yaml title=".tf-branch-deploy.yml"
default-environment: dev
production-environments: [prod]
stable-branch: main

defaults:
  var-files:
    paths:
      - ../shared/common.tfvars
  init-args:
    args:
      - "-upgrade"
  plan-args:
    args:
      - "-parallelism=20"

environments:
  dev:
    working-directory: terraform/dev
    var-files:
      paths:
        - dev.tfvars

  prod:
    working-directory: terraform/prod
    var-files:
      paths:
        - prod.tfvars
    plan-args:
      args:
        - "-parallelism=10"
```

By default, environment settings inherit from `defaults`.

## Inheritance

The inheritable fields are:

- `var-files`
- `backend-configs`
- `init-args`
- `plan-args`
- `apply-args`

Each supports the same shape:

```yaml
var-files:
  inherit: true
  paths:
    - dev.tfvars
```

For argument fields, use `args` instead of `paths`:

```yaml
plan-args:
  inherit: true
  args:
    - "-refresh=false"
```

Set `inherit: false` to replace the default list for a specific environment:

```yaml
prod:
  working-directory: terraform/prod
  var-files:
    inherit: false
    paths:
      - prod-only.tfvars
```

## Complete Example

```yaml title=".tf-branch-deploy.yml"
# yaml-language-server: $schema=https://scarowar.github.io/terraform-branch-deploy/schema.json

default-environment: dev
production-environments: [prod, prod-eu]
stable-branch: main

defaults:
  var-files:
    paths:
      - ../shared/common.tfvars
  backend-configs:
    paths:
      - ../shared/backend.conf
  plan-args:
    args:
      - "-parallelism=20"

environments:
  dev:
    working-directory: terraform/environments/dev
    var-files:
      paths:
        - dev.tfvars

  staging:
    working-directory: terraform/environments/staging
    var-files:
      paths:
        - staging.tfvars

  prod:
    working-directory: terraform/environments/prod
    var-files:
      paths:
        - prod.tfvars
    plan-args:
      inherit: false
      args:
        - "-parallelism=10"

  prod-eu:
    working-directory: terraform/environments/prod-eu
    var-files:
      paths:
        - prod-eu.tfvars
```

## Validation

Enable editor validation with the generated JSON schema.

=== "VS Code"

    Add this comment to `.tf-branch-deploy.yml`:

    ```yaml
    # yaml-language-server: $schema=https://scarowar.github.io/terraform-branch-deploy/schema.json
    ```

=== "JetBrains IDEs"

    Add a JSON Schema mapping:

    | Setting | Value |
    | --- | --- |
    | Name | `terraform-branch-deploy` |
    | Schema URL | Use the schema URL below. |
    | File pattern | `.tf-branch-deploy.yml` |

    ```text
    https://scarowar.github.io/terraform-branch-deploy/schema.json
    ```

The action validates the configuration during execute mode. Unknown fields are rejected.
