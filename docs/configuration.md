# Configuration

Learn how to configure Terraform Branch Deploy for your workflows, environments, and advanced use cases.

## Action Inputs

The action accepts several inputs to customize its behavior. Add these under the `with:` section in your workflow YAML.

| Input                | Description                                                                                                    | Default   | Example                         |
|----------------------|----------------------------------------------------------------------------------------------------------------|-----------|----------------------------------|
| `github-token`       | GitHub token with required permissions                                                                         | —         | `${{ secrets.GITHUB_TOKEN }}`    |
| `terraform-version`  | Terraform CLI version to use                                                                                  | `latest`  | `1.7.5`                         |
| `working-directory`  | Default path to Terraform files                                                                                | `.`       | `infrastructure/`               |
| `noop-trigger`       | Command for plan operations                                                                                   | `.plan`   | `.preview`                      |
| `trigger`            | Command for apply operations                                                                                  | `.apply`  | `.deploy`                       |
| `stable_branch`      | Branch for rollback operations                                                                                | `main`    | `master`                        |
| `skip`               | Extract environment info and exit early (Skip Mode). See [Skip Mode](#skip-mode) below.                      | `false`   | `true`                          |
| `admins`             | Comma-separated list of admin users/teams                                                                     | —         | `monalisa,octocat,my-org/my-team`|
| `admins_pat`         | Personal access token for org team access                                                                     | —         | `${{ secrets.ADMIN_PAT }}`       |
| `disable_naked_commands` | Require environment for commands (e.g., `.plan to dev`). Block naked commands for safety.                | `"true"`    | `"false"`                         |

!!! tip
    Most users only need to set `github-token`. Other inputs are optional and for advanced scenarios.

## Action Outputs

Outputs are available as step outputs in your workflow. Use them for conditional logic or chaining steps.

| Output           | Description                                                      |
|------------------|------------------------------------------------------------------|
| `env`            | The environment selected for deployment                          |
| `continue`       | "true" if deployment should continue, otherwise empty           |
| `sha`            | The SHA of the branch to be deployed                            |
| `rollback`       | "true" if this is a rollback operation                         |
| `plan`           | "true" if this is a plan operation                             |
| `apply`          | "true" if this is an apply operation                           |
| `params`         | The raw parameters passed into the deployment command           |
| `parsed_params`  | Stringified JSON of parsed parameters                           |

## YAML Configuration File

The `.tf-branch-deploy.yml` file defines your deployment environments, defaults, and advanced options. Its structure is validated by a JSON schema for IDE autocompletion and error checking.

Below is an extensive example covering all supported fields, with inline annotations explaining each part:

```yaml linenums="1" title=".tf-branch-deploy.yml (full example)"
# yaml-language-server: $schema=./tf-branch-deploy.schema.json  # (1)
default-environment: dev  # (2)
production-environments:  # (3)
  - prod
  - main
defaults:  # (4)
  var-files:  # (5)
    paths:
      - common.tfvars
  backend-configs:  # (6)
    paths:
      - common.backend.tfvars
  plan-args:  # (7)
    args:
      - "-compact-warnings"
  apply-args:  # (8)
    args:
      - "-auto-approve"
  init-args:  # (9)
    args:
      - "-upgrade"
environments:  # (10)
  dev:  # (11)
    working-directory: ./terraform/dev  # (12)
    var-files:
      paths:
        - ./terraform/dev/dev.tfvars
    backend-configs:
      paths:
        - ./terraform/dev/dev.backend.tfvars
    plan-args:
      args:
        - "-parallelism=10"
    apply-args:
      args:
        - "-auto-approve=false"
    init-args:
      args:
        - "-reconfigure"
  prod:  # (13)
    working-directory: ./terraform/prod
    var-files:
      inherit: false  # (14)
      paths:
        - ./terraform/prod/prod.tfvars
        - ./terraform/prod/secrets.tfvars
    backend-configs:
      inherit: false  # (15)
      paths:
        - ./terraform/prod/prod.backend.tfvars
    plan-args:
      inherit: false  # (16)
      args:
        - "-parallelism=30"
    apply-args:
      args:
        - "-auto-approve"
    init-args:
      args:
        - "-upgrade"
```

1.  **YAML schema reference** — Enables IDE autocompletion and validation.
2.  **default-environment** — The default environment to deploy to if none is specified.
3.  **production-environments** — List of environments considered production for extra safety and GitHub deployment status.
4.  **defaults** — Shared settings inherited by all environments unless overridden.
5.  **var-files** — Default variable files for all environments.
6.  **backend-configs** — Default backend config files for all environments.
7.  **plan-args** — Default arguments for `terraform plan`.
8.  **apply-args** — Default arguments for `terraform apply`.
9.  **init-args** — Default arguments for `terraform init`.
10. **environments** — Map of environment names to their configuration.
11. **dev** — Example environment definition.
12. **working-directory** — Path to the Terraform code for this environment.
13. **prod** — Example production environment definition.
14. **inherit: false** — Prevents inheriting defaults for this section.
15. **inherit: false** — Prevents inheriting backend-configs defaults.
16. **inherit: false** — Prevents inheriting plan-args defaults.

Refer to the [schema file](https://github.com/scarowar/terraform-branch-deploy/blob/main/tf-branch-deploy.schema.json) for a full list of supported fields and validation rules.

### Inheritance and Overrides

You can define shared defaults and override them per environment. For example:

```yaml linenums="1" title="Partial config: Inheritance and overrides"
defaults:
  plan-args:
    args: ["-compact-warnings"]

environments:
  prod:
    plan-args:
      inherit: false  # Don't inherit defaults
      args: ["-parallelism=30"]
```

!!! note
    Use `inherit: false` to prevent an environment from inheriting a default value.

## Skip Mode

The `skip` input enables a special mode where the action only extracts environment info and outputs, without running any Terraform operations. This is useful for advanced workflows, secrets management, or conditional logic.

```yaml title="Workflow step: Skip mode"
- name: Extract environment info only
  uses: scarowar/terraform-branch-deploy@v0.1.0
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    skip: true

- name: Use environment info
  run: echo "Target environment is ${{ steps.extract-env.outputs.env }}"
```

!!! tip
    Skip mode is ideal for multi-step workflows or when integrating with other tools.

## Best Practices

- Use `production-environments` to protect critical environments.
- Keep secrets and sensitive variables in secure files or GitHub secrets.
- Use inheritance to avoid duplication, but override as needed for special cases.
- Validate your YAML with the provided schema for IDE autocompletion and error checking.

---

See [Commands](commands.md) for all supported PR commands, or [Advanced Workflows](advanced.md) for more complex scenarios.
