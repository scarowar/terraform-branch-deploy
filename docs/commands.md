# Commands

Terraform Branch Deploy supports a set of pull request commands for safe, auditable, and flexible infrastructure automation. Use these commands as PR comments to trigger actions.


## Core Commands

| Command Pattern                        | Description                                                      | Example Usage                |
|----------------------------------------|------------------------------------------------------------------|------------------------------|
| `.plan to <env>`                       | Preview changes for a specific environment (noop mode)            | `.plan to dev`               |
| `.plan to <env> | <args>`              | Preview with extra Terraform CLI arguments                        | `.plan to dev | -var=debug=true` |
| `.apply to <env>`                      | Deploy this branch to the environment                             | `.apply to dev`              |
| `.apply <branch> to <env>`             | Rollback the environment to a specific branch                     | `.apply main to dev`         |
| `.apply to <env> | <args>`             | Deploy with extra Terraform CLI arguments                         | `.apply to dev | -auto-approve=false` |

!!! tip
    All commands require an environment (e.g., `to dev`). By default, naked commands (without an environment) are blocked for safety. You can allow them by setting `disable_naked_commands: false` in your workflow.


## Locking & Unlocking

| Command Pattern                                 | Description                                                      | Example Usage                        |
|-------------------------------------------------|------------------------------------------------------------------|--------------------------------------|
| `.lock <env>`                                   | Obtain the deployment lock for the specified environment          | `.lock dev`                          |
| `.lock <env> --reason <text>`                   | Lock environment with a reason                                   | `.lock dev --reason "maintenance"`  |
| `.lock --global`                                | Obtain a global deployment lock (blocks all environments)         | `.lock --global`                     |
| `.lock --global --reason <text>`                | Global lock with a reason                                        | `.lock --global --reason "incident"`|
| `.unlock <env>`                                 | Release the deployment lock for the specified environment         | `.unlock dev`                        |
| `.unlock --global`                              | Release the global deployment lock                               | `.unlock --global`                   |
| `.lock <env> --details`                         | Show information about the current lock for the environment       | `.lock dev --details`                |
| `.lock --global --details`                      | Show information about the current global deployment lock         | `.lock --global --details`           |
| `.wcid <env>`                                   | Alias for `.lock <env> --details`                                | `.wcid dev`                          |

![Locking an environment with .lock dev](assets/images/lock.png)
/// caption
Comment `.lock dev` on a pull request to obtain a deployment lock for the environment.
///

![Viewing lock details with .wcid dev](assets/images/wcid.png)
/// caption
Comment `.wcid dev` on a pull request to view details about the current lock for the environment.
///

![Unlocking an environment with .unlock dev](assets/images/unlock.png)
/// caption
Comment `.unlock dev` on a pull request to release the deployment lock for the environment.
///


!!! note
    Locking is essential for preventing concurrent or conflicting deployments. Use global locks to block all environments during maintenance or incidents.




## Passing Extra Arguments

You can pass extra Terraform CLI arguments (such as `--target` or `--var`) by piping them after your command. For example:


![Passing extra arguments with pipe syntax](assets/images/plan-extra-args.png)
/// caption
Comment `.plan to dev | --target=null_resource.dev_test` on a pull request to pass extra arguments to Terraform.
///

---

## Best Practices

- Always specify the environment to avoid accidental changes.
- Use locking for production and critical environments.
- Use global locks during maintenance or incidents.
- Use rollback commands (e.g., `.apply main to <env>`) for safe, auditable recovery from mistakes or incidents.
- Use extra arguments for advanced Terraform options.
- Review plan output before applying changes.

---

See [Quickstart](quickstart.md) to get started, or [Advanced Workflows](advanced.md) for more complex scenarios.
